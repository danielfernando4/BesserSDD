"""
Traceability Agent — Phase 4 of the CC-SDD Pipeline.

Generates and maintains traceability.md — a comprehensive cross-reference
matrix that ensures bidirectional mapping between
Requirements ↔ Design Classes ↔ Acceptance Criteria.

Also provides reconciliation: when the diagram changes manually, this
agent updates the requirements to match.
"""

import logging
from datetime import datetime
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

TRACEABILITY_SYSTEM_PROMPT = """You are an expert Traceability & Audit agent in a Spec-Driven Development (SDD) pipeline.
Your role is to generate and maintain a traceability document that ensures full bidirectional mapping
between Requirements (numbered, EARS format) and Design Classes.

You MUST generate the output in the EXACT format specified below. Follow the template precisely.
Do NOT add markdown code fences around the output — return the markdown directly.

## TEMPLATE:

# Traceability Matrix: {ProjectName}
Last Updated: {Date}

## 1. Change History

| # | Date | Type | Element | Description | Affected Requirements | Agent |
|---|------|------|---------|-------------|-----------------------|-------|
| 1 | {date} | CREATED | {element} | {description} | Req 1, Req 3 | system |

## 2. Requirement → Design (Class) Coverage Matrix

| Requirement | Objective | Associated Classes | Coverage Status |
| :--- | :--- | :--- | :--- |
| **Requirement 1** | {Short objective} | ClassName1, ClassName2 | ✅ Implemented |
| **Requirement 2** | {Short objective} | ClassName3 | ✅ Implemented |

## 3. Design (Class) → Requirement Reverse Trace

| Class | Attributes | Derived from Requirements | Trace Status |
| :--- | :--- | :--- | :--- |
| **ClassName1** | attr1, attr2 | Requirement 1, Requirement 3 | ✅ Traced |

## 4. Acceptance Criteria Coverage

| Requirement | Total Criteria | Criteria Traceable to Design | Coverage |
| :--- | :--- | :--- | :--- |
| **Requirement 1** | 5 | 5 | 100% |
| **Requirement 2** | 3 | 3 | 100% |

## 5. Orphan Analysis

### Orphan Requirements (without Design Class)
{List any requirements that don't map to any class, or "None — all requirements are implemented."}

### Orphan Classes (without Requirement)
{List any classes that don't trace to any requirement, or "None — all classes are justified."}

## 6. Coverage Summary

| Metric | Value |
| :--- | :--- |
| Total Requirements | {N} |
| Total Design Classes | {N} |
| Requirement Implementation | {X/N} ({%}) |
| Class Traceability | {X/N} ({%}) |
| Orphan Count | {N} |

## RULES:
1. Parse ALL numbered requirements from requirements.md and ALL classes from the design JSON.
2. Cross-reference to build complete bidirectional mappings.
3. Identify and flag any orphans (elements without mappings).
4. The change history should record initial creation entries for all elements.
5. Coverage percentages must be accurate.
6. Detect the language used in the requirements. Write the document in that same language.
7. Requirements use numbered IDs (Requirement 1, Requirement 2, ...), NOT BR/REQ codes.
8. Output ONLY the markdown document, nothing else.
"""

RECONCILE_SYSTEM_PROMPT = """You are an expert Requirements Reconciliation agent.
Your role is to update requirements to reflect manual diagram changes, maintaining
full traceability with the EARS (Easy Approach to Requirements Syntax) format.

When diagram classes/attributes/relationships change, you must:
1. Add new Requirements for new classes/concepts if needed.
2. Modify existing Requirements if class attributes changed.
3. Remove Requirements that correspond to deleted classes/features.
4. Update all requirement numbering to maintain sequential order.
5. Preserve the original language and EARS format.
6. EARS keywords (When, If, While, Where, shall, the system) must remain in English.
7. All other content follows the language of the existing requirements.

Output the COMPLETE updated requirements.md, not just changes.
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
        """Generate initial traceability.md from requirements and design documents."""
        today = datetime.now().strftime("%Y-%m-%d %H:%M")

        prompt = (
            f"Based on the following requirements and design documents, generate "
            f"the traceability.md document with complete bidirectional mappings.\n\n"
            f"--- BEGIN REQUIREMENTS ---\n{requirements_content}\n--- END REQUIREMENTS ---\n\n"
            f"--- BEGIN DESIGN ---\n{design_content}\n--- END DESIGN ---\n\n"
            f"Project Name: {project_name}\n"
            f"Current Date/Time: {today}\n\n"
            f"Generate the complete traceability document. Ensure:\n"
            f"1. Every requirement maps to at least one class.\n"
            f"2. Every class traces back to at least one requirement.\n"
            f"3. Identify and flag any orphans.\n"
            f"4. Include initial CREATED entries in the change history for all elements."
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
        """Update traceability.md to reflect a change."""
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

    def reconcile_requirements(
        self,
        changes_description: str,
        current_requirements: str,
    ) -> str:
        """Update requirements to reflect manual diagram changes.

        This is the "diagram → requirements" direction of bidirectional
        traceability. When the user edits the class diagram directly,
        this method updates the requirements document to stay in sync.
        """
        prompt = (
            f"The user made manual changes to the class diagram. "
            f"Update the requirements document to reflect these changes.\n\n"
            f"--- DIAGRAM CHANGES ---\n{changes_description}\n--- END ---\n\n"
            f"--- CURRENT REQUIREMENTS ---\n{current_requirements}\n--- END ---\n\n"
            f"Rules:\n"
            f"1. If a new class was added, create corresponding Requirements with EARS acceptance criteria.\n"
            f"2. If attributes were added to a class, add acceptance criteria for the new capabilities.\n"
            f"3. If a class was removed, remove its corresponding Requirements.\n"
            f"4. If relationships changed, update Requirements to reflect new interactions.\n"
            f"5. Maintain EARS format for all acceptance criteria.\n"
            f"6. Keep existing numbering stable — only add new requirements at the end.\n"
            f"7. Output the COMPLETE updated requirements.md document."
        )

        logger.info("[TraceabilityAgent] Reconciling requirements from diagram changes...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=RECONCILE_SYSTEM_PROMPT,
            temperature=0.3,
        )
        return content
