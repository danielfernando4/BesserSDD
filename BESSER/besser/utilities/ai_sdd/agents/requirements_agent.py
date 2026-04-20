"""
Requirements Agent — Phase 2 of the CC-SDD Pipeline.

Takes the brief.md and produces a traceable requirements.md with business rules,
functional requirements (EARS syntax), acceptance criteria, and a traceability matrix.
"""

import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

REQUIREMENTS_SYSTEM_PROMPT = """Eres un Analista de Requisitos experto en un entorno de Spec-Driven Development (SDD).
Tu rol es procesar un brief de proyecto y producir un documento de requisitos (requirements.md) completamente estructurado y rastreable en ESPAÑOL.

Debes generar la salida EXACTAMENTE en el formato especificado a continuación. Tu respuesta debe estar completamente en Español.

## TEMPLATE:

# Especificación: {ProjectName}
Estado: Borrador

## 1. Contexto
{Breve explicación del propósito del módulo y el problema que resuelve, derivado del brief.}

## 2. Contexto de Limitación (Boundary Context)

* **En Alcance:**
  - {Elemento dentro del alcance}
* **Fuera de Alcance:**
  - {Elemento excluido del alcance}

## 3. Reglas de Negocio

{Las reglas de negocio son independientes de la tecnología. Responden al POR QUÉ.}

* **[BR-001]** {Descripción de la regla}
* **[BR-002]** {Descripción de la regla}
* **[BR-003]** {Descripción de la regla}

## 4. Requisitos y Criterios de Aceptación (EARS)

{Cada requisito DEBE derivar de una regla de negocio y debe seguir la sintaxis EARS (CUANDO/SI/MIENTRAS..., ENTONCES el sistema DEBE...).}

### [REQ-001] {Título del Requisito}
**Deriva de:** [BR-XXX]
**Intención (EARS):** {CUANDO una condición ocurra, ENTONCES el sistema DEBERÁ realizar una acción.}
**Criterios de Aceptación:**
- [ ] {Criterio medible 1}
- [ ] {Criterio medible 2}

## 5. Matriz de Trazabilidad (BR → REQ)

| Regla de Negocio (BR) | Requisitos Derivados (REQ) | Estado de Cobertura |
| :--- | :--- | :--- |
| **BR-001** | REQ-001, REQ-002 | 🟡 Pendiente |

## RULES / REGLAS:
1. Todo REQ DEBE derivar de al menos un BR.
2. Todo BR DEBE tener al menos un REQ.
3. El idioma de todo el documento es **Español**.
4. Los criterios de aceptación deben ser probables y específicos.
5. La matriz de trazabilidad debe estar completa.
6. Los IDs deben ser secuenciales: BR-001, BR-002, ...; REQ-001, REQ-002, ...
7. NO agregues cercas ocultas adicionales de markdown alrededor del documento principal.
"""


class RequirementsAgent:
    """Generates a traceable requirements.md from a brief.md."""

    def __init__(self, client: GeminiClient):
        self.client = client

    def generate(self, brief_content: str, project_name: str) -> str:
        """Generate requirements.md from the brief.

        Args:
            brief_content: The full text of brief.md.
            project_name: The project name.

        Returns:
            The requirements.md content.
        """
        prompt = (
            f"Based on the following project brief, generate the requirements.md document.\n\n"
            f"--- BEGIN BRIEF ---\n{brief_content}\n--- END BRIEF ---\n\n"
            f"Project Name: {project_name}\n\n"
            f"Generate detailed business rules and functional requirements that fully cover "
            f"the scope defined in the brief. Ensure every business rule maps to at least one "
            f"requirement and vice versa."
        )

        logger.info("[RequirementsAgent] Generating requirements.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=REQUIREMENTS_SYSTEM_PROMPT,
            temperature=0.5,
        )

        logger.info("[RequirementsAgent] Generated requirements.md successfully.")
        return content

    def update(
        self,
        current_requirements: str,
        change_description: str,
        brief_content: str,
    ) -> str:
        """Update requirements.md based on a change (from vibe modeling or manual edit).

        Args:
            current_requirements: Current requirements.md content.
            change_description: Description of what changed and why.
            brief_content: Current brief.md for context.

        Returns:
            Updated requirements.md content.
        """
        prompt = (
            f"You have the current requirements document and a change request. "
            f"Update the requirements document to reflect the change while maintaining "
            f"full traceability.\n\n"
            f"--- CURRENT REQUIREMENTS ---\n{current_requirements}\n--- END ---\n\n"
            f"--- BRIEF (context) ---\n{brief_content}\n--- END ---\n\n"
            f"--- CHANGE REQUEST ---\n{change_description}\n--- END ---\n\n"
            f"Update rules:\n"
            f"1. If new functionality is added, create new BR(s) and REQ(s) as needed.\n"
            f"2. If functionality is modified, update existing BR(s) and REQ(s).\n"
            f"3. If functionality is removed, mark BR(s) and REQ(s) as deprecated (don't delete).\n"
            f"4. Always update the traceability matrix.\n"
            f"5. Keep all existing IDs stable — never renumber.\n"
            f"6. Output the COMPLETE updated requirements.md document."
        )

        logger.info("[RequirementsAgent] Updating requirements.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=REQUIREMENTS_SYSTEM_PROMPT,
            temperature=0.4,
        )
        return content
