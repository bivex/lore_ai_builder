from typing import Dict, List, Optional, Tuple


def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """Computes Jaro-Winkler similarity between two strings."""
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] == s2[j]:
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

    if matches == 0:
        return 0.0

    k = 0
    transpositions = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    transpositions = transpositions // 2
    jaro = (matches / len1 + matches / len2 + (matches - transpositions) / matches) / 3.0

    # Winkler prefix adjustment (up to 4 chars)
    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * p * (1.0 - jaro)


def normalize_entity_name(name: str) -> str:
    """Strips leading articles, honorifics, and punctuation without regex."""
    import unicodedata
    cleaned = unicodedata.normalize("NFKC", name).strip()
    cf = cleaned.casefold()

    # 1. Strip articles
    articles = ("the ", "a ", "an ")
    for art in articles:
        if cf.startswith(art):
            cf = cf.removeprefix(art).strip()
            break

    # 2. Strip organization/title prefixes
    titles = (
        "order of ", "clan of ", "house of ",
        "lord ", "lady ", "king ", "queen ",
        "князь ", "воевода ", "орден ", "клан "
    )
    for title in titles:
        if cf.startswith(title):
            cf = cf.removeprefix(title).strip()
            break

    return "".join(c for c in cf if c.isalnum() or c in (" ", "-")).strip()


class EntityResolutionService:
    """Algorithm resolving entity aliases, preventing duplicate nodes in the Wiki Link Graph."""

    def __init__(self, match_threshold: float = 0.85):
        self.match_threshold = match_threshold
        # canonical_name -> list of aliases
        self._canonical_registry: Dict[str, List[str]] = {}

    def register_canonical(self, canonical_name: str, aliases: Optional[List[str]] = None) -> None:
        if canonical_name not in self._canonical_registry:
            self._canonical_registry[canonical_name] = []
        if aliases:
            for a in aliases:
                if a not in self._canonical_registry[canonical_name]:
                    self._canonical_registry[canonical_name].append(a)

    def _is_valid_fuzzy_match(self, q: str, target: str, score: float) -> bool:
        """Guards against false positive merges between distinct short names (e.g. Alden vs Aldon)."""
        q_tokens = q.split()
        target_tokens = target.split()

        # Multi-token containment: "Kaelen Voss" inside "Commander Kaelen Voss"
        if len(q_tokens) >= 1 and len(target_tokens) >= 1:
            q_set = set(q_tokens)
            t_set = set(target_tokens)
            if (len(q_set) > 1 or len(t_set) > 1) and (q_set.issubset(t_set) or t_set.issubset(q_set)):
                return True

        # Single-token names (e.g. "Alden" vs "Aldon", "Voss" vs "Ross"):
        # For <= 5 chars, distinct names differ by only 1 letter, Jaro-Winkler gives false >0.90!
        if len(q_tokens) == 1 and len(target_tokens) == 1:
            if max(len(q), len(target)) <= 5:
                return q == target
            if max(len(q), len(target)) <= 7:
                return score >= 0.95 and q == target

        return score >= self.match_threshold

    def resolve(self, query_name: str) -> Tuple[str, bool]:
        """Resolves query_name to existing canonical entity if similarity exceeds threshold.
        
        Returns (resolved_name, is_existing_match).
        """
        norm_query = normalize_entity_name(query_name)

        # 1. Exact match against canonical or known aliases
        for canonical, aliases in self._canonical_registry.items():
            if normalize_entity_name(canonical) == norm_query:
                return canonical, True
            for alias in aliases:
                if normalize_entity_name(alias) == norm_query:
                    return canonical, True

        # 2. Fuzzy Jaro-Winkler match with false-positive guard
        best_match = None
        best_score = 0.0

        for canonical, aliases in self._canonical_registry.items():
            norm_canonical = normalize_entity_name(canonical)
            score = jaro_winkler_similarity(norm_query, norm_canonical)
            if score > best_score and self._is_valid_fuzzy_match(norm_query, norm_canonical, score):
                best_score = score
                best_match = canonical

            for alias in aliases:
                norm_alias = normalize_entity_name(alias)
                ascore = jaro_winkler_similarity(norm_query, norm_alias)
                if ascore > best_score and self._is_valid_fuzzy_match(norm_query, norm_alias, ascore):
                    best_score = ascore
                    best_match = canonical

        if best_match:
            # Register new variant as alias
            self._canonical_registry[best_match].append(query_name)
            return best_match, True

        # 3. New unique entity
        self.register_canonical(query_name)
        return query_name, False
