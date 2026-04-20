#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║           BESSER-PEARL  –  Script de Ejecución                  ║
║   Instala dependencias (si faltan) y abre terminales separadas  ║
╚══════════════════════════════════════════════════════════════════╝

Uso:
  python run_besser.py                  -> instala deps (si falta) + abre los 3 terminales
  python run_besser.py --skip-deps      -> omite instalación y lanza directamente
  python run_besser.py --only backend   -> solo el backend
  python run_besser.py --only frontend  -> solo el frontend
  python run_besser.py --only agent     -> solo el modeling agent
  python run_besser.py --no-agent       -> backend + frontend

URLs una vez arriba:
  Frontend   -> http://localhost:8080
  Backend    -> http://localhost:9000/besser_api/docs
  Agent WS   -> ws://localhost:8765
"""

import os
import sys
import time
import shutil
import signal
import platform
import argparse
import textwrap
import subprocess
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# Colores / UI
# ──────────────────────────────────────────────────────────────────

BOLD    = "\033[1m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
RESET   = "\033[0m"


def banner():
    print(f"""
{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════════════╗
║           BESSER-PEARL  –  Script de Ejecución                  ║
║   Instala dependencias (si faltan) y abre terminales separadas  ║
╚══════════════════════════════════════════════════════════════════╝
{RESET}""")


def step(msg):  print(f"\n{BOLD}{CYAN}▶  {msg}{RESET}")
def ok(msg):    print(f"{GREEN}✔  {msg}{RESET}")
def warn(msg):  print(f"{YELLOW}⚠  {msg}{RESET}")
def info(msg):  print(f"{CYAN}▶  {msg}{RESET}")
def error(msg): print(f"{RED}✖  {msg}{RESET}")


def fatal(msg):
    error(msg)
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────
# Plataforma
# ──────────────────────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"
IS_LINUX   = platform.system() == "Linux"

NPM_CMD = "npm.cmd" if IS_WINDOWS else "npm"
NPX_CMD = "npx.cmd" if IS_WINDOWS else "npx"


def venv_python(venv_dir):
    if IS_WINDOWS:
        return Path(venv_dir) / "Scripts" / "python.exe"
    return Path(venv_dir) / "bin" / "python"


def venv_pip(venv_dir):
    if IS_WINDOWS:
        return Path(venv_dir) / "Scripts" / "pip.exe"
    return Path(venv_dir) / "bin" / "pip"


# ──────────────────────────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────────────────────────

BASE_DIR     = Path(__file__).resolve().parent
BESSER_DIR   = BASE_DIR / "BESSER"
AGENT_DIR    = BASE_DIR / "modeling-agent"
FRONTEND_DIR = BESSER_DIR / "besser" / "utilities" / "web_modeling_editor" / "frontend"
BESSER_VENV  = BESSER_DIR / "venv"
AGENT_VENV   = AGENT_DIR  / "venv"


# ──────────────────────────────────────────────────────────────────
# Ejecución de subprocesos
# ──────────────────────────────────────────────────────────────────

def _needs_shell(cmd):
    if not IS_WINDOWS:
        return False
    first = str(cmd[0]).lower()
    return first.endswith(".cmd") or first.endswith(".bat")


def run(cmd, cwd=None, env=None, capture=False):
    """Ejecuta un comando; lanza RuntimeError si el proceso falla."""
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        capture_output=capture,
        text=True,
        shell=_needs_shell(cmd),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Comando fallido: {' '.join(str(c) for c in cmd)}\n"
            f"{result.stderr or ''}"
        )
    return result


def run_pip(pip_exec, args, cwd=None):
    run([str(pip_exec)] + args, cwd=cwd)


# ──────────────────────────────────────────────────────────────────
# Detección de Python 3.12
# ──────────────────────────────────────────────────────────────────

def find_python312():
    """
    Devuelve el ejecutable de Python 3.12 o detiene el script.
    Puede devolver:
      "py -3.12"   → Windows py launcher
      ruta absoluta al intérprete
    """
    if IS_WINDOWS:
        py_launcher = shutil.which("py")
        if py_launcher:
            r = subprocess.run(
                ["py", "-3.12", "--version"],
                capture_output=True, text=True
            )
            if r.returncode == 0 and "3.12" in (r.stdout + r.stderr):
                version = (r.stdout + r.stderr).strip()
                ok(f"Python 3.12 encontrado vía py launcher: {version}")
                return "py -3.12"

    for cand in ["python3.12", "python3", "python"]:
        path = shutil.which(cand)
        if not path:
            continue
        r = subprocess.run([path, "--version"], capture_output=True, text=True)
        version_line = (r.stdout + r.stderr).strip()
        if "3.12" in version_line:
            ok(f"Python 3.12 encontrado: {path} ({version_line})")
            return path

    fatal(textwrap.dedent("""
        Python 3.12 no encontrado en el PATH.

        Por qué 3.12 y no una versión mayor:
          pydantic-core (dependencia de FastAPI) necesita Wheels pre-compilados.
          Para Python 3.13+ esos archivos aún no existen, lo que obliga a
          compilar Rust localmente → falla si no tienes Rust instalado.

        Instala Python 3.12:
          Windows : https://www.python.org/downloads/release/python-3129/
                    Marca "Add Python to PATH" durante la instalación.
          macOS   : brew install python@3.12   (o descarga el instalador)
          Linux   : sudo apt install python3.12  /  sudo dnf install python3.12

        Después de instalarlo, abre una NUEVA terminal y vuelve a ejecutar
        el script.
    """))


def check_node_npm():
    node_path = shutil.which("node")
    npm_path  = shutil.which(NPM_CMD) or shutil.which("npm")

    missing = []
    if not node_path:
        missing.append("node")
    if not npm_path:
        missing.append("npm")

    if missing:
        fatal(textwrap.dedent(f"""
            No se encontraron en el PATH: {', '.join(missing)}

            El frontend usa Node.js (recomendado >= 18 LTS).
            Instálalo desde : https://nodejs.org/en/download/
            nvm-windows     : https://github.com/coreybutler/nvm-windows/releases

            Después de instalarlo abre una NUEVA terminal y vuelve a
            ejecutar el script para que el PATH se actualice.
        """))

    r_node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    r_npm  = subprocess.run([NPM_CMD, "--version"], capture_output=True, text=True,
                            shell=IS_WINDOWS)
    ok(f"Node.js {r_node.stdout.strip()}  /  npm {r_npm.stdout.strip()}")


# ──────────────────────────────────────────────────────────────────
# Instalación de dependencias
# ──────────────────────────────────────────────────────────────────

def create_venv(python_exec, venv_dir):
    """Crea el venv solo si no existe ya."""
    venv_dir = Path(venv_dir)
    if venv_dir.exists():
        ok(f"venv ya existe: {venv_dir}")
        return

    print(f"  Creando entorno virtual en {venv_dir} ...")
    if isinstance(python_exec, str) and python_exec.startswith("py "):
        # Windows py launcher: "py -3.12"
        cmd = ["py", "-3.12", "-m", "venv", str(venv_dir)]
    else:
        cmd = [str(python_exec), "-m", "venv", str(venv_dir)]
    run(cmd)
    ok(f"Entorno virtual creado: {venv_dir}")


def install_besser_requirements(pip_exec):
    req = BESSER_DIR / "requirements.txt"
    if not req.exists():
        warn("requirements.txt del core BESSER no encontrado. Se omite.")
        return
    print("  Instalando dependencias del BESSER core...")
    run_pip(pip_exec, ["install", "-r", str(req)], cwd=BESSER_DIR)
    ok("Dependencias del BESSER core instaladas")


def install_backend_requirements(pip_exec):
    backend_dir = BESSER_DIR / "besser" / "utilities" / "web_modeling_editor" / "backend"
    req = backend_dir / "requirements.txt"
    if not req.exists():
        warn("requirements.txt del backend no encontrado. Se omite.")
        return
    print("  Instalando dependencias del backend...")
    run_pip(pip_exec, ["install", "-r", str(req)], cwd=backend_dir)
    ok("Dependencias del backend instaladas")


def install_agent_requirements(pip_exec):
    req = AGENT_DIR / "requirements.txt"
    if not req.exists():
        warn("requirements.txt del modeling-agent no encontrado. Se omite.")
        return
    print("  Instalando dependencias del modeling-agent...")
    try:
        run_pip(pip_exec, ["install", "-r", str(req)], cwd=AGENT_DIR)
    except RuntimeError:
        warn("Fallo con caché. Reintentando con --no-cache-dir...")
        run_pip(pip_exec, ["install", "--no-cache-dir", "-r", str(req)], cwd=AGENT_DIR)
    ok("Dependencias del modeling-agent instaladas")


def install_frontend_dependencies():
    if not FRONTEND_DIR.exists():
        warn(f"No se encontró el directorio del frontend: {FRONTEND_DIR}")
        warn("¿Se inicializaron los submódulos correctamente?")
        return

    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        ok("node_modules ya existe — se omite npm install")
        return

    print("  Instalando dependencias npm del frontend (puede tardar varios minutos)...")
    run([NPM_CMD, "install"], cwd=FRONTEND_DIR)

    print("  Ejecutando npm audit fix (no fatal si hay advertencias)...")
    subprocess.run(
        [NPM_CMD, "audit", "fix", "--force"],
        cwd=str(FRONTEND_DIR),
        env=os.environ,
        shell=IS_WINDOWS,
    )
    ok("Dependencias npm del frontend instaladas")


def create_env_file():
    """Crea el .env del frontend a partir del .env.example si no existe."""
    webpack_dir = (
        FRONTEND_DIR / "packages" / "webapp" / "webpack"
    )
    env_example = webpack_dir / ".env.example"
    env_file    = webpack_dir / ".env"

    if env_file.exists():
        ok(f".env ya existe en {webpack_dir}")
        return

    if env_example.exists():
        shutil.copy(str(env_example), str(env_file))
        ok(f".env creado copiando .env.example en {webpack_dir}")
    else:
        env_content = textwrap.dedent("""\
            # === Deployment URLs (Change for local/prod) ===
            # LOCAL:
            DEPLOYMENT_URL=http://localhost:8080
            BACKEND_URL=http://localhost:9000/besser_api
            UML_BOT_WS_URL=ws://localhost:8765

            # PRODUCTION (descomenta y ajusta):
            # DEPLOYMENT_URL=https://editor.besser-pearl.org
            # BACKEND_URL=https://editor.besser-pearl.org/besser_api
            # UML_BOT_WS_URL=wss://editor.besser-pearl.org/agent

            # GitHub OAuth CLIENT ID ONLY (sin secret)
            GITHUB_CLIENT_ID=your_github_client_id_here
        """)
        webpack_dir.mkdir(parents=True, exist_ok=True)
        env_file.write_text(env_content, encoding="utf-8")
        ok(f".env creado con valores por defecto en {webpack_dir}")

    print(f"\n  {YELLOW}⚠  RECUERDA editar el .env en:{RESET}")
    print(f"     {env_file}")
    print(f"  {YELLOW}   Rellena GITHUB_CLIENT_ID con tu OAuth App de GitHub.{RESET}")


def ensure_agent_config():
    """Copia config_example.yaml → config.yaml si no existe."""
    config_example = AGENT_DIR / "config_example.yaml"
    config_file    = AGENT_DIR / "config.yaml"
    if not config_file.exists():
        if config_example.exists():
            shutil.copy(str(config_example), str(config_file))
            ok("config.yaml creado a partir de config_example.yaml")
        else:
            warn("config_example.yaml no encontrado. Crea config.yaml manualmente.")
    else:
        ok("config.yaml ya existe")

    if config_file.exists():
        print(f"\n  {YELLOW}⚠  RECUERDA editar config.yaml del modeling-agent:{RESET}")
        print(f"     {config_file}")
        print(f"  {YELLOW}   Rellena las claves de API (OpenAI, Anthropic, etc.).{RESET}")


def run_dependency_phase():
    """
    Crea los entornos virtuales Python e instala todas las dependencias
    (Python + Node.js) si todavía no están presentes.
    """
    step("Verificando herramientas del sistema")
    python_exec = find_python312()
    check_node_npm()

    # ── Python venv + deps para BESSER / Backend ──────────────────
    step("Entorno virtual Python — BESSER / Backend")
    create_venv(python_exec, BESSER_VENV)
    pip_besser = venv_pip(BESSER_VENV)

    step("Dependencias Python — BESSER core")
    install_besser_requirements(pip_besser)

    step("Dependencias Python — Backend")
    install_backend_requirements(pip_besser)

    # ── Python venv + deps para Modeling Agent ────────────────────
    step("Entorno virtual Python — Modeling Agent")
    create_venv(python_exec, AGENT_VENV)
    pip_agent = venv_pip(AGENT_VENV)

    step("Dependencias Python — Modeling Agent")
    install_agent_requirements(pip_agent)

    # ── Config del agente ─────────────────────────────────────────
    step("Configuración del Modeling Agent")
    ensure_agent_config()

    # ── .env del frontend ─────────────────────────────────────────
    step("Configuración .env del frontend")
    create_env_file()

    # ── Dependencias Node.js ──────────────────────────────────────
    step("Dependencias Node.js — Frontend")
    install_frontend_dependencies()

    print(f"\n{GREEN}{BOLD}✔  Fase de dependencias completada.{RESET}\n")


# ──────────────────────────────────────────────────────────────────
# Validaciones previas al lanzamiento
# ──────────────────────────────────────────────────────────────────

def validate_repos():
    """Verifica que las carpetas de los repositorios existen."""
    problems = []
    if not BESSER_DIR.exists():
        problems.append(f"Carpeta BESSER no encontrada: {BESSER_DIR}")
    if not AGENT_DIR.exists():
        problems.append(f"Carpeta modeling-agent no encontrada: {AGENT_DIR}")
    if not FRONTEND_DIR.exists():
        problems.append(f"Frontend no encontrado: {FRONTEND_DIR}")
    if problems:
        error("Hay problemas con la instalación:")
        for p in problems:
            print(f"  {RED}*{RESET} {p}")
        fatal("Ejecuta primero:  python setup_besser.py")


def validate_venvs():
    """Verifica que los venvs están creados (necesario para lanzar servicios)."""
    problems = []
    if not BESSER_VENV.exists():
        problems.append(f"venv de BESSER no encontrado: {BESSER_VENV}")
    if not AGENT_VENV.exists():
        problems.append(f"venv del modeling-agent no encontrado: {AGENT_VENV}")
    if problems:
        error("Los entornos virtuales no existen:")
        for p in problems:
            print(f"  {RED}*{RESET} {p}")
        fatal("Ejecuta sin --skip-deps para que se instalen automáticamente.")


def check_env_configured():
    env_path = FRONTEND_DIR / "packages" / "webapp" / "webpack" / ".env"
    if not env_path.exists():
        warn(".env del frontend no encontrado.")
        return
    if "your_github_client_id_here" in env_path.read_text(encoding="utf-8"):
        warn(f"GITHUB_CLIENT_ID aún es placeholder. Edita: {env_path}")


def check_agent_config():
    cfg = AGENT_DIR / "config.yaml"
    if not cfg.exists():
        warn(f"config.yaml del modeling-agent no encontrado: {cfg}")


# ──────────────────────────────────────────────────────────────────
# Definición de servicios
# ──────────────────────────────────────────────────────────────────

class ServiceDef:
    """Describe un servicio: nombre, comando, directorio de trabajo."""
    def __init__(self, key, title, cmd, cwd):
        self.key   = key
        self.title = title
        self.cmd   = cmd
        self.cwd   = Path(cwd)


def get_services():
    python_back  = venv_python(BESSER_VENV)
    python_agent = venv_python(AGENT_VENV)

    if not python_back.exists():
        fatal(f"Python del venv de BESSER no encontrado: {python_back}")
    if not python_agent.exists():
        fatal(f"Python del venv del agente no encontrado: {python_agent}")

    # Punto de entrada del agente
    for candidate in ["modeling_agent.py", "main.py", "agent.py", "app.py"]:
        if (AGENT_DIR / candidate).exists():
            agent_entry = candidate
            break
    else:
        py_files = list(AGENT_DIR.glob("*.py"))
        if not py_files:
            fatal(f"No se encontró ningún .py en {AGENT_DIR}")
        agent_entry = py_files[0].name
        warn(f"Punto de entrada del agente detectado: {agent_entry}")

    return {
        "backend": ServiceDef(
            key   = "backend",
            title = "BESSER | Backend (FastAPI - puerto 9000)",
            cmd   = [
                str(python_back), "-m", "uvicorn",
                "besser.utilities.web_modeling_editor.backend.backend:app",
                "--reload", "--port", "9000",
            ],
            cwd   = BESSER_DIR,
        ),
        "frontend": ServiceDef(
            key   = "frontend",
            title = "BESSER | Frontend (Node.js - puerto 8080)",
            cmd   = [NPM_CMD, "run", "dev"],
            cwd   = FRONTEND_DIR,
        ),
        "agent": ServiceDef(
            key   = "agent",
            title = "BESSER | Modeling Agent (WebSocket - puerto 8765)",
            cmd   = [str(python_agent), agent_entry],
            cwd   = AGENT_DIR,
        ),
        "sdd": ServiceDef(
            key   = "sdd",
            title = "BESSER | CC-SDD Server (WebSocket - puerto 8766)",
            cmd   = [str(python_back), "-m", "besser.utilities.ai_sdd.server"],
            cwd   = BESSER_DIR,
        ),
    }


# ──────────────────────────────────────────────────────────────────
# Apertura de terminal por SO
# ──────────────────────────────────────────────────────────────────

def _launch_windows(svc):
    inner    = " ".join(f'"{c}"' if " " in str(c) else str(c) for c in svc.cmd)
    full_cmd = f'cd /d "{svc.cwd}" && {inner}'
    proc = subprocess.Popen(
        f'start "{svc.title}" cmd /k "{full_cmd}"',
        shell=True,
        cwd=str(svc.cwd),
    )
    return proc


def _launch_macos(svc):
    inner    = " ".join(f"'{c}'" if " " in str(c) else str(c) for c in svc.cmd)
    full_cmd = f"cd '{svc.cwd}' && {inner}"
    script = textwrap.dedent(f"""\
        tell application "Terminal"
            do script "printf '\\\\033]0;{svc.title}\\\\007' && {full_cmd}"
            activate
        end tell
    """)
    proc = subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


_LINUX_TERMINALS = [
    ("gnome-terminal", lambda title, cmd_str, cwd:
        ["gnome-terminal", f"--title={title}", "--", "bash", "-c",
         f"cd '{cwd}' && {cmd_str}; echo; echo '--- Proceso terminado. Cierra esta ventana. ---'; exec bash"]),
    ("konsole", lambda title, cmd_str, cwd:
        ["konsole", "--title", title, "-e", "bash", "-c",
         f"cd '{cwd}' && {cmd_str}; exec bash"]),
    ("xfce4-terminal", lambda title, cmd_str, cwd:
        ["xfce4-terminal", f"--title={title}", "-e",
         f"bash -c \"cd '{cwd}' && {cmd_str}; exec bash\""]),
    ("xterm", lambda title, cmd_str, cwd:
        ["xterm", "-title", title, "-e",
         f"bash -c \"cd '{cwd}' && {cmd_str}; exec bash\""]),
    ("lxterminal", lambda title, cmd_str, cwd:
        ["lxterminal", f"--title={title}", "-e",
         f"bash -c \"cd '{cwd}' && {cmd_str}; exec bash\""]),
    ("mate-terminal", lambda title, cmd_str, cwd:
        ["mate-terminal", f"--title={title}", "-e",
         f"bash -c \"cd '{cwd}' && {cmd_str}; exec bash\""]),
    ("tilix", lambda title, cmd_str, cwd:
        ["tilix", "--title", title, "-e",
         f"bash -c \"cd '{cwd}' && {cmd_str}; exec bash\""]),
]


def _find_linux_terminal():
    for name, builder in _LINUX_TERMINALS:
        if shutil.which(name):
            return name, builder
    return None, None


def _launch_linux(svc):
    term_name, builder = _find_linux_terminal()
    inner = " ".join(f"'{c}'" if " " in str(c) else str(c) for c in svc.cmd)

    if term_name:
        cmd_list = builder(svc.title, inner, str(svc.cwd))
        proc = subprocess.Popen(
            cmd_list,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    else:
        warn(
            f"No se encontró ningún emulador de terminal gráfico.\n"
            f"  Iniciando '{svc.title}' en background.\n"
            f"  Los logs aparecerán mezclados en esta terminal."
        )
        proc = subprocess.Popen(svc.cmd, cwd=str(svc.cwd), env=os.environ)
        return proc


def launch_in_terminal(svc):
    info(f"Abriendo terminal para: {svc.title}")
    if IS_WINDOWS:
        proc = _launch_windows(svc)
    elif IS_MAC:
        proc = _launch_macos(svc)
    else:
        proc = _launch_linux(svc)
    ok(f"Terminal abierta para {svc.key}")
    return proc


# ──────────────────────────────────────────────────────────────────
# Argparse
# ──────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Instala dependencias (si faltan) y abre terminales para los servicios de BESSER-PEARL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Ejemplos:
              python run_besser.py                  # instala deps (si falta) + 3 terminales
              python run_besser.py --skip-deps      # salta instalación y lanza directamente
              python run_besser.py --only backend   # solo backend
              python run_besser.py --only frontend  # solo frontend
              python run_besser.py --only agent     # solo modeling agent
              python run_besser.py --no-agent       # backend + frontend
        """),
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Omite la instalación de dependencias y lanza los servicios directamente",
    )
    parser.add_argument(
        "--only",
        choices=["backend", "frontend", "agent"],
        default=None,
        help="Abre únicamente el terminal del servicio indicado",
    )
    parser.add_argument(
        "--no-agent",
        action="store_true",
        help="Abre backend + frontend sin el modeling agent",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

def main():
    banner()
    args = parse_args()

    # Siempre verificamos que los repos estén clonados
    validate_repos()

    if args.skip_deps:
        warn("--skip-deps activo: se omite la instalación de dependencias.")
        validate_venvs()
    else:
        run_dependency_phase()

    check_env_configured()
    check_agent_config()

    all_services = get_services()

    # Filtrar servicios según flags
    if args.only:
        to_launch = {args.only: all_services[args.only]}
    elif args.no_agent:
        to_launch = {k: v for k, v in all_services.items() if k != "agent"}
    else:
        to_launch = all_services

    step("Abriendo terminales de servicios")

    launched = []
    for svc in to_launch.values():
        try:
            proc = launch_in_terminal(svc)
            launched.append((svc, proc))
            time.sleep(0.8)
        except Exception as exc:
            error(f"No se pudo abrir el terminal para '{svc.title}': {exc}")

    if not launched:
        fatal("No se pudo abrir ningún terminal.")

    print(f"""
{BOLD}{GREEN}
══════════════════════════════════════════════════════════════════
   Terminales abiertas — servicios en ejecución
══════════════════════════════════════════════════════════════════
{RESET}""")

    if "backend" in to_launch:
        print(f"  {BLUE}{BOLD}Backend {RESET} -> http://localhost:9000/besser_api")
        print(f"          -> Docs: http://localhost:9000/besser_api/docs")
    if "frontend" in to_launch:
        print(f"  {MAGENTA}{BOLD}Frontend{RESET} -> http://localhost:8080")
    if "agent" in to_launch:
        print(f"  {GREEN}{BOLD}Agent   {RESET} -> ws://localhost:8765")

    print(f"""
  {YELLOW}Cada servicio corre en su propia ventana de terminal.
  Para detener un servicio: cierra su ventana o presiona Ctrl+C en ella.
  Para detenerlos todos:   cierra las ventanas manualmente.{RESET}
  {CYAN}Consejo: usa --skip-deps en próximas ejecuciones para arrancar más rápido.{RESET}
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Cancelado por el usuario.{RESET}")
        sys.exit(0)
    except RuntimeError as exc:
        fatal(str(exc))