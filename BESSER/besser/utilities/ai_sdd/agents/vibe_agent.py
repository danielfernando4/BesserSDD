"""
Vibe Modeling Agent — Interactive modification agent for CC-SDD.

Handles natural language instructions to modify the BUML class diagram and/or
requirements, maintaining full bidirectional traceability.
"""

import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

VIBE_SYSTEM_PROMPT = """Eres un Agente experto en Vibe Modeling interactivo en un entorno de Spec-Driven Development (SDD).
Tu rol es interpretar instrucciones en lenguaje natural y determinar qué cambios deben realizarse
al diseño (Diagrama de clases BUML) Y/O a los requisitos.

Recibirás el estado actual de:
1. requirements.md (Business Rules y Requisitos)
2. design.md (Diseño BUML de Clases y Trazabilidad)

El usuario te dará una instrucción como:
- "Agrega un atributo email a la clase Usuario"
- "Quita la clase Manager"

DEBES responder con un objeto JSON describiendo los cambios, **COMPLETAMENTE EN ESPAÑOL**:

{
  "change_type": "design_only" | "requirements_only" | "both",
  "summary": "Resumen legible de lo que cambió en español",
  "design_changes": "Descripción de los cambios de diseño para que el Agente de Diseño los aplique (En Español)",
  "requirements_changes": "Descripción de cambios en requisitos para el Agente de Requisitos (En Español)",
  "new_br_needed": true | false,
  "new_req_needed": true | false,
  "affected_elements": {
    "classes_added": ["NombreClase"],
    "classes_modified": ["NombreClase"],
    "classes_removed": ["NombreClase"],
    "reqs_added": ["REQ-XXX"],
    "reqs_modified": ["REQ-XXX"],
    "brs_added": ["BR-XXX"],
    "brs_modified": ["BR-XXX"]
  },
  "chat_response": "Mensaje amigable en Español diciendo al usuario lo que acabas de hacer"
}

## RULES / REGLAS:
1. Si el usuario modifica el diagrama, DEBES determinar si los requisitos (requirements.md) necesitan actualizarse.
2. Si el usuario modifica los requisitos, DEBES determinar si el diseño necesita actualización.
3. Mantén siempre la trazabilidad bidireccional.
4. El chat_response DEBE ser en Español y ser amigable.
5. Responde SOLAMENTE con el objeto JSON, sin texto extra.
"""


class VibeAgent:
    """Interprets user instructions and orchestrates design/requirements updates."""

    def __init__(self, client: GeminiClient):
        self.client = client

    def analyze_instruction(
        self,
        instruction: str,
        requirements_content: str,
        design_content: str,
    ) -> dict:
        """Analyze a user instruction and determine what changes are needed.

        Args:
            instruction: The user's natural language instruction.
            requirements_content: Current requirements.md content.
            design_content: Current design.md content.

        Returns:
            A dict describing the changes to make.
        """
        prompt = (
            f"The user gives this instruction:\n\n"
            f'"{instruction}"\n\n'
            f"--- CURRENT REQUIREMENTS ---\n{requirements_content}\n--- END ---\n\n"
            f"--- CURRENT DESIGN ---\n{design_content}\n--- END ---\n\n"
            f"Analyze this instruction and return the JSON object describing all changes needed. "
            f"Remember: every design change may require a requirements update and vice versa."
        )

        logger.info(f"[VibeAgent] Analyzing instruction: {instruction[:100]}...")
        result = self.client.generate_json(
            prompt=prompt,
            system_instruction=VIBE_SYSTEM_PROMPT,
            temperature=0.4,
        )

        # Ensure required keys exist
        result.setdefault("change_type", "both")
        result.setdefault("summary", instruction)
        result.setdefault("design_changes", "")
        result.setdefault("requirements_changes", "")
        result.setdefault("new_br_needed", False)
        result.setdefault("new_req_needed", False)
        result.setdefault("affected_elements", {})
        result.setdefault("chat_response", f"I've processed your request: {instruction}")

        logger.info(f"[VibeAgent] Change type: {result['change_type']}")
        return result
