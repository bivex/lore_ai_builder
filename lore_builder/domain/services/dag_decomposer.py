from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
from collections import deque

from ..model.value_objects import EntityType


@dataclass
class LoreTaskNode:
    task_id: str
    name: str
    entity_type: EntityType
    prompt_hint: str
    dependencies: List[str] = field(default_factory=list)
    year: Optional[int] = None
    era: Optional[str] = None


class LoreDAGPlanner:
    """Algorithm parsing complex lore requests into a Directed Acyclic Graph (DAG) and scheduling via Kahn's Topological Sort."""

    @staticmethod
    def topological_sort(nodes: List[LoreTaskNode]) -> List[List[LoreTaskNode]]:
        """Performs Kahn's algorithm to organize task nodes into parallel execution waves.
        
        Returns a list of waves: [[wave0_tasks], [wave1_tasks], ...]
        Raises ValueError if a cycle is detected.
        """
        node_map: Dict[str, LoreTaskNode] = {n.task_id: n for n in nodes}
        in_degree: Dict[str, int] = {n.task_id: 0 for n in nodes}
        adjacency: Dict[str, List[str]] = {n.task_id: [] for n in nodes}

        # Build graph
        for node in nodes:
            for dep_id in node.dependencies:
                if dep_id not in node_map:
                    raise ValueError(f"Task '{node.task_id}' depends on non-existent task '{dep_id}'")
                adjacency[dep_id].append(node.task_id)
                in_degree[node.task_id] += 1

        # Kahn's algorithm with wave grouping
        current_wave = [node_map[tid] for tid, deg in in_degree.items() if deg == 0]
        waves: List[List[LoreTaskNode]] = []
        processed_count = 0

        while current_wave:
            waves.append(current_wave)
            processed_count += len(current_wave)
            next_wave: List[LoreTaskNode] = []

            for task in current_wave:
                for neighbor_id in adjacency[task.task_id]:
                    in_degree[neighbor_id] -= 1
                    if in_degree[neighbor_id] == 0:
                        next_wave.append(node_map[neighbor_id])

            current_wave = next_wave

        if processed_count != len(nodes):
            raise ValueError("Cycle detected in lore dependency graph. Impossible causal ordering.")

        return waves

    @staticmethod
    def decompose_prompt_heuristics(prompt: str) -> List[LoreTaskNode]:
        """Heuristic rule-based decomposition of a high-level world prompt into structured DAG tasks.
        
        Can also be paired with an LLM-based planner for arbitrary prompts.
        """
        nodes: List[LoreTaskNode] = []
        prompt_lower = prompt.lower()

        # Check for Factions / Orders
        if "clan" in prompt_lower or "necromancer" in prompt_lower or "faction" in prompt_lower:
            nodes.append(
                LoreTaskNode(
                    task_id="t_faction_1",
                    name="The Northern Ashen Clan",
                    entity_type=EntityType.FACTION,
                    prompt_hint="Ancient necromantic clan dwelling in the boreal tundras, harvesting bone and soul-frost.",
                    year=150,
                    era="Second Age",
                )
            )

        if "paladin" in prompt_lower or "sun" in prompt_lower or "order" in prompt_lower:
            nodes.append(
                LoreTaskNode(
                    task_id="t_faction_2",
                    name="The Radiant Dawn Paladins",
                    entity_type=EntityType.FACTION,
                    prompt_hint="Solar knightly order guarding the holy ley towers against the necromancers.",
                    year=160,
                    era="Second Age",
                )
            )

        # Check for Conflicts / Wars
        if "war" in prompt_lower or "feud" in prompt_lower or "battle" in prompt_lower:
            deps = [n.task_id for n in nodes if n.entity_type == EntityType.FACTION]
            nodes.append(
                LoreTaskNode(
                    task_id="t_event_1",
                    name="The War of the Eclipse",
                    entity_type=EntityType.HISTORICAL_EVENT,
                    prompt_hint="A bitter three-decade war where the Ashen Clan attempted to extinguish the Solar Tower.",
                    dependencies=deps,
                    year=200,
                    era="Second Age",
                )
            )

        # Check for Artifacts / Relics
        if "artifact" in prompt_lower or "relic" in prompt_lower or "blood" in prompt_lower:
            faction_deps = [n.task_id for n in nodes if "Ashen" in n.name]
            nodes.append(
                LoreTaskNode(
                    task_id="t_artifact_1",
                    name="The Sanguine Reliquary",
                    entity_type=EntityType.ARTIFACT,
                    prompt_hint="A forbidden dark iron chest containing the preserved heart of the First Necromancer.",
                    dependencies=faction_deps or [nodes[0].task_id],
                    year=180,
                    era="Second Age",
                )
            )

        # Check for Locations / Lands
        if "land" in prompt_lower or "territory" in prompt_lower or "region" in prompt_lower:
            event_deps = [n.task_id for n in nodes if n.entity_type == EntityType.HISTORICAL_EVENT]
            nodes.append(
                LoreTaskNode(
                    task_id="t_location_1",
                    name="The Frost-Blighted Wastes",
                    entity_type=EntityType.LOCATION,
                    prompt_hint="The scarred northern tundra poisoned by necromantic fallout following the war.",
                    dependencies=event_deps or ([n.task_id for n in nodes]),
                    year=230,
                    era="Second Age",
                )
            )

        # If nothing specific was extracted, create a general seed task
        if not nodes:
            nodes.append(
                LoreTaskNode(
                    task_id="t_seed_1",
                    name="Origin of the Realm",
                    entity_type=EntityType.HISTORICAL_EVENT,
                    prompt_hint=prompt,
                    year=100,
                    era="First Age",
                )
            )

        return nodes
