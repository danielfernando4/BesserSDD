"""
SDD Pipeline — Agent-Driven Phase Orchestrator.

Manages the CC-SDD workflow where the user interacts via chat.
The pipeline runs phases sequentially, pausing after each one.
When the user sends a message, the agent determines the intent:
  - "advance" → move to next phase
  - "iterate" → refine current phase with the user's feedback
  - "vibe" → modify design/requirements (only after pipeline completes)

Flow: Brief → Requirements → Design → Traceability → Complete
"""

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .agents.gemini_client import GeminiClient
from .agents.brief_agent import BriefAgent
from .agents.requirements_agent import RequirementsAgent
from .agents.design_agent import DesignAgent
from .agents.traceability_agent import TraceabilityAgent
from .agents.vibe_agent import VibeAgent
from .layout import apply_layout

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    BRIEF = "brief"
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    TRACEABILITY = "traceability"
    COMPLETE = "complete"


# Phase execution order
_PHASE_ORDER = [Phase.BRIEF, Phase.REQUIREMENTS, Phase.DESIGN, Phase.TRACEABILITY]

# System prompt for routing user messages during the pipeline
_ROUTER_PROMPT = """You are a routing agent. Analyze the user's message and determine their intent.
The pipeline is currently paused after generating the "{phase}" phase.

Possible intents:
1. "advance" — the user is satisfied and wants to proceed to the next phase.
   Examples: "ok", "bien", "looks good", "continue", "next", "proceed", "perfecto", "lgtm", "sí", "yes", "dale", "avanza", "siguiente", "approve"
2. "iterate" — the user wants to refine/change the current phase output.
   Examples: "add more detail about X", "change Y to Z", "remove the section about W", "I don't like the part about..."

Respond with ONLY a JSON object:
{{"intent": "advance"}} or {{"intent": "iterate", "feedback": "cleaned up version of the user's feedback"}}

User message: "{message}"
"""


class SDDProject:
    """Holds all generated artifacts for a single SDD project."""

    def __init__(self, idea: str, project_name: str = ""):
        self.idea = idea
        self.project_name = project_name

        # Generated artifacts
        self.brief: str = ""
        self.requirements: str = ""
        self.design_md: str = ""
        self.canvas_json: dict = {}         # SystemClassSpec with positions
        self.traceability: str = ""

        # State
        self.current_phase: Phase = Phase.BRIEF
        self.phase_approved: Dict[Phase, bool] = {}


class SDDPipeline:
    """Agent-driven SDD pipeline with bidirectional traceability."""

    def __init__(self, api_key: str, send_message: Callable, output_dir: Optional[str] = None):
        self.client = GeminiClient(api_key)
        self.send = send_message
        self.output_dir = output_dir

        # Agents
        self.brief_agent = BriefAgent(self.client)
        self.requirements_agent = RequirementsAgent(self.client)
        self.design_agent = DesignAgent(self.client)
        self.traceability_agent = TraceabilityAgent(self.client)
        self.vibe_agent = VibeAgent(self.client)

        self.project: Optional[SDDProject] = None

        # Ensure output directory exists
        if self.output_dir:
            try:
                Path(self.output_dir).mkdir(parents=True, exist_ok=True)
                logger.info(f"[Pipeline] Output directory: {self.output_dir}")
            except Exception as e:
                logger.warning(f"[Pipeline] Could not create output dir: {e}")
                self.output_dir = None

    # ── Pipeline Start ─────────────────────────────────────────────────

    async def start_pipeline(self, idea: str) -> None:
        """Start the pipeline. Generates brief and pauses for user input."""
        self.project = SDDProject(idea=idea)
        logger.info(f"[Pipeline] Starting with idea: {idea[:100]}...")
        await self._run_phase(Phase.BRIEF)

    # ── User Message Handler (Agent-Driven Routing) ────────────────────

    async def handle_user_message(self, message: str) -> None:
        """Handle any user message. The agent decides the intent.

        - During pipeline: routes between "advance" and "iterate"
        - After completion: routes to vibe modeling
        """
        if not self.project:
            await self._send_error("No active project. Start a pipeline first.")
            return

        # If pipeline is complete → vibe modeling
        if self.project.current_phase == Phase.COMPLETE:
            await self._handle_vibe_message(message)
            return

        # During pipeline → route via LLM
        current_phase = self.project.current_phase
        logger.info(f"[Pipeline] User message during {current_phase.value}: {message[:100]}...")

        try:
            # Ask the LLM to classify the intent
            router_prompt = _ROUTER_PROMPT.format(
                phase=current_phase.value,
                message=message,
            )
            result = self.client.generate_json(
                prompt=router_prompt,
                system_instruction="You are a routing classifier. Respond with JSON only.",
                temperature=0.1,
            )

            intent = result.get("intent", "iterate")
            feedback = result.get("feedback", message)

            if intent == "advance":
                await self._advance_phase()
            else:
                # Iterate current phase with feedback
                await self.send({
                    "type": "agent_message",
                    "phase": current_phase.value,
                    "message": f"Refining {current_phase.value} with your feedback...",
                })
                await self._run_phase(current_phase, feedback=feedback)

        except Exception as e:
            logger.error(f"[Pipeline] Routing error: {e}", exc_info=True)
            # Fallback: treat as iteration
            await self.send({
                "type": "agent_message",
                "phase": current_phase.value,
                "message": f"Processing your feedback...",
            })
            await self._run_phase(current_phase, feedback=message)

    async def _advance_phase(self) -> None:
        """Advance to the next phase in the pipeline."""
        current = self.project.current_phase
        self.project.phase_approved[current] = True

        await self.send({
            "type": "pipeline_status",
            "phase": current.value,
            "status": "completed",
        })

        try:
            current_idx = _PHASE_ORDER.index(current)
            if current_idx + 1 < len(_PHASE_ORDER):
                next_phase = _PHASE_ORDER[current_idx + 1]
                await self._run_phase(next_phase)
            else:
                self.project.current_phase = Phase.COMPLETE
                await self.send({
                    "type": "pipeline_complete",
                    "projectName": self.project.project_name,
                })
        except ValueError:
            await self._send_error(f"Unknown phase: {current}")

    # ── Vibe Modeling ──────────────────────────────────────────────────

    async def _handle_vibe_message(self, message: str) -> None:
        """Handle a vibe modeling instruction (after pipeline completes)."""
        logger.info(f"[Pipeline] Vibe message: {message[:100]}...")

        await self.send({
            "type": "agent_message",
            "phase": "vibe",
            "message": "Analyzing your instruction...",
        })

        try:
            canvas_json_str = json.dumps(self.project.canvas_json, ensure_ascii=False)
            analysis = self.vibe_agent.analyze_instruction(
                instruction=message,
                requirements_content=self.project.requirements,
                design_content=canvas_json_str,
            )

            change_type = analysis.get("change_type", "both")
            change_desc = analysis.get("summary", message)

            # Apply design changes
            if change_type in ("design_only", "both"):
                design_md, new_spec = self.design_agent.update(
                    current_design_md=self.project.design_md,
                    current_spec=self.project.canvas_json,
                    change_description=analysis.get("design_changes", change_desc),
                    requirements_content=self.project.requirements,
                )
                apply_layout(new_spec)
                self.project.design_md = design_md
                self.project.canvas_json = new_spec

                await self.send({"type": "file_update", "filename": "design.md", "content": design_md})
                await self.send({"type": "canvas_update", "canvasJson": new_spec})
                self._save_file("design.md", design_md)
                self._save_file("class_diagram.json", json.dumps(new_spec, indent=2, ensure_ascii=False))

            # Apply requirements changes
            if change_type in ("requirements_only", "both"):
                new_reqs = self.requirements_agent.update(
                    current_requirements=self.project.requirements,
                    change_description=analysis.get("requirements_changes", change_desc),
                    brief_content=self.project.brief,
                )
                self.project.requirements = new_reqs
                await self.send({"type": "file_update", "filename": "requirements.md", "content": new_reqs})
                self._save_file("requirements.md", new_reqs)

            # Update traceability
            new_trace = self.traceability_agent.update(
                current_traceability=self.project.traceability,
                change_description=change_desc,
                requirements_content=self.project.requirements,
                design_content=json.dumps(self.project.canvas_json, indent=2, ensure_ascii=False),
            )
            self.project.traceability = new_trace
            await self.send({"type": "file_update", "filename": "traceability.md", "content": new_trace})
            self._save_file("traceability.md", new_trace)

            chat_response = analysis.get("chat_response", f"Applied changes: {change_desc}")
            await self.send({
                "type": "agent_message",
                "phase": "vibe",
                "message": chat_response,
            })

        except Exception as e:
            logger.error(f"[Pipeline] Vibe error: {e}", exc_info=True)
            await self._send_error(f"Error processing instruction: {e}")

    # ── Diagram Update (Bidirectional Traceability) ────────────────────

    async def handle_diagram_update(self, new_canvas_json: dict) -> None:
        """Handle manual diagram changes from the frontend."""
        if not self.project or not self.project.canvas_json:
            return

        changes = self._detect_diagram_changes(self.project.canvas_json, new_canvas_json)
        if not changes:
            return

        logger.info(f"[Pipeline] Diagram changes: {changes}")

        await self.send({
            "type": "agent_message",
            "phase": "traceability",
            "message": f"Detected diagram changes: {changes}\nUpdating requirements...",
        })

        try:
            self.project.canvas_json = new_canvas_json

            new_design_md = self.design_agent.update_from_diagram(
                new_spec=new_canvas_json,
                current_design_md=self.project.design_md,
                requirements_content=self.project.requirements,
            )
            self.project.design_md = new_design_md
            await self.send({"type": "file_update", "filename": "design.md", "content": new_design_md})
            self._save_file("design.md", new_design_md)
            self._save_file("class_diagram.json", json.dumps(new_canvas_json, indent=2, ensure_ascii=False))

            new_reqs = self.traceability_agent.reconcile_requirements(
                changes_description=changes,
                current_requirements=self.project.requirements,
            )
            self.project.requirements = new_reqs
            await self.send({"type": "file_update", "filename": "requirements.md", "content": new_reqs})
            self._save_file("requirements.md", new_reqs)

            new_trace = self.traceability_agent.update(
                current_traceability=self.project.traceability,
                change_description=f"Manual diagram edit: {changes}",
                requirements_content=self.project.requirements,
                design_content=json.dumps(new_canvas_json, indent=2, ensure_ascii=False),
            )
            self.project.traceability = new_trace
            await self.send({"type": "file_update", "filename": "traceability.md", "content": new_trace})
            self._save_file("traceability.md", new_trace)

            await self.send({
                "type": "agent_message",
                "phase": "traceability",
                "message": "✅ Requirements and traceability updated to reflect your diagram changes.",
            })

        except Exception as e:
            logger.error(f"[Pipeline] Diagram update error: {e}", exc_info=True)
            await self._send_error(f"Error reconciling diagram changes: {e}")

    # ── Internal Phase Runners ─────────────────────────────────────────

    async def _run_phase(self, phase: Phase, feedback: str = "") -> None:
        """Run a single phase and pause for user input."""
        self.project.current_phase = phase

        await self.send({
            "type": "pipeline_status",
            "phase": phase.value,
            "status": "running",
        })

        try:
            if phase == Phase.BRIEF:
                await self._run_brief(feedback)
            elif phase == Phase.REQUIREMENTS:
                await self._run_requirements(feedback)
            elif phase == Phase.DESIGN:
                await self._run_design(feedback)
            elif phase == Phase.TRACEABILITY:
                await self._run_traceability(feedback)

            # Mark phase as ready (waiting for user input)
            # Exception: traceability auto-completes
            if phase == Phase.TRACEABILITY:
                self.project.phase_approved[phase] = True
                self.project.current_phase = Phase.COMPLETE
                await self.send({
                    "type": "pipeline_status",
                    "phase": phase.value,
                    "status": "completed",
                })
                await self.send({
                    "type": "pipeline_complete",
                    "projectName": self.project.project_name,
                })
            else:
                await self.send({
                    "type": "pipeline_status",
                    "phase": phase.value,
                    "status": "ready",
                })

        except Exception as e:
            logger.error(f"[Pipeline] Phase {phase.value} failed: {e}", exc_info=True)
            await self.send({
                "type": "pipeline_status",
                "phase": phase.value,
                "status": "error",
            })
            await self._send_error(f"Phase {phase.value} failed: {str(e)}")

    async def _run_brief(self, feedback: str = "") -> None:
        if feedback and self.project.brief:
            prompt_idea = (
                f"Original idea: {self.project.idea}\n\n"
                f"Current brief:\n{self.project.brief}\n\n"
                f"User feedback: {feedback}\n\nUpdate the brief."
            )
        else:
            prompt_idea = self.project.idea

        content = self.brief_agent.generate(prompt_idea)
        self.project.brief = content

        for line in content.split("\n"):
            if line.startswith("# "):
                name = line.replace("# ", "").replace("Brief:", "").strip()
                if name:
                    self.project.project_name = name
                    break

        await self.send({"type": "file_update", "filename": "brief.md", "content": content})
        self._save_file("brief.md", content)
        await self.send({
            "type": "agent_message",
            "phase": "brief",
            "message": (
                f"📝 **Brief generated** for *{self.project.project_name}*.\n\n"
                f"Review the brief in the file explorer. "
                f"If it looks good, type something like **\"ok\"** or **\"continue\"** to proceed. "
                f"Otherwise, tell me what to change."
            ),
        })

    async def _run_requirements(self, feedback: str = "") -> None:
        if feedback and self.project.requirements:
            new_reqs = self.requirements_agent.update(
                current_requirements=self.project.requirements,
                change_description=feedback,
                brief_content=self.project.brief,
            )
        else:
            new_reqs = self.requirements_agent.generate(
                brief_content=self.project.brief,
                project_name=self.project.project_name,
            )

        self.project.requirements = new_reqs
        await self.send({"type": "file_update", "filename": "requirements.md", "content": new_reqs})
        self._save_file("requirements.md", new_reqs)
        await self.send({
            "type": "agent_message",
            "phase": "requirements",
            "message": (
                "📋 **Requirements generated** in EARS format.\n\n"
                "Review the requirements. Type **\"ok\"** to proceed to design, "
                "or tell me what to change."
            ),
        })

    async def _run_design(self, feedback: str = "") -> None:
        if feedback and self.project.canvas_json:
            design_md, spec = self.design_agent.update(
                current_design_md=self.project.design_md,
                current_spec=self.project.canvas_json,
                change_description=feedback,
                requirements_content=self.project.requirements,
            )
        else:
            design_md, spec = self.design_agent.generate(
                requirements_content=self.project.requirements,
                brief_content=self.project.brief,
                project_name=self.project.project_name,
            )

        apply_layout(spec)
        self.project.design_md = design_md
        self.project.canvas_json = spec

        await self.send({"type": "file_update", "filename": "design.md", "content": design_md})
        await self.send({"type": "canvas_update", "canvasJson": spec})
        self._save_file("design.md", design_md)
        self._save_file("class_diagram.json", json.dumps(spec, indent=2, ensure_ascii=False))
        await self.send({
            "type": "agent_message",
            "phase": "design",
            "message": (
                f"🏗️ **Class diagram generated** with {len(spec.get('classes', []))} classes "
                f"and {len(spec.get('relationships', []))} relationships.\n\n"
                f"The diagram has been rendered on the canvas. "
                f"Type **\"ok\"** to generate traceability, or tell me what to change."
            ),
        })

    async def _run_traceability(self, feedback: str = "") -> None:
        design_str = json.dumps(self.project.canvas_json, indent=2, ensure_ascii=False)

        if feedback and self.project.traceability:
            content = self.traceability_agent.update(
                current_traceability=self.project.traceability,
                change_description=feedback,
                requirements_content=self.project.requirements,
                design_content=design_str,
            )
        else:
            content = self.traceability_agent.generate(
                requirements_content=self.project.requirements,
                design_content=design_str,
                project_name=self.project.project_name,
            )

        self.project.traceability = content
        await self.send({"type": "file_update", "filename": "traceability.md", "content": content})
        self._save_file("traceability.md", content)
        await self.send({
            "type": "agent_message",
            "phase": "traceability",
            "message": (
                "🔗 **Traceability matrix generated.** All phases complete!\n\n"
                "You can now use the chat to refine the design. "
                "Try things like: *\"Add an email attribute to User\"* or "
                "*\"Create a Payment class\"*."
            ),
        })

    # ── Change Detection ───────────────────────────────────────────────

    def _detect_diagram_changes(self, old_spec: dict, new_spec: dict) -> str:
        old_classes = {c["className"]: c for c in old_spec.get("classes", [])}
        new_classes = {c["className"]: c for c in new_spec.get("classes", [])}
        changes: list[str] = []

        for name in new_classes:
            if name not in old_classes:
                attrs = [a.get("name", "?") for a in new_classes[name].get("attributes", [])]
                changes.append(f"Added class '{name}' with attributes: {', '.join(attrs)}")
        for name in old_classes:
            if name not in new_classes:
                changes.append(f"Removed class '{name}'")
        for name in old_classes:
            if name not in new_classes:
                continue
            old_cls, new_cls = old_classes[name], new_classes[name]
            old_attrs = {a["name"] for a in old_cls.get("attributes", []) if "name" in a}
            new_attrs = {a["name"] for a in new_cls.get("attributes", []) if "name" in a}
            for a in new_attrs - old_attrs:
                changes.append(f"Added attribute '{a}' to '{name}'")
            for a in old_attrs - new_attrs:
                changes.append(f"Removed attribute '{a}' from '{name}'")

        def _rel_key(r: dict) -> str:
            return f"{r.get('source','?')}-{r.get('type','?')}-{r.get('target','?')}"

        old_rels = {_rel_key(r) for r in old_spec.get("relationships", [])}
        new_rels = {_rel_key(r) for r in new_spec.get("relationships", [])}
        for rk in new_rels - old_rels:
            changes.append(f"Added relationship: {rk}")
        for rk in old_rels - new_rels:
            changes.append(f"Removed relationship: {rk}")

        return "; ".join(changes)

    async def _send_error(self, message: str) -> None:
        await self.send({"type": "error", "message": message})

    # ── File Persistence ─────────────────────────────────────────────────

    def _save_file(self, filename: str, content: str) -> None:
        """Persist a generated file to the output directory (overwrites)."""
        if not self.output_dir:
            return
        try:
            path = Path(self.output_dir) / filename
            path.write_text(content, encoding="utf-8")
            logger.info(f"[Pipeline] Saved: {path}")
        except Exception as e:
            logger.warning(f"[Pipeline] Failed to save {filename}: {e}")
