"""
SDD Pipeline Orchestrator — Manages the end-to-end CC-SDD pipeline.

Coordinates the sequential execution of agents (Brief → Requirements → Design → Traceability)
and handles Vibe Modeling interactions for iterative refinement.
"""

import logging
from typing import Any, Callable, Optional

from .agents.gemini_client import GeminiClient
from .agents.brief_agent import BriefAgent
from .agents.requirements_agent import RequirementsAgent
from .agents.design_agent import DesignAgent
from .agents.traceability_agent import TraceabilityAgent
from .agents.vibe_agent import VibeAgent
from .parsers.buml_to_canvas import parse_design_to_canvas

logger = logging.getLogger(__name__)

# Pipeline phase constants
PHASE_BRIEF = "brief"
PHASE_REQUIREMENTS = "requirements"
PHASE_DESIGN = "design"
PHASE_TRACEABILITY = "traceability"
PHASE_COMPLETE = "complete"


class SDDProject:
    """In-memory representation of an SDD project with all generated artifacts."""

    def __init__(self):
        self.name: str = ""
        self.idea: str = ""
        self.brief: str = ""
        self.requirements: str = ""
        self.design: str = ""
        self.traceability: str = ""
        self.canvas_json: dict = {}
        self.current_phase: str = ""
        self.change_history: list[dict] = []

    def get_files(self) -> dict[str, str]:
        """Return all generated files as a dict of filename → content."""
        files = {}
        if self.brief:
            files["brief.md"] = self.brief
        if self.requirements:
            files["requirements.md"] = self.requirements
        if self.design:
            files["design.md"] = self.design
        if self.traceability:
            files["traceability.md"] = self.traceability
        return files


class SDDPipeline:
    """Orchestrates the CC-SDD pipeline from idea to design with traceability."""

    def __init__(self, api_key: str):
        self.client = GeminiClient(api_key)
        self.brief_agent = BriefAgent(self.client)
        self.requirements_agent = RequirementsAgent(self.client)
        self.design_agent = DesignAgent(self.client)
        self.traceability_agent = TraceabilityAgent(self.client)
        self.vibe_agent = VibeAgent(self.client)
        self.projects: dict[str, SDDProject] = {}

    async def run_pipeline(
        self,
        idea: str,
        on_status: Callable[[str, str, str], Any],
        on_file: Callable[[str, str], Any],
        on_canvas: Callable[[dict], Any],
        on_message: Callable[[str, str], Any],
    ) -> SDDProject:
        """Run the full SDD pipeline from a raw idea.

        Args:
            idea: The user's raw idea/description.
            on_status: Callback(phase, status, message) for pipeline status updates.
            on_file: Callback(filename, content) when a file is generated/updated.
            on_canvas: Callback(canvas_json) when the BUML diagram is ready.
            on_message: Callback(phase, message) for agent chat messages.

        Returns:
            The completed SDDProject.
        """
        project = SDDProject()
        project.idea = idea

        # ─── Phase 1: Brief ─────────────────────────────────────────────
        await on_status(PHASE_BRIEF, "running", "Analyzing your idea and generating project brief...")
        await on_message(PHASE_BRIEF, "🔍 Analyzing your idea and creating a structured brief...")

        try:
            project_name, brief_content = self.brief_agent.generate(idea)
            project.name = project_name
            project.brief = brief_content
            project.current_phase = PHASE_BRIEF

            await on_file("brief.md", brief_content)
            await on_status(PHASE_BRIEF, "completed", f"Brief generated for: {project_name}")
            await on_message(PHASE_BRIEF, f"✅ Brief created for **{project_name}**")
        except Exception as e:
            logger.error(f"[Pipeline] Brief generation failed: {e}", exc_info=True)
            await on_status(PHASE_BRIEF, "error", str(e))
            await on_message(PHASE_BRIEF, f"❌ Error generating brief: {e}")
            raise

        # ─── Phase 2: Requirements ──────────────────────────────────────
        await on_status(PHASE_REQUIREMENTS, "running", "Deriving business rules and requirements...")
        await on_message(PHASE_REQUIREMENTS, "📋 Extracting business rules and writing requirements with EARS syntax...")

        try:
            requirements_content = self.requirements_agent.generate(
                project.brief, project.name
            )
            project.requirements = requirements_content
            project.current_phase = PHASE_REQUIREMENTS

            await on_file("requirements.md", requirements_content)
            await on_status(PHASE_REQUIREMENTS, "completed", "Requirements document generated")
            await on_message(PHASE_REQUIREMENTS, "✅ Requirements & traceability matrix created")
        except Exception as e:
            logger.error(f"[Pipeline] Requirements generation failed: {e}", exc_info=True)
            await on_status(PHASE_REQUIREMENTS, "error", str(e))
            await on_message(PHASE_REQUIREMENTS, f"❌ Error generating requirements: {e}")
            raise

        # ─── Phase 3: Design (BUML) ─────────────────────────────────────
        await on_status(PHASE_DESIGN, "running", "Designing BUML class diagram from requirements...")
        await on_message(PHASE_DESIGN, "🏗️ Designing BUML class diagram and technology stack...")

        try:
            design_content = self.design_agent.generate(
                project.requirements, project.brief, project.name
            )
            project.design = design_content
            project.current_phase = PHASE_DESIGN

            await on_file("design.md", design_content)

            # Parse BUML to canvas JSON
            canvas_json = parse_design_to_canvas(design_content)
            project.canvas_json = canvas_json

            await on_canvas(canvas_json)
            await on_status(PHASE_DESIGN, "completed", "BUML class diagram generated")
            await on_message(PHASE_DESIGN, "✅ BUML class diagram designed and exported to canvas")
        except Exception as e:
            logger.error(f"[Pipeline] Design generation failed: {e}", exc_info=True)
            await on_status(PHASE_DESIGN, "error", str(e))
            await on_message(PHASE_DESIGN, f"❌ Error generating design: {e}")
            raise

        # ─── Phase 4: Traceability ──────────────────────────────────────
        await on_status(PHASE_TRACEABILITY, "running", "Building traceability matrix...")
        await on_message(PHASE_TRACEABILITY, "🔗 Building full bidirectional traceability matrix...")

        try:
            traceability_content = self.traceability_agent.generate(
                project.requirements, project.design, project.name
            )
            project.traceability = traceability_content
            project.current_phase = PHASE_COMPLETE

            await on_file("traceability.md", traceability_content)
            await on_status(PHASE_TRACEABILITY, "completed", "Traceability matrix generated")
            await on_message(PHASE_TRACEABILITY, "✅ Traceability matrix complete — all elements mapped")
        except Exception as e:
            logger.error(f"[Pipeline] Traceability generation failed: {e}", exc_info=True)
            await on_status(PHASE_TRACEABILITY, "error", str(e))
            await on_message(PHASE_TRACEABILITY, f"❌ Error generating traceability: {e}")
            raise

        # ─── Pipeline Complete ───────────────────────────────────────────
        await on_status(PHASE_COMPLETE, "completed", "SDD pipeline complete!")
        await on_message(
            PHASE_COMPLETE,
            f"🎉 **Pipeline complete!** Project **{project.name}** is ready.\n\n"
            f"Generated artifacts:\n"
            f"- 📄 `brief.md` — Project brief\n"
            f"- 📋 `requirements.md` — Business rules & requirements\n"
            f"- 🏗️ `design.md` — BUML class diagram\n"
            f"- 🔗 `traceability.md` — Full traceability matrix\n\n"
            f"You can now use **Vibe Modeling** to modify the design through natural language!"
        )

        # Store the project
        self.projects[project.name] = project
        return project

    async def handle_vibe_message(
        self,
        project: SDDProject,
        instruction: str,
        on_file: Callable[[str, str], Any],
        on_canvas: Callable[[dict], Any],
        on_message: Callable[[str, str], Any],
    ) -> None:
        """Handle a Vibe Modeling instruction — update design, requirements, and traceability.

        Args:
            project: The active SDDProject.
            instruction: User's natural language instruction.
            on_file: Callback(filename, content) when files are updated.
            on_canvas: Callback(canvas_json) when diagram is updated.
            on_message: Callback(phase, message) for chat responses.
        """
        await on_message("vibe", f"🔄 Processing: *{instruction}*")

        try:
            # Step 1: Analyze the instruction
            analysis = self.vibe_agent.analyze_instruction(
                instruction, project.requirements, project.design
            )

            chat_response = analysis.get("chat_response", "Changes applied.")
            change_type = analysis.get("change_type", "both")

            # Step 2: Update design if needed
            if change_type in ("design_only", "both"):
                await on_message("vibe", "🏗️ Updating design...")
                design_changes = analysis.get("design_changes", instruction)
                new_design = self.design_agent.update(
                    project.design, design_changes, project.requirements
                )
                project.design = new_design
                await on_file("design.md", new_design)

                # Re-parse canvas
                canvas_json = parse_design_to_canvas(new_design)
                project.canvas_json = canvas_json
                await on_canvas(canvas_json)

            # Step 3: Update requirements if needed
            if change_type in ("requirements_only", "both"):
                await on_message("vibe", "📋 Updating requirements...")
                req_changes = analysis.get("requirements_changes", instruction)
                new_requirements = self.requirements_agent.update(
                    project.requirements, req_changes, project.brief
                )
                project.requirements = new_requirements
                await on_file("requirements.md", new_requirements)

            # Step 4: Always update traceability
            await on_message("vibe", "🔗 Updating traceability...")
            new_traceability = self.traceability_agent.update(
                project.traceability,
                analysis.get("summary", instruction),
                project.requirements,
                project.design,
            )
            project.traceability = new_traceability
            await on_file("traceability.md", new_traceability)

            # Record change
            project.change_history.append({
                "instruction": instruction,
                "analysis": analysis,
            })

            await on_message("vibe", f"✅ {chat_response}")

        except Exception as e:
            logger.error(f"[Pipeline] Vibe modeling error: {e}", exc_info=True)
            await on_message("vibe", f"❌ Error processing instruction: {e}")
