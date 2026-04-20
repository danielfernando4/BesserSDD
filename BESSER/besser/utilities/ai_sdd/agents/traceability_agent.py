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

TRACEABILITY_SYSTEM_PROMPT = """You are an expert Traceability & Audit agent in a Spec-Driven Development (SDD) pipeline.
Your role is to generate and maintain a traceability document that ensures full bidirectional mapping
between Business Rules, Requirements, and Design Classes.

You MUST generate the output in the EXACT format specified below. Follow the template precisely.
Do NOT add markdown code fences around the output — return the markdown directly.

## TEMPLATE:

# Traceability Log: {ProjectName}
Last Updated: {Date}

## 1. Change History

| # | Date | Type | Element | From | To | Affected BR/REQ | Agent |
|---|------|------|---------|------|----|-----------------|-------|
| 1 | {date} | CREATED | {element} | — | {new value} | {BR/REQ IDs} | system |

## 2. BR → REQ Coverage Matrix

| Business Rule | Associated Requirements | Coverage Status |
| :--- | :--- | :--- |
| **BR-001** | REQ-001, REQ-002 | ✅ Covered |

## 3. REQ → Design (Class) Coverage Matrix

| Requirement | Associated Classes | Coverage Status |
| :--- | :--- | :--- |
| **REQ-001** | ClassName1, ClassName2 | ✅ Implemented |

## 4. Design (Class) → REQ Reverse Trace

| Class | Derived from Requirements | Trace Status |
| :--- | :--- | :--- |
| **ClassName1** | REQ-001, REQ-003 | ✅ Traced |

## 5. Orphan Analysis

### Orphan Business Rules (BR without REQ)
{List any BRs that don't map to any REQ, or "None — all business rules are covered."}

### Orphan Requirements (REQ without Design Class)
{List any REQs that don't map to any class, or "None — all requirements are implemented."}

### Orphan Classes (Class without REQ)
{List any classes that don't trace to any REQ, or "None — all classes are justified."}

## 6. Coverage Summary

| Metric | Value |
| :--- | :--- |
| Total Business Rules | {N} |
| Total Requirements | {N} |
| Total Design Classes | {N} |
| BR Coverage | {X/N} ({%}) |
| REQ Implementation | {X/N} ({%}) |
| Class Traceability | {X/N} ({%}) |
| Orphan Count | {N} |

## RULES:
1. Parse ALL BRs from requirements.md and ALL classes from design.md.
2. Cross-reference to build complete bidirectional mappings.
3. Identify and flag any orphans (elements without mappings).
4. The change history should record initial creation entries for all elements.
5. Coverage percentages must be accurate.
6. Write everything in English.
7. Output ONLY the markdown document, nothing else.
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
