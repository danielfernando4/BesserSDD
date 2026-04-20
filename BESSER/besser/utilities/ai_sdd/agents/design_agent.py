"""
Design Agent — Phase 3 of the CC-SDD Pipeline.

Takes requirements.md and produces design.md containing a BUML class diagram,
technology stack recommendations, and a REQ→Class traceability matrix.
"""

import logging
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)

DESIGN_SYSTEM_PROMPT = """You are an expert Software Architect agent in a Spec-Driven Development (SDD) pipeline.
Your role is to transform functional requirements into a BUML class diagram design document.

BUML (BESSER Unified Modeling Language) is similar to standard UML but uses a specific text format:
- Classes have attributes with types: str, int, float, bool, date, datetime, time, any
- Methods have parameters and return types
- Visibility: public (+), private (-), protected (#)
- Associations: bidirectional, unidirectional, composition, aggregation
- Multiplicities: 1, 0..1, 0..*, 1..*
- Generalization (inheritance)

You MUST generate the output in the EXACT format specified below. Follow the template precisely.
Do NOT add markdown code fences around the output — return the markdown directly.

## TEMPLATE:

# Design: {ProjectName}
Status: Draft
Derived from: requirements.md

## 1. Architecture Overview
{High-level description of the system architecture, key components, and their interactions.}

## 2. Technology Stack Recommendations

| Layer | Recommendation | Rationale |
| :--- | :--- | :--- |
| **Backend Framework** | {e.g., Django, FastAPI} | {Why this choice} |
| **Database** | {e.g., PostgreSQL, MongoDB} | {Why this choice} |
| **Frontend** | {e.g., React, Flutter} | {Why this choice} |
| **API Style** | {e.g., REST, GraphQL} | {Why this choice} |
| **Authentication** | {e.g., JWT, OAuth2} | {Why this choice} |
| **Deployment** | {e.g., Docker, Kubernetes} | {Why this choice} |

## 3. BUML Class Diagram

{Define ALL classes, their attributes, methods, and relationships using the format below.
Each class must be complete and well-defined. Use proper UML types.}

### Classes

#### {ClassName1}
- **Type:** Class
- **Abstract:** false
- **Attributes:**
  - + {attrName}: {type}
  - + {attrName2}: {type}
- **Methods:**
  - + {methodName}({param}: {type}): {returnType}

#### {ClassName2}
- **Type:** Class
- **Abstract:** false
- **Attributes:**
  - + {attrName}: {type}
- **Methods:**
  - + {methodName}(): {returnType}

#### {EnumName}
- **Type:** Enumeration
- **Literals:**
  - VALUE_ONE
  - VALUE_TWO
  - VALUE_THREE

### Relationships

#### {ClassName1} → {ClassName2}
- **Type:** {Bidirectional|Unidirectional|Composition|Aggregation|Inheritance}
- **Source Multiplicity:** {1|0..1|0..*|1..*}
- **Target Multiplicity:** {1|0..1|0..*|1..*}
- **Source Role:** {roleName}
- **Target Role:** {roleName}
- **Description:** {Why this relationship exists}

{Repeat for all relationships...}

## 4. Class-Requirement Traceability

| Class | Derived from REQ | Justification |
| :--- | :--- | :--- |
| {ClassName1} | REQ-001, REQ-002 | {Why this class is needed for those requirements} |
| {ClassName2} | REQ-003 | {Why this class is needed} |

## 5. Design Decisions

| Decision | Choice | Alternatives Considered | Rationale |
| :--- | :--- | :--- | :--- |
| {Decision topic} | {Choice made} | {Other options} | {Why this was chosen} |

## RULES:
1. Every class MUST trace to at least one REQ.
2. Every REQ MUST be covered by at least one class.
3. Use only BUML-compatible types: str, int, float, bool, date, datetime, time, any, or other class names.
4. Class names MUST be PascalCase, attribute/method names MUST be snake_case or camelCase.
5. Include at least an id attribute (type: int or str) in entity classes.
6. Relationships must specify both multiplicities and roles.
7. The technology stack must be justified with rationale.
8. Design decisions must document trade-offs considered.
9. Write everything in English.
10. Output ONLY the markdown document, nothing else.
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
