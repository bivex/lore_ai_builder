import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from ..ports.outbound.memory_port import MemoryPort
from ..ports.outbound.resource_port import ResourceControllerPort
from ..ports.outbound.llm_port import LLMProviderPort
from ..ports.outbound.event_publisher_port import EventPublisherPort
from ..ports.outbound.jev_decision_port import JevDecisionPort
from ..use_cases.generate_entity_use_case import GenerateEntityUseCase
from ..use_cases.audit_entity_use_case import AuditEntityUseCase
from ..dto.entity_dto import GenerateEntityCommand, EntityResponseDTO
from ...domain.services.dag_decomposer import LoreDAGPlanner, LoreTaskNode
from ...domain.services.entity_resolver import EntityResolutionService
from ...domain.services.triplet_extractor import TripletExtractionService
from ...domain.services.temporal_validator import TimeInterval
from ..services.context_optimizer import ContextOptimizerService, ContextItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SwarmGenerationResultDTO:
    prompt: str
    total_waves: int
    entities_generated: List[EntityResponseDTO]
    wiki_nodes: List[Dict[str, Any]]
    facts_committed: int


class OrchestrateSwarmUseCase:
    """Master Algorithm: Coordinates multi-agent swarm generation across DAG topological waves,
    optimizing context packing (RRF + Knapsack), enforcing OS resource limits (JobObjects_RD),
    guaranteeing temporal and axiomatic consistency, and classifying relations via Jev System-1 decisions.
    """

    def __init__(
        self,
        memory_port: MemoryPort,
        resource_controller: ResourceControllerPort,
        llm_provider: LLMProviderPort,
        event_publisher: EventPublisherPort,
        jev_port: Optional[JevDecisionPort] = None,
        audit_use_case: Optional[AuditEntityUseCase] = None,
    ):
        self.memory = memory_port
        self.resources = resource_controller
        self.llm = llm_provider
        self.publisher = event_publisher
        self.jev = jev_port

        self.auditor = audit_use_case or AuditEntityUseCase(
            memory_port=self.memory,
            event_publisher=self.publisher,
            jev_port=self.jev,
        )
        self.generator = GenerateEntityUseCase(
            memory_port=self.memory,
            resource_controller=self.resources,
            llm_provider=self.llm,
            event_publisher=self.publisher,
            audit_use_case=self.auditor,
        )
        self.resolver = EntityResolutionService(match_threshold=0.85)

    def execute(self, user_prompt: str) -> SwarmGenerationResultDTO:
        logger.info(f"Decomposing user prompt into DAG tasks: '{user_prompt[:60]}...'")

        # 1. Algorithm: Prompt -> DAG Decomposition
        raw_tasks = LoreDAGPlanner.decompose_prompt_heuristics(user_prompt)

        # 2. Algorithm: Kahn's Topological Sort into Execution Waves
        waves = LoreDAGPlanner.topological_sort(raw_tasks)
        logger.info(f"Topological sorting organized {len(raw_tasks)} tasks into {len(waves)} execution wave(s).")

        generated_entities: List[EntityResponseDTO] = []
        total_facts = 0

        # 3. Wave-by-Wave Multi-Agent Execution under JobObjects_RD Supervision
        for wave_idx, wave_tasks in enumerate(waves):
            logger.info(f"--- Launching Wave {wave_idx + 1}/{len(waves)} with {len(wave_tasks)} task(s) ---")

            for task in wave_tasks:
                # Algorithm: Entity Resolution & Deduplication
                resolved_name, is_existing = self.resolver.resolve(task.name)

                # Algorithm: Context Assembly & Knapsack Budget Allocation
                context_hint = self._build_optimized_context_hint(task, user_prompt)

                cmd = GenerateEntityCommand(
                    name=resolved_name,
                    entity_type=task.entity_type,
                    prompt_hint=context_hint,
                    era=task.era,
                    year=task.year,
                )

                # Execute under native OS shield & audit
                res = self.generator.execute(cmd)
                generated_entities.append(res)
                total_facts += len(res.facts)

                # Algorithm: Triplet Extraction & Distillation into Link Graph
                extracted_relations = TripletExtractionService.extract_triplets_and_relations(
                    entity_name=res.name,
                    text=res.description,
                )

                # Algorithm: Jev System-1 Ontological Relation Classification
                if self.jev and extracted_relations:
                    candidate_relation_types = [
                        "allied_with", "enemy_of", "vassal_of", "ruler_of",
                        "creator_of", "located_in", "worships", "opposes", "member_of"
                    ]
                    for target, rel_hint in extracted_relations.items():
                        ontology_choice = self.jev.classify_relation_type(
                            entity_a=res.name,
                            entity_b=target,
                            narrative_context=f"{res.description} {rel_hint}",
                            candidate_relations=candidate_relation_types,
                        )
                        self.memory.add_entity_relation(
                            from_entity=res.name,
                            to_entity=target,
                            relation_type=ontology_choice.relation,
                        )
                        logger.info(
                            f"Jev classified relation: '{res.name}' --[{ontology_choice.relation}]--> '{target}' "
                            f"(confidence: {ontology_choice.confidence:.2f})"
                        )

                logger.info(f"Generated & validated '{res.name}' ({res.entity_type}) with {len(res.facts)} facts.")

        # 4. Compile Wiki Knowledge Network Nodes
        wiki_nodes = []
        for ent in generated_entities:
            graph_data = self.memory.get_entity_wiki_graph(ent.name)
            wiki_nodes.append(graph_data)

        return SwarmGenerationResultDTO(
            prompt=user_prompt,
            total_waves=len(waves),
            entities_generated=generated_entities,
            wiki_nodes=wiki_nodes,
            facts_committed=total_facts,
        )

    def _build_optimized_context_hint(self, task: LoreTaskNode, global_prompt: str) -> str:
        """Assembles optimal context items and applies Knapsack packing within budget."""
        # 1. Search relevant L1 facts
        facts = self.memory.search_canonical_facts(query=f"{task.name} {task.prompt_hint}", limit=5)
        context_items: List[ContextItem] = []

        for i, f in enumerate(facts):
            cost = ContextOptimizerService.estimate_tokens(f.statement)
            context_items.append(
                ContextItem(
                    item_id=f.fact_id,
                    content=f.statement,
                    relevance_score=1.0 / (i + 1),
                    token_cost=cost,
                    source_type="L1_FACT",
                )
            )

        # 2. Knapsack pack within 500 token budget for hints
        packed = ContextOptimizerService.knapsack_pack(context_items, max_token_budget=500)
        facts_summary = "; ".join(item.content for item in packed)

        hint = f"{task.prompt_hint}."
        if facts_summary:
            hint += f" Pre-existing facts: [{facts_summary}]."
        return hint
