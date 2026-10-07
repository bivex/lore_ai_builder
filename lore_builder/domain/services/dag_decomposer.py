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

        is_cyrillic = any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in prompt)

        # Check for Factions / Orders
        if any(w in prompt_lower for w in ["clan", "necromancer", "faction", "клан", "некромант", "волхв", "фракци"]):
            name = "Древний Клан Волхвов" if is_cyrillic else "The Northern Ashen Clan"
            hint = (
                "Тайный орден северных чародеев и волхвов Нави, черпающих морозную силу."
                if is_cyrillic
                else "Ancient necromantic clan dwelling in the boreal tundras, harvesting bone and soul-frost."
            )
            nodes.append(
                LoreTaskNode(
                    task_id="t_faction_1",
                    name=name,
                    entity_type=EntityType.FACTION,
                    prompt_hint=hint,
                    year=150,
                    era="Вторая Эпоха" if is_cyrillic else "Second Age",
                )
            )

        if any(w in prompt_lower for w in ["paladin", "sun", "order", "паладин", "солнц", "рассвет", "орден", "витяз"]):
            name = "Орден Паладинов Рассвета" if is_cyrillic else "The Radiant Dawn Paladins"
            hint = (
                "Светлое рыцарское братство, охраняющее священные башни света."
                if is_cyrillic
                else "Solar knightly order guarding the holy ley towers against the necromancers."
            )
            nodes.append(
                LoreTaskNode(
                    task_id="t_faction_2",
                    name=name,
                    entity_type=EntityType.FACTION,
                    prompt_hint=hint,
                    year=160,
                    era="Вторая Эпоха" if is_cyrillic else "Second Age",
                )
            )

        # Check for Conflicts / Wars
        if any(w in prompt_lower for w in ["war", "feud", "battle", "войн", "вражд", "битв"]):
            deps = [n.task_id for n in nodes if n.entity_type == EntityType.FACTION]
            name = "Война Ледяного Затмения" if is_cyrillic else "The War of the Eclipse"
            hint = (
                "Жестокая тридцатилетняя война за контроль над северными рубежами."
                if is_cyrillic
                else "A bitter three-decade war where the Ashen Clan attempted to extinguish the Solar Tower."
            )
            nodes.append(
                LoreTaskNode(
                    task_id="t_event_1",
                    name=name,
                    entity_type=EntityType.HISTORICAL_EVENT,
                    prompt_hint=hint,
                    dependencies=deps,
                    year=200,
                    era="Вторая Эпоха" if is_cyrillic else "Second Age",
                )
            )

        # Check for Artifacts / Relics
        if any(w in prompt_lower for w in ["artifact", "relic", "blood", "артефакт", "реликви", "кров"]):
            faction_deps = [n.task_id for n in nodes if "Ashen" in n.name or "Волхв" in n.name]
            name = "Кровавый Реликварий" if is_cyrillic else "The Sanguine Reliquary"
            hint = (
                "Древний ларец с запечатанным сердцем первородного чародея."
                if is_cyrillic
                else "A forbidden dark iron chest containing the preserved heart of the First Necromancer."
            )
            nodes.append(
                LoreTaskNode(
                    task_id="t_artifact_1",
                    name=name,
                    entity_type=EntityType.ARTIFACT,
                    prompt_hint=hint,
                    dependencies=faction_deps or [nodes[0].task_id],
                    year=180,
                    era="Вторая Эпоха" if is_cyrillic else "Second Age",
                )
            )

        # Check for Locations / Lands
        if any(w in prompt_lower for w in ["land", "territory", "region", "земл", "территори", "регион", "пустош"]):
            event_deps = [n.task_id for n in nodes if n.entity_type == EntityType.HISTORICAL_EVENT]
            name = "Морозные Пустоши Рубежа" if is_cyrillic else "The Frost-Blighted Wastes"
            hint = (
                "Изуродованная колдовской стужей северная тундра на границе с Навью."
                if is_cyrillic
                else "The scarred northern tundra poisoned by necromantic fallout following the war."
            )
            nodes.append(
                LoreTaskNode(
                    task_id="t_location_1",
                    name=name,
                    entity_type=EntityType.LOCATION,
                    prompt_hint=hint,
                    dependencies=event_deps or ([n.task_id for n in nodes]),
                    year=230,
                    era="Вторая Эпоха" if is_cyrillic else "Second Age",
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
