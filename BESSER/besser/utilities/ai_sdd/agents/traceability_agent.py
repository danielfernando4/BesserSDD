"""
Traceability Agent — Phase 4 of the CC-SDD Pipeline.

Generates and maintains traceability.md — a comprehensive change log and
cross-reference matrix that ensures bidirectional mapping between
Business Rules ↔ Requirements ↔ Design Classes.
"""

import logging
from datetime import datetime
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

TRACEABILITY_SYSTEM_PROMPT = """Eres un Agente de Trazabilidad y Auditoría experto en un entorno de Spec-Driven Development (SDD).
Tu rol es generar y mantener un documento de trazabilidad que asegure un mapeo bidireccional completo
entre Reglas de Negocio, Requisitos y Clases de Diseño en ESPAÑOL.

Debes generar la salida EXACTAMENTE en el formato especificado a continuación. Tu respuesta debe estar completamente en Español.

## TEMPLATE:

# Registro de Trazabilidad: {ProjectName}
Última actualización: {Date}

## 1. Historial de Cambios

| # | Fecha | Tipo | Elemento | Desde | Hasta | BR/REQ Afectado | Agente |
|---|------|------|---------|------|----|-----------------|-------|
| 1 | {date} | CREADO | {element} | — | {new value} | {BR/REQ IDs} | system |

## 2. Matriz de Cobertura BR → REQ

| Regla de Negocio | Requisitos Asociados | Estado de Cobertura |
| :--- | :--- | :--- |
| **BR-001** | REQ-001, REQ-002 | ✅ Cubierto |

## 3. Matriz de Cobertura REQ → Diseño (Clases)

| Requisito | Clases Asociadas | Estado de Cobertura |
| :--- | :--- | :--- |
| **REQ-001** | ClassName1, ClassName2 | ✅ Implementado |

## 4. Trazabilidad Inversa: Diseño (Clases) → REQ

| Clase | Derivada de Requisitos | Estado de Trazabilidad |
| :--- | :--- | :--- |
| **ClassName1** | REQ-001, REQ-003 | ✅ Trazado |

## 5. Análisis de Huérfanos

### Reglas de Negocio Huérfanas (BR sin REQ)
{Lista cualquier BR que no mapee a ningún REQ, o "Ninguno — todas las reglas están cubiertas."}

### Requisitos Huérfanos (REQ sin Clase de Diseño)
{Lista cualquier REQ que no mapee a ninguna clase, o "Ninguno — todos los requisitos están implementados."}

### Clases Huérfanas (Clase sin REQ)
{Lista cualquier clase que no trace a ningún REQ, o "Ninguno — todas las clases están justificadas."}

## 6. Resumen de Cobertura

| Métrica | Valor |
| :--- | :--- |
| Total Reglas de Negocio | {N} |
| Total Requisitos | {N} |
| Total Clases de Diseño | {N} |
| Cobertura BR | {X/N} ({%}) |
| Implementación REQ | {X/N} ({%}) |
| Trazabilidad de Clases | {X/N} ({%}) |
| Cantidad de Huérfanos | {N} |

## RULES / REGLAS:
1. Extrae TODAS las BR de requirements.md y TODAS las clases de design.md.
2. Referencia de forma cruzada para construir los mapeos bidireccionales completos.
3. Identifica cualquier huérfano (elementos sin mapeo).
4. El historial de cambios debe registrar entradas iniciales de CREADO para todos los elementos.
5. Los porcentajes de cobertura deben ser precisos.
6. Escribe todo tu contenido en **Español**.
7. Genera ÚNICAMENTE el documento markdown, nada más, sin backticks ocultos de markdown.
"""


class TraceabilityAgent:
    """Generates and maintains the traceability.md document."""

    def __init__(self, client: GeminiClient):
        self.client = client

    def generate(
        self,
        requirements_content: str,
        design_content: str,
        project_name: str,
    ) -> str:
        """Generate initial traceability.md from requirements and design documents.

        Args:
            requirements_content: Full text of requirements.md.
            design_content: Full text of design.md.
            project_name: The project name.

        Returns:
            The traceability.md content.
        """
        today = datetime.now().strftime("%Y-%m-%d %H:%M")

        prompt = (
            f"Based on the following requirements and design documents, generate "
            f"the traceability.md document with complete bidirectional mappings.\n\n"
            f"--- BEGIN REQUIREMENTS ---\n{requirements_content}\n--- END REQUIREMENTS ---\n\n"
            f"--- BEGIN DESIGN ---\n{design_content}\n--- END DESIGN ---\n\n"
            f"Project Name: {project_name}\n"
            f"Current Date/Time: {today}\n\n"
            f"Generate the complete traceability document. Ensure:\n"
            f"1. Every BR maps to at least one REQ.\n"
            f"2. Every REQ maps to at least one class.\n"
            f"3. Every class traces back to at least one REQ.\n"
            f"4. Identify and flag any orphans.\n"
            f"5. Include initial CREATED entries in the change history for all elements."
        )

        logger.info("[TraceabilityAgent] Generating traceability.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=TRACEABILITY_SYSTEM_PROMPT,
            temperature=0.3,
        )

        logger.info("[TraceabilityAgent] Generated traceability.md successfully.")
        return content

    def update(
        self,
        current_traceability: str,
        change_description: str,
        requirements_content: str,
        design_content: str,
    ) -> str:
        """Update traceability.md to reflect a change.

        Args:
            current_traceability: Current traceability.md content.
            change_description: What changed and why.
            requirements_content: Updated requirements.md.
            design_content: Updated design.md.

        Returns:
            Updated traceability.md content.
        """
        today = datetime.now().strftime("%Y-%m-%d %H:%M")

        prompt = (
            f"You have the current traceability document. A change has been made to "
            f"the project. Update the traceability document to reflect this change.\n\n"
            f"--- CURRENT TRACEABILITY ---\n{current_traceability}\n--- END ---\n\n"
            f"--- UPDATED REQUIREMENTS ---\n{requirements_content}\n--- END ---\n\n"
            f"--- UPDATED DESIGN ---\n{design_content}\n--- END ---\n\n"
            f"--- CHANGE DESCRIPTION ---\n{change_description}\n--- END ---\n\n"
            f"Current Date/Time: {today}\n\n"
            f"Update rules:\n"
            f"1. ADD new entries to the Change History table (don't replace existing ones).\n"
            f"2. Update all coverage matrices based on current requirements and design.\n"
            f"3. Re-run orphan analysis.\n"
            f"4. Update coverage summary metrics.\n"
            f"5. The change type should be: ADDED, MODIFIED, REMOVED, or UPDATED.\n"
            f"6. Output the COMPLETE updated traceability.md document."
        )

        logger.info("[TraceabilityAgent] Updating traceability.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=TRACEABILITY_SYSTEM_PROMPT,
            temperature=0.3,
        )
        return content
