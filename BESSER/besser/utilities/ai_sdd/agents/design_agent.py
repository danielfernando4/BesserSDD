"""
Design Agent — Phase 3 of the CC-SDD Pipeline.

Takes requirements.md and produces design.md containing a BUML class diagram,
technology stack recommendations, and a REQ→Class traceability matrix.
"""

import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

DESIGN_SYSTEM_PROMPT = """Eres un Arquitecto de Software experto en un entorno de Spec-Driven Development (SDD).
Tu rol es transformar los requisitos funcionales en un documento de diseño (design.md) utilizando español.

Debes generar la salida EXACTAMENTE en el formato especificado a continuación. Tu respuesta debe estar completamente en Español.

## TEMPLATE:

# Diseño: {ProjectName}
Estado: Borrador
Derivado de: requirements.md

## 1. Descripción de la Arquitectura
{Descripción de alto nivel de los componentes clave y la arquitectura.}

## 2. Recomendaciones Tecnológicas

| Capa | Recomendación | Justificación |
| :--- | :--- | :--- |
| **Backend Framework** | {ej. Django, FastAPI} | {Por qué esta elección} |
| **Database** | {ej. PostgreSQL} | {Por qué esta elección} |
| **Frontend** | {ej. React} | {Por qué esta elección} |
| **Deployment** | {ej. Docker} | {Por qué esta elección} |

## 3. Modelo BUML (Código)

```buml
// Escribe aquí las clases en pseudocódigo estilo BUML estructurado o Python BESSER API
// DEBES seguir este micro-lenguaje exacto para que el parser lo pueda leer fácilmente:

class {ClassName1} {
  + {attrName1}: {type}
  + {attrName2}: {type}
  + {methodName}({param}: {type}): {return_type}
}

class {ClassName2} {
  + id: int
}

// Para relaciones usa el siguiente formato: (SourceClass -> TargetClass: Tipo [multiplicidad])
rel {ClassName1} -> {ClassName2}: Bidirectional [1..*]
rel {ClassName2} -> {ClassName3}: Composition [1..1]
```

## 4. Trazabilidad de Requisitos

| Clase | Derivada del REQ | Justificación |
| :--- | :--- | :--- |
| {ClassName1} | REQ-001, REQ-002 | {Por qué se necesita} |

## 5. Decisiones de Diseño

| Decisión | Elección | Justificación |
| :--- | :--- | :--- |
| {Tema} | {Elección} | {Por qué se eligió} |

## RULES / REGLAS:
1. Toda clase DEBE rastrearse a al menos un REQ.
2. Todo REQ DEBE estar cubierto por una clase.
3. El código bajo ```buml DEBE usar estrictamente el formato `class Nombre { ... }` y `rel Source -> Target: Type [mult]`.
4. El idioma de todo el documento es **Español**, incluyendo justificaciones, pero mantén nombres PascalCase para clases.
5. Tipos permitidos: str, int, float, bool, date, datetime, any.
6. NO agregues cercas ocultas adicionales de markdown alrededor del documento principal.
"""


class DesignAgent:
    """Generates a BUML class diagram design document from requirements."""

    def __init__(self, client: GeminiClient):
        self.client = client

    def generate(self, requirements_content: str, brief_content: str, project_name: str) -> str:
        """Generate design.md from requirements.

        Args:
            requirements_content: Full text of requirements.md.
            brief_content: Full text of brief.md for additional context.
            project_name: The project name.

        Returns:
            The design.md content.
        """
        prompt = (
            f"Based on the following requirements and brief, generate the design.md document "
            f"with a complete BUML class diagram.\n\n"
            f"--- BEGIN REQUIREMENTS ---\n{requirements_content}\n--- END REQUIREMENTS ---\n\n"
            f"--- BEGIN BRIEF ---\n{brief_content}\n--- END BRIEF ---\n\n"
            f"Project Name: {project_name}\n\n"
            f"Generate a comprehensive class diagram that covers ALL requirements. "
            f"Include proper attributes, methods, relationships, and ensure full traceability. "
            f"The design must be production-quality — think about proper normalization, "
            f"separation of concerns, and extensibility."
        )

        logger.info("[DesignAgent] Generating design.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=DESIGN_SYSTEM_PROMPT,
            temperature=0.5,
        )

        logger.info("[DesignAgent] Generated design.md successfully.")
        return content

    def update(
        self,
        current_design: str,
        change_description: str,
        requirements_content: str,
    ) -> str:
        """Update design.md based on a change from vibe modeling.

        Args:
            current_design: Current design.md content.
            change_description: What changed and why.
            requirements_content: Current requirements.md for context.

        Returns:
            Updated design.md content.
        """
        prompt = (
            f"You have the current design document and a change request. "
            f"Update the design document to reflect the change while maintaining "
            f"full traceability to requirements.\n\n"
            f"--- CURRENT DESIGN ---\n{current_design}\n--- END ---\n\n"
            f"--- REQUIREMENTS (context) ---\n{requirements_content}\n--- END ---\n\n"
            f"--- CHANGE REQUEST ---\n{change_description}\n--- END ---\n\n"
            f"Update rules:\n"
            f"1. If a new class is needed, add it with proper attributes and relationships.\n"
            f"2. If classes are modified, update their attributes/methods.\n"
            f"3. If classes are removed, remove them and their relationships.\n"
            f"4. ALWAYS update the Class-Requirement Traceability table.\n"
            f"5. Keep class names consistent with the existing design.\n"
            f"6. Output the COMPLETE updated design.md document."
        )

        logger.info("[DesignAgent] Updating design.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=DESIGN_SYSTEM_PROMPT,
            temperature=0.4,
        )
        return content
