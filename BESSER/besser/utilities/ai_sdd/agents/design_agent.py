"""
Design Agent — Phase 3 of the CC-SDD Pipeline.

Takes requirements.md and produces a BESSER-compatible JSON class diagram
(SystemClassSpec format) that the frontend can render directly.

The agent does NOT produce B-UML markdown. Instead, it generates structured
JSON that matches the BESSER web editor format, eliminating the need for any
parsing step.
"""

import json
import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

DESIGN_SYSTEM_PROMPT = """You are an expert Software Architect agent in a Spec-Driven Development (SDD) pipeline.
Your role is to transform functional requirements into a class diagram design.

You MUST produce TWO outputs separated by the marker `---JSON_SEPARATOR---`:

**PART 1: Design Document (Markdown)**
A design.md with architecture overview, technology stack, and design decisions.
Do NOT include any class/relationship definitions in this part — those go in Part 2.

**PART 2: Class Diagram JSON**
A JSON object following this EXACT schema (SystemClassSpec):

```json
{
  "systemName": "MySystem",
  "classes": [
    {
      "className": "User",
      "attributes": [
        {"name": "id", "type": "String", "visibility": "public"},
        {"name": "email", "type": "String", "visibility": "private"}
      ],
      "methods": [
        {"name": "login", "returnType": "bool", "visibility": "public", "parameters": []}
      ],
      "isAbstract": false,
      "isEnumeration": false
    }
  ],
  "relationships": [
    {
      "type": "Association",
      "source": "User",
      "target": "Order",
      "sourceMultiplicity": "1",
      "targetMultiplicity": "0..*",
      "name": "places"
    }
  ],
  "constraints": [
    {
      "contextClass": "User",
      "constraint": "context User inv:\\n  self.age >= 18"
    }
  ]
}
```

## JSON Schema Rules:
- **className**: PascalCase, ONE word (e.g., User, Product, Order)
- **attributes**: Each has name (camelCase), type (String, int, float, bool, Date, or PascalCase class/enum name), visibility (public/private/protected)
- **methods**: Each has name (camelCase), returnType, visibility, parameters (list of {name, type})
- **methods**: Generally SKIP methods unless explicitly required. Only include 1-2 core domain methods per class MAX. Never include getters/setters.
- **isEnumeration**: If true, list enum values as attributes with name only (no type needed)
- **relationships.type**: One of: "Association", "Inheritance", "Composition", "Aggregation", "Realization", "Dependency"
- **multiplicities**: "1", "0..1", "0..*", "1..*"
- **constraints**: If applicable, you MUST declare OCL (Object Constraint Language) constraints for business rules (e.g. self.age >= 18). Each has 'contextClass' (string) and 'constraint' (string containing 'context [class] inv: ...').
- Every class MUST have at least an 'id' attribute
- Every requirement MUST map to at least one class
- Relationships are CRITICAL — always include meaningful connections

## Part 1 Template:

# Design: {ProjectName}
Status: Draft
Derived from: requirements.md

## 1. Architecture Overview
{High-level description}

## 2. Technology Stack Recommendations

| Layer | Recommendation | Rationale |
| :--- | :--- | :--- |
| **Backend** | ... | ... |
| **Database** | ... | ... |
| **Frontend** | ... | ... |

## 3. Class-Requirement Traceability

| Class | Derived from REQ | Justification |
| :--- | :--- | :--- |
| User | REQ-001, REQ-002 | ... |

## 4. Design Decisions

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| ... | ... | ... |

## RULES:
1. Part 1 is Markdown only — NO class definitions, NO JSON.
2. Part 2 is JSON only — valid, parseable JSON matching the schema above.
3. Separate them EXACTLY with: ---JSON_SEPARATOR---
4. Every class MUST trace to at least one REQ.
5. Every REQ MUST be covered by at least one class.
6. Use only BESSER-compatible attribute types: String, int, float, bool, Date, or PascalCase class/enum names.
7. Include proper multiplicities on ALL relationships.
8. Detect the language of the provided requirements. Write Part 1 in that same language.
9. Class names, attribute names, and method names are ALWAYS in English (camelCase/PascalCase).
10. Output ONLY Part 1 + separator + Part 2, nothing else.
"""


class DesignAgent:
    """Generates a BESSER-compatible JSON class diagram from requirements."""

    def __init__(self, client: GeminiClient):
        self.client = client

    def generate(
        self, requirements_content: str, brief_content: str, project_name: str
    ) -> tuple[str, dict]:
        """Generate design.md + SystemClassSpec JSON from requirements.

        Args:
            requirements_content: Full text of requirements.md.
            brief_content: Full text of brief.md for additional context.
            project_name: The project name.

        Returns:
            Tuple of (design_markdown, system_spec_json).
        """
        prompt = (
            f"Based on the following requirements and brief, generate the design document "
            f"(Part 1 — Markdown) and the class diagram (Part 2 — JSON).\n\n"
            f"--- BEGIN REQUIREMENTS ---\n{requirements_content}\n--- END REQUIREMENTS ---\n\n"
            f"--- BEGIN BRIEF ---\n{brief_content}\n--- END BRIEF ---\n\n"
            f"Project Name: {project_name}\n\n"
            f"Generate a comprehensive class diagram that covers ALL requirements. "
            f"Include proper attributes, methods, relationships, and ensure full traceability. "
            f"The design must be production-quality — think about proper normalization, "
            f"separation of concerns, and extensibility.\n\n"
            f"Remember: output Part 1 (Markdown), then ---JSON_SEPARATOR---, then Part 2 (JSON)."
        )

        logger.info("[DesignAgent] Generating design + JSON...")
        raw = self.client.generate(
            prompt=prompt,
            system_instruction=DESIGN_SYSTEM_PROMPT,
            temperature=0.5,
        )

        design_md, system_spec = self._parse_response(raw, project_name)
        logger.info(
            f"[DesignAgent] Generated {len(system_spec.get('classes', []))} classes, "
            f"{len(system_spec.get('relationships', []))} relationships."
        )
        return design_md, system_spec

    def update(
        self,
        current_design_md: str,
        current_spec: dict,
        change_description: str,
        requirements_content: str,
    ) -> tuple[str, dict]:
        """Update design.md + JSON based on a change.

        Args:
            current_design_md: Current design.md content.
            current_spec: Current SystemClassSpec JSON.
            change_description: What changed and why.
            requirements_content: Current requirements.md for context.

        Returns:
            Tuple of (updated_design_markdown, updated_system_spec_json).
        """
        current_json_str = json.dumps(current_spec, indent=2, ensure_ascii=False)

        prompt = (
            f"You have the current design and a change request. "
            f"Update BOTH the design document (Part 1) and the class diagram JSON (Part 2).\n\n"
            f"--- CURRENT DESIGN MARKDOWN ---\n{current_design_md}\n--- END ---\n\n"
            f"--- CURRENT CLASS DIAGRAM JSON ---\n{current_json_str}\n--- END ---\n\n"
            f"--- REQUIREMENTS (context) ---\n{requirements_content}\n--- END ---\n\n"
            f"--- CHANGE REQUEST ---\n{change_description}\n--- END ---\n\n"
            f"Update rules:\n"
            f"1. If a new class is needed, add it with proper attributes and relationships.\n"
            f"2. If classes are modified, update their attributes/methods.\n"
            f"3. If classes are removed, remove them and their relationships.\n"
            f"4. ALWAYS update the Class-Requirement Traceability table in Part 1.\n"
            f"5. Keep class names consistent with the existing design.\n"
            f"6. Output the COMPLETE updated Part 1 + ---JSON_SEPARATOR--- + Part 2."
        )

        logger.info("[DesignAgent] Updating design + JSON...")
        raw = self.client.generate(
            prompt=prompt,
            system_instruction=DESIGN_SYSTEM_PROMPT,
            temperature=0.4,
        )
        return self._parse_response(raw, "")

    def update_from_diagram(
        self,
        new_spec: dict,
        current_design_md: str,
        requirements_content: str,
    ) -> str:
        """Update design.md to reflect manual diagram changes.

        When the user edits the diagram directly, this regenerates the
        design markdown (architecture + traceability) to match.

        Args:
            new_spec: The new SystemClassSpec JSON from the frontend.
            current_design_md: Current design.md content.
            requirements_content: Current requirements.md for context.

        Returns:
            Updated design.md markdown (Part 1 only, no JSON).
        """
        spec_str = json.dumps(new_spec, indent=2, ensure_ascii=False)

        prompt = (
            f"The user manually edited the class diagram. Update the design document "
            f"(Part 1 ONLY - Markdown) to reflect the new diagram state.\n\n"
            f"--- UPDATED CLASS DIAGRAM JSON ---\n{spec_str}\n--- END ---\n\n"
            f"--- CURRENT DESIGN MARKDOWN ---\n{current_design_md}\n--- END ---\n\n"
            f"--- REQUIREMENTS ---\n{requirements_content}\n--- END ---\n\n"
            f"Update the architecture overview, traceability table, and design decisions "
            f"to match the new diagram. Output ONLY the updated Markdown, no JSON."
        )

        logger.info("[DesignAgent] Updating design.md from diagram changes...")
        return self.client.generate(
            prompt=prompt,
            system_instruction=DESIGN_SYSTEM_PROMPT,
            temperature=0.3,
        )

    def _parse_response(self, raw: str, fallback_name: str) -> tuple[str, dict]:
        """Parse the LLM response into (design_md, system_spec_json)."""
        separator = "---JSON_SEPARATOR---"

        if separator in raw:
            parts = raw.split(separator, 1)
            design_md = parts[0].strip()
            json_part = parts[1].strip()
        else:
            # Fallback: try to find JSON block at the end
            logger.warning("[DesignAgent] No separator found, attempting fallback parse.")
            json_start = raw.rfind("{")
            if json_start > 0:
                design_md = raw[:json_start].strip()
                json_part = raw[json_start:]
            else:
                design_md = raw
                json_part = ""

        # Parse the JSON
        system_spec = self._extract_json(json_part, fallback_name)

        return design_md, system_spec

    def _extract_json(self, text: str, fallback_name: str) -> dict:
        """Extract and validate SystemClassSpec JSON from text."""
        if not text.strip():
            return {"systemName": fallback_name or "System", "classes": [], "relationships": []}

        cleaned = text.strip()

        # Remove markdown code fences if present
        if "```json" in cleaned:
            start = cleaned.index("```json") + 7
            end = cleaned.index("```", start) if "```" in cleaned[start:] else len(cleaned)
            cleaned = cleaned[start:end].strip()
        elif "```" in cleaned:
            start = cleaned.index("```") + 3
            end = cleaned.index("```", start) if "```" in cleaned[start:] else len(cleaned)
            cleaned = cleaned[start:end].strip()

        # Find the JSON object
        brace_start = cleaned.find("{")
        brace_end = cleaned.rfind("}")

        if brace_start == -1 or brace_end == -1:
            logger.error("[DesignAgent] No JSON found in response.")
            return {"systemName": fallback_name or "System", "classes": [], "relationships": []}

        json_str = cleaned[brace_start : brace_end + 1]

        try:
            spec = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"[DesignAgent] JSON parse error: {e}")
            return {"systemName": fallback_name or "System", "classes": [], "relationships": []}

        # Validate required keys
        spec.setdefault("systemName", fallback_name or "System")
        spec.setdefault("classes", [])
        spec.setdefault("relationships", [])

        # Validate each class
        for cls in spec["classes"]:
            cls.setdefault("className", "UnnamedClass")
            cls.setdefault("attributes", [])
            cls.setdefault("methods", [])
            cls.setdefault("isAbstract", False)
            cls.setdefault("isEnumeration", False)
            # Validate attributes
            for attr in cls["attributes"]:
                attr.setdefault("name", "unnamed")
                attr.setdefault("visibility", "public")
                if not cls["isEnumeration"]:
                    attr.setdefault("type", "String")

        # Validate relationships
        valid_types = {"Association", "Inheritance", "Composition", "Aggregation", "Realization", "Dependency"}
        class_names = {c["className"] for c in spec["classes"]}
        valid_rels = []
        for rel in spec["relationships"]:
            rel.setdefault("type", "Association")
            rel.setdefault("sourceMultiplicity", "1")
            rel.setdefault("targetMultiplicity", "*")
            if rel.get("source") in class_names and rel.get("target") in class_names:
                if rel["type"] not in valid_types:
                    rel["type"] = "Association"
                valid_rels.append(rel)
        spec["relationships"] = valid_rels

        return spec
