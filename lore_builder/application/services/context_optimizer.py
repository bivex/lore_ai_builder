from dataclasses import dataclass
from typing import List, Dict, Any, Set, Tuple
from collections import deque


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    content: str
    relevance_score: float
    token_cost: int
    source_type: str  # "L3_RULE", "L1_FACT", "WIKI_NEIGHBOR"


class ContextOptimizerService:
    """Algorithms for Context Assembly: Multi-Hop Graph BFS, Reciprocal Rank Fusion (RRF), and Knapsack Token Budgeting."""

    @staticmethod
    def rrf_fuse(
        bm25_ranks: Dict[str, int],
        vector_ranks: Dict[str, int],
        graph_ranks: Dict[str, int],
        k: int = 60,
    ) -> Dict[str, float]:
        """Calculates Reciprocal Rank Fusion (RRF) scores across multiple retrievers.
        
        Score(d) = sum(1 / (k + rank_i(d)))
        """
        all_ids = set(bm25_ranks.keys()) | set(vector_ranks.keys()) | set(graph_ranks.keys())
        fused_scores: Dict[str, float] = {}

        for doc_id in all_ids:
            score = 0.0
            if doc_id in bm25_ranks:
                score += 1.0 / (k + bm25_ranks[doc_id])
            if doc_id in vector_ranks:
                score += 1.0 / (k + vector_ranks[doc_id])
            if doc_id in graph_ranks:
                score += 1.0 / (k + graph_ranks[doc_id])
            fused_scores[doc_id] = score

        return fused_scores

    @staticmethod
    def multi_hop_graph_bfs(
        start_nodes: List[str],
        graph: Dict[str, List[str]],
        max_hops: int = 2,
    ) -> Dict[str, int]:
        """Performs Breadth-First-Search up to max_hops on Wiki Link Graph.
        
        Returns node_name -> hop_distance.
        """
        distances: Dict[str, int] = {}
        queue: deque = deque([(node, 0) for node in start_nodes])
        visited: Set[str] = set(start_nodes)

        for node in start_nodes:
            distances[node] = 0

        while queue:
            current, dist = queue.popleft()
            if dist >= max_hops:
                continue

            neighbors = graph.get(current, [])
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    distances[neighbor] = dist + 1
                    queue.append((neighbor, dist + 1))

        return distances

    @staticmethod
    def knapsack_pack(
        items: List[ContextItem],
        max_token_budget: int = 2000,
    ) -> List[ContextItem]:
        """Greedy approximation for 0/1 Knapsack: Packs highest density (value / token_cost) items within token budget."""
        if not items or max_token_budget <= 0:
            return []

        # Sort by value density (relevance_score / token_cost) descending
        sorted_items = sorted(
            items,
            key=lambda x: (x.relevance_score / max(1, x.token_cost)),
            reverse=True,
        )

        packed: List[ContextItem] = []
        current_tokens = 0

        for item in sorted_items:
            if current_tokens + item.token_cost <= max_token_budget:
                packed.append(item)
                current_tokens += item.token_cost

        return packed

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Heuristic estimation of token count (~4 chars per token)."""
        return max(1, len(text) // 4)
