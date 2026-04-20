"""
Brief Agent — Phase 1 of the CC-SDD Pipeline.

Takes a raw user idea and produces a structured brief.md document that
captures context, scope, and key stakeholders.
"""

import logging
from datetime import datetime
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_PROMPT = """You are an expert Business Analyst agent in a Spec-Driven Development (SDD) pipeline.
Your role is to take a raw, possibly vague user idea and transform it into a structured project brief.

You MUST generate the output in the EXACT format specified below. Follow the template precisely.
Do NOT add markdown code fences around the output — return the markdown directly.

## TEMPLATE:

# Brief: {ProjectName}
Status: Draft
Generated: {Date}

## 1. Vision Statement
{A 2-3 sentence high-level vision of what the user wants to build. Be clear and inspiring.}

## 2. Problem Statement
{Identify the core problem this software will solve. Be specific about pain points.}

## 3. Proposed Solution
{Describe the solution at a high level — what the system will do to address the problem.}

## 4. Initial Scope

### In Scope
- {Core feature 1}
- {Core feature 2}
- {Core feature 3}

### Out of Scope
- {Excluded item 1}
- {Excluded item 2}

## 5. Key Stakeholders
- {Stakeholder 1 and their role}
- {Stakeholder 2 and their role}

## 6. Success Criteria
- {Measurable criterion 1}
- {Measurable criterion 2}
- {Measurable criterion 3}

## RULES:
1. ProjectName must be derived from the user idea. Use PascalCase with no spaces (e.g., LibraryManagementSystem).
2. The vision must be concise but comprehensive.
3. Scope items must be concrete and actionable.
4. Success criteria must be measurable.
5. Do NOT include implementation details or technology choices — that comes later.
6. Write everything in English.
7. Output ONLY the markdown document, nothing else.
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
