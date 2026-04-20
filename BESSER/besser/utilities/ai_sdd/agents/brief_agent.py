"""
Brief Agent — Phase 1 of the CC-SDD Pipeline.

Takes a raw user idea and produces a structured brief.md document that
captures context, scope, and key stakeholders.
"""

import logging
from datetime import datetime
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_PROMPT = """Eres un Analista de Negocios experto en un entorno de Spec-Driven Development (SDD).
Tu rol es tomar una idea vaga de un usuario y transformarla en un documento inicial estructurado (brief) EN ESPAÑOL.

Debes generar la salida EXACTAMENTE en el formato especificado a continuación. Tu respuesta debe estar completamente en Español.

## TEMPLATE:

# Brief: {ProjectName}
Estado: Borrador
Generado: {Date}

## 1. Declaración de Visión
{Una visión de 2-3 oraciones sobre lo que el usuario quiere construir. Sé claro e inspirador.}

## 2. Declaración del Problema
{Identifica el problema central que este software resolverá. Sé específico sobre los puntos de dolor.}

## 3. Solución Propuesta
{Describe la solución a alto nivel — qué hará el sistema para resolver el problema.}

## 4. Alcance Inicial

### En Alcance
- {Característica principal 1}
- {Característica principal 2}
- {Característica principal 3}

### Fuera de Alcance
- {Elemento excluido 1}
- {Elemento excluido 2}

## 5. Stakeholders Clave
- {Interesado 1 y su rol}
- {Interesado 2 y su rol}

## 6. Criterios de Éxito
- {Criterio medible 1}
- {Criterio medible 2}
- {Criterio medible 3}

## RULES / REGLAS:
1. ProjectName debe derivar de la idea del usuario. Usa PascalCase sin espacios (ej. SistemaGestionBiblioteca).
2. La visión debe ser concisa pero comprehensiva.
3. Los elementos de alcance deben ser concretos y accionables.
4. Los criterios de éxito deben ser medibles.
5. NO incluyas detalles de implementación ni elecciones tecnológicas — eso viene después.
6. Escribe todo tu contenido en **Español** para el usuario.
7. Genera ÚNICAMENTE el documento markdown, nada más, sin backticks ocultos de markdown.
"""


class BriefAgent:
    """Generates a structured brief.md from a raw user idea."""

    def __init__(self, client: GeminiClient):
        self.client = client

    def generate(self, user_idea: str) -> tuple[str, str]:
        """Generate a brief.md document from the user's idea.

        Returns:
            A tuple of (project_name, brief_content).
        """
        today = datetime.now().strftime("%Y-%m-%d")

        prompt = (
            f"The user has the following idea for a software product:\n\n"
            f'"{user_idea}"\n\n'
            f"Today's date is {today}.\n\n"
            f"Generate the brief.md document following the template exactly. "
            f"Derive a project name from the user's idea."
        )

        logger.info("[BriefAgent] Generating brief.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=BRIEF_SYSTEM_PROMPT,
            temperature=0.7,
        )

        # Extract project name from the generated content
        project_name = self._extract_project_name(content)
        logger.info(f"[BriefAgent] Generated brief for project: {project_name}")

        return project_name, content

    @staticmethod
    def _extract_project_name(content: str) -> str:
        """Extract the project name from the brief header."""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# Brief:"):
                name = line.replace("# Brief:", "").strip()
                return name if name else "UnnamedProject"
        return "UnnamedProject"
