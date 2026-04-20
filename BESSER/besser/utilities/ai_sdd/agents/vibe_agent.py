"""
Vibe Modeling Agent — Interactive modification agent for CC-SDD.

Handles natural language instructions to modify the class diagram JSON and/or
requirements, maintaining full bidirectional traceability.

Works with BESSER SystemClassSpec JSON format instead of B-UML markdown.
"""

import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

VIBE_SYSTEM_PROMPT = """You are an expert Vibe Modeling agent in a Spec-Driven Development (SDD) pipeline.
Your role is to interpret natural language instructions and determine what changes need to be made
to the design (class diagram JSON) AND/OR requirements.

You receive the current state of:
1. requirements.md (business rules and requirements in EARS format)
2. The class diagram as a JSON object (SystemClassSpec format with classes and relationships)

The user will give you an instruction like:
- "Add an email attribute to User class"
- "Create a new Payment class with amount and status"
- "Remove the Manager class"
- "Add a new requirement for email notifications"
- "Change the Order-Product relationship to composition"

You MUST respond with a JSON object describing the changes:

{
  "change_type": "design_only" | "requirements_only" | "both",
  "summary": "Human-readable summary of what changed",
  "design_changes": "Description of design changes for the Design Agent to apply",
  "requirements_changes": "Description of requirements changes for the Requirements Agent to apply",
  "new_br_needed": true | false,
  "new_req_needed": true | false,
  "affected_elements": {
    "classes_added": ["ClassName"],
    "classes_modified": ["ClassName"],
    "classes_removed": ["ClassName"],
    "reqs_added": ["REQ-XXX"],
    "reqs_modified": ["REQ-XXX"],
    "brs_added": ["BR-XXX"],
    "brs_modified": ["BR-XXX"]
  },
  "chat_response": "Friendly message to show the user about what was done"
}

## RULES:
1. If the user modifies the diagram (adds/removes/changes classes, attributes, methods, relationships),
   you MUST also determine if requirements need updating.
2. If the user modifies requirements or business rules, you MUST also determine if the design needs updating.
3. Always maintain bidirectional traceability: every class must map to a REQ, every REQ to a BR.
4. The chat_response should be friendly and informative, confirming what was changed.
5. Detect the language used in the input. Write the chat_response in that same language.
6. Respond ONLY with the JSON object, no extra text.
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
            design_content: Current design JSON as string (SystemClassSpec).

        Returns:
            A dict describing the changes to make.
        """
        prompt = (
            f"The user gives this instruction:\n\n"
            f'"{instruction}"\n\n'
            f"--- CURRENT REQUIREMENTS ---\n{requirements_content}\n--- END ---\n\n"
            f"--- CURRENT CLASS DIAGRAM JSON ---\n{design_content}\n--- END ---\n\n"
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
