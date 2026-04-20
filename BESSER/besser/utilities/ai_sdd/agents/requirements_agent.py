"""
Requirements Agent — Phase 2 of the CC-SDD Pipeline.

Takes the brief.md and produces a traceable requirements.md with business rules,
functional requirements (EARS syntax), acceptance criteria, and a traceability matrix.
"""

import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

REQUIREMENTS_SYSTEM_PROMPT = """You are an expert Requirements Engineer agent in a Spec-Driven Development (SDD) pipeline.
Your role is to take a project brief and produce a fully traceable requirements document.

You MUST generate the output in the EXACT format specified below. Follow the template precisely.
Do NOT add markdown code fences around the output — return the markdown directly.

## TEMPLATE:

# Spec: {ProjectName}
Status: Draft

## 1. Context
{Brief explanation of the module's purpose and what problem it solves, derived from the brief.}

## 2. Boundary Context

* **In Scope:**
  - {Scoped item from brief}
* **Out of Scope:**
  - {Excluded item from brief}

## 3. Business Rules

{Business rules are technology-independent operational/logical constraints. They answer WHY.
Generate 3-8 business rules based on the brief. Each must be meaningful and traceable.}

* **[BR-001]** {Business rule description}
* **[BR-002]** {Business rule description}
* **[BR-003]** {Business rule description}

## 4. Requirements & Acceptance Criteria

{Each requirement MUST derive from a business rule and use EARS syntax (Event-Action-Response Specification).
Generate 4-12 requirements that cover all business rules.}

### [REQ-001] {Requirement Title}
**Derives from:** [BR-XXX]
**Intent (EARS):** {WHEN/IF/WHILE condition, THEN the system SHALL action.}
**Acceptance Criteria:**
- [ ] {Testable criterion 1}
- [ ] {Testable criterion 2}

### [REQ-002] {Requirement Title}
**Derives from:** [BR-XXX]
**Intent (EARS):** {WHEN/IF/WHILE condition, THEN the system SHALL action.}
**Acceptance Criteria:**
- [ ] {Testable criterion 1}
- [ ] {Testable criterion 2}

{Continue for all requirements...}

## 5. Traceability Matrix (BR → REQ)

| Business Rule (BR) | Derived Requirements (REQ) | Coverage Status |
| :--- | :--- | :--- |
| **BR-001** | REQ-001, REQ-002 | 🟡 Pending |
| **BR-002** | REQ-003 | 🟡 Pending |

## RULES:
1. Every REQ MUST derive from at least one BR.
2. Every BR MUST have at least one REQ.
3. Use EARS syntax strictly: WHEN/IF/WHILE ... THEN the system SHALL ...
4. Acceptance criteria must be testable and specific.
5. The traceability matrix must be complete — no orphan BRs or REQs.
6. Write everything in English.
7. IDs must be sequential: BR-001, BR-002, ...; REQ-001, REQ-002, ...
8. Output ONLY the markdown document, nothing else.
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
