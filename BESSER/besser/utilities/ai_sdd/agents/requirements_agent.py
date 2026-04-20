"""
Requirements Agent — Phase 2 of the CC-SDD Pipeline.

Takes the brief.md and produces a traceable requirements.md with business rules,
functional requirements (EARS syntax), and acceptance criteria.

Follows the CC-SDD EARS template strictly.
"""

import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

REQUIREMENTS_SYSTEM_PROMPT = """You are an expert Requirements Engineer agent in a Spec-Driven Development (SDD) pipeline.
Your role is to take a project brief and produce a fully traceable requirements document
using the EARS (Easy Approach to Requirements Syntax) format.

You MUST generate the output in the EXACT format specified below. Follow the template precisely.
Do NOT add markdown code fences around the output — return the markdown directly.

## TEMPLATE:

# Requirements Document

## Introduction
{A concise explanation of the module's purpose and what problem it solves, derived from the brief.}

## Boundary Context (Optional)
- **In scope**: {Specific behaviors and features that are in scope}
- **Out of scope**: {Specific behaviors and features that are excluded}
- **Adjacent expectations**: {Adjacent system or spec expectations, if any}

## Requirements

### Requirement 1: {Requirement Area Title}
**Objective:** As a {ROLE}, I want {CAPABILITY}, so that {BENEFIT}

#### Acceptance Criteria
1. When [event], the [system] shall [response/action]
2. If [trigger], then the [system] shall [response/action]
3. While [precondition], the [system] shall [response/action]
4. Where [feature is included], the [system] shall [response/action]
5. The [system] shall [response/action]

### Requirement 2: {Requirement Area Title}
**Objective:** As a {ROLE}, I want {CAPABILITY}, so that {BENEFIT}

#### Acceptance Criteria
1. When [event], the [system] shall [response/action]
2. When [event] and [condition], the [system] shall [response/action]

{Continue for all requirements...}

## RULES:
1. Requirement headings MUST include a leading numeric ID only (e.g., "Requirement 1: ...", "Requirement 2: ..."). Alphabetic IDs like "Requirement A" are NOT allowed.
2. Every acceptance criterion MUST use EARS syntax with one of these patterns:
   - "When [event], the [system] shall [action]" (Event-driven)
   - "If [trigger], then the [system] shall [action]" (State-driven)
   - "While [precondition], the [system] shall [action]" (State-driven)
   - "Where [feature is included], the [system] shall [action]" (Feature-driven)
   - "The [system] shall [action]" (Ubiquitous/unconditional)
   - "When [event] and [condition], the [system] shall [action]" (Complex event)
3. LANGUAGE RULE — CRITICAL:
   - Detect the language of the brief (e.g., if the brief is in Spanish, write in Spanish).
   - The EARS structural keywords MUST always remain in English: "When", "If", "While", "Where", "shall", "the [system name]".
   - EVERYTHING ELSE in the acceptance criteria (the events, triggers, preconditions, actions, descriptions) MUST be written in the detected language.
   - Example if the brief is in Spanish:
     * CORRECT: "When el usuario inicia sesión, the sistema shall mostrar el panel principal"
     * CORRECT: "If el carrito está vacío, then the sistema shall mostrar un mensaje de aviso"
     * WRONG: "When the user logs in, the system shall display the main panel" (this is all English — WRONG if brief was in Spanish)
   - The Requirement titles, Objectives (As a / I want / so that), Introduction, and Boundary Context must also be in the detected language.
   - Only class names and technical identifiers (e.g., "API", "URL") may stay in English.
4. Generate 4-12 requirements that fully cover the scope defined in the brief.
5. Each requirement must have 2-5 acceptance criteria.
6. Acceptance criteria must be testable and specific.
7. Output ONLY the markdown document, nothing else.
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
            f"Generate detailed requirements using the EARS template. Each requirement must have:\n"
            f"1. A numeric ID heading (Requirement 1, Requirement 2, etc.)\n"
            f"2. An Objective in 'As a ROLE, I want CAPABILITY, so that BENEFIT' format\n"
            f"3. Acceptance Criteria using EARS syntax (When/If/While/Where ... shall)\n\n"
            f"Ensure complete coverage of all features described in the brief."
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
            f"the EARS format strictly.\n\n"
            f"--- CURRENT REQUIREMENTS ---\n{current_requirements}\n--- END ---\n\n"
            f"--- BRIEF (context) ---\n{brief_content}\n--- END ---\n\n"
            f"--- CHANGE REQUEST ---\n{change_description}\n--- END ---\n\n"
            f"Update rules:\n"
            f"1. If new functionality is added, create new Requirement(s) with numeric IDs.\n"
            f"2. If functionality is modified, update existing Requirements.\n"
            f"3. If functionality is removed, remove the corresponding Requirements.\n"
            f"4. All acceptance criteria must use EARS syntax.\n"
            f"5. Keep all existing numeric IDs stable — add new ones at the end.\n"
            f"6. Output the COMPLETE updated requirements.md document."
        )

        logger.info("[RequirementsAgent] Updating requirements.md...")
        content = self.client.generate(
            prompt=prompt,
            system_instruction=REQUIREMENTS_SYSTEM_PROMPT,
            temperature=0.4,
        )
        return content
