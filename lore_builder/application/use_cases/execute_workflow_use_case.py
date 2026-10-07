import json
import logging
import os
from typing import Dict, Any, List, Optional

from ..dto.workflow_dto import (
    WorkflowConfigDTO,
    WorkflowTaskDTO,
    WorkflowExecutionResultDTO,
)
from ..dto.entity_dto import GenerateEntityCommand
from ..ports.outbound.memory_port import MemoryPort
from ..ports.outbound.jev_decision_port import JevDecisionPort
from .generate_entity_use_case import GenerateEntityUseCase
from .orchestrate_swarm_use_case import OrchestrateSwarmUseCase
from .audit_entity_use_case import AuditEntityUseCase
from ...domain.model.aggregate import WorldBibleAggregate

logger = logging.getLogger(__name__)


class ExecuteWorkflowUseCase:
    """Use case that executes a declarative YAML workflow specification across the Hexagonal DDD domain."""

    def __init__(
        self,
        memory_port: MemoryPort,
        generator: GenerateEntityUseCase,
        orchestrator: OrchestrateSwarmUseCase,
        auditor: AuditEntityUseCase,
        jev_port: JevDecisionPort,
    ):
        self.memory = memory_port
        self.generator = generator
        self.orchestrator = orchestrator
        self.auditor = auditor
        self.jev = jev_port

    def execute(self, workflow: WorkflowConfigDTO) -> WorkflowExecutionResultDTO:
        logger.info(f"Starting YAML workflow execution with {len(workflow.tasks)} task(s).")

        # 1. Initialize custom world bible if defined in YAML
        if workflow.world:
            custom_world = WorldBibleAggregate(
                world_id="custom-yaml-world",
                name=workflow.world.name,
                cosmology=workflow.world.cosmology,
                immutable_laws=workflow.world.immutable_laws,
                tone=workflow.world.tone,
            )
            self.memory.save_world_bible(custom_world)
            logger.info(f"Loaded custom World Bible from YAML: '{custom_world.name}' with {len(custom_world.immutable_laws)} laws.")

        task_results: List[Dict[str, Any]] = []
        successful = 0
        failed = 0

        # 2. Sequential execution of declarative tasks
        for idx, task in enumerate(workflow.tasks):
            logger.info(f"Executing YAML Task [{idx + 1}/{len(workflow.tasks)}]: {task.task_type.upper()}")
            try:
                res = self._execute_single_task(task)
                task_results.append({
                    "task_index": idx + 1,
                    "task_type": task.task_type,
                    "status": "SUCCESS",
                    "result": res,
                })
                successful += 1
            except Exception as e:
                logger.error(f"Error executing task #{idx + 1} ({task.task_type}): {e}", exc_info=True)
                task_results.append({
                    "task_index": idx + 1,
                    "task_type": task.task_type,
                    "status": "FAILED",
                    "error": str(e),
                })
                failed += 1

        # 3. Export output file if configured in YAML settings
        output_file_written = None
        if workflow.settings.output_file:
            output_file_written = self._write_output_file(
                workflow.settings.output_file,
                task_results,
            )

        return WorkflowExecutionResultDTO(
            total_tasks=len(workflow.tasks),
            successful_tasks=successful,
            failed_tasks=failed,
            task_results=task_results,
            output_file_written=output_file_written,
        )

    def _execute_single_task(self, task: WorkflowTaskDTO) -> Dict[str, Any]:
        t_type = task.task_type

        if t_type == "generate":
            cmd = GenerateEntityCommand(
                name=task.name,  # type: ignore
                entity_type=task.entity_type,  # type: ignore
                prompt_hint=task.prompt,  # type: ignore
                era=task.era,
                year=task.year,
            )
            res = self.generator.execute(cmd)
            return {
                "entity_name": res.name,
                "entity_type": res.entity_type,
                "status": res.status,
                "summary": res.summary,
                "timeline": res.timeline,
                "facts": res.facts,
                "relations": res.relations,
            }

        elif t_type == "swarm":
            swarm_res = self.orchestrator.execute(task.prompt)  # type: ignore
            return {
                "prompt": swarm_res.prompt,
                "total_waves": swarm_res.total_waves,
                "entities_count": len(swarm_res.entities_generated),
                "entities": [
                    {"name": e.name, "type": e.entity_type, "status": e.status, "summary": e.summary}
                    for e in swarm_res.entities_generated
                ],
                "facts_committed": swarm_res.facts_committed,
            }

        elif t_type == "audit":
            world = self.memory.get_world_bible()
            report = self.jev.audit_entity_canon(
                world_rules=world.render_prompt_context(),
                entity_name=task.name,  # type: ignore
                entity_narrative=task.narrative,  # type: ignore
                immutable_laws=world.immutable_laws,
            )
            return {
                "entity_name": task.name,
                "verdict": report.recommended_verdict,
                "p_compliant": report.is_canon_consistent.p_yes,
                "distortion_risk_score": report.lore_distortion_risk.score,
                "risk_levels": report.lore_distortion_risk.level_probabilities,
                "explanation": report.explanation,
            }

        elif t_type == "classify":
            candidates = task.candidate_relations or [
                "allied_with", "enemy_of", "vassal_of", "ruler_of", "creator_of", "located_in", "worships", "opposes"
            ]
            choice = self.jev.classify_relation_type(
                entity_a=task.source,  # type: ignore
                entity_b=task.target,  # type: ignore
                narrative_context=task.context,  # type: ignore
                candidate_relations=candidates,
            )
            return {
                "entity_a": choice.entity_a,
                "entity_b": choice.entity_b,
                "chosen_relation": choice.relation,
                "confidence": choice.confidence,
                "probabilities": choice.probabilities,
            }

        elif t_type == "temporal":
            choice = self.jev.classify_temporal_relation(
                interval_a=task.interval_a,  # type: ignore
                interval_b=task.interval_b,  # type: ignore
                narrative_context=task.context,  # type: ignore
            )
            return {
                "interval_a": choice.interval_a,
                "interval_b": choice.interval_b,
                "allen_relation": choice.allen_relation,
                "confidence": choice.confidence,
                "probabilities": choice.probabilities,
            }

        elif t_type == "score":
            score_dec = self.jev.evaluate_lore_distortion_risk(
                world_context="High fantasy canon",
                entity_narrative=task.narrative,  # type: ignore
            )
            return {
                "score": score_dec.score,
                "confidence": score_dec.confidence,
                "level_probabilities": score_dec.level_probabilities,
            }

        elif t_type == "graph":
            g = self.memory.get_entity_wiki_graph(task.name)  # type: ignore
            return g

        elif t_type == "show-world":
            bible = self.memory.get_world_bible()
            return {
                "name": bible.name,
                "cosmology": bible.cosmology,
                "immutable_laws": bible.immutable_laws,
                "tone": bible.tone,
            }

        raise ValueError(f"Unknown task type: '{t_type}'")

    def _write_output_file(self, file_path: str, results: List[Dict[str, Any]]) -> str:
        """Writes the workflow execution results to a file (JSON or Markdown)."""
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        if abs_path.endswith(".json"):
            with open(abs_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
        else:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write("# Lore AI Builder — YAML Workflow Execution Results\n\n")
                for r in results:
                    f.write(f"## Task #{r['task_index']}: {r['task_type'].upper()} ({r['status']})\n\n")
                    f.write("```json\n")
                    f.write(json.dumps(r.get("result") or r.get("error"), indent=2, ensure_ascii=False))
                    f.write("\n```\n\n")

        logger.info(f"Exported workflow results to: {abs_path}")
        return abs_path
