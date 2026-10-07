from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum


class AllenRelation(str, Enum):
    BEFORE = "before"
    MEETS = "meets"
    OVERLAPS = "overlaps"
    STARTS = "starts"
    DURING = "during"
    FINISHES = "finishes"
    EQUALS = "equals"
    AFTER = "after"
    MET_BY = "met_by"
    OVERLAPPED_BY = "overlapped_by"
    STARTED_BY = "started_by"
    CONTAINS = "contains"
    FINISHED_BY = "finished_by"


@dataclass(frozen=True)
class TimeInterval:
    start_year: int
    end_year: Optional[int] = None

    def __post_init__(self):
        if self.end_year is not None and self.end_year < self.start_year:
            raise ValueError(f"Invalid interval: end_year ({self.end_year}) < start_year ({self.start_year})")

    @property
    def effective_end(self) -> int:
        return self.end_year if self.end_year is not None else self.start_year

    def relation_to(self, other: "TimeInterval") -> AllenRelation:
        s1, e1 = self.start_year, self.effective_end
        s2, e2 = other.start_year, other.effective_end

        if e1 < s2:
            return AllenRelation.BEFORE
        if e1 == s2 and s1 < e1:
            return AllenRelation.MEETS
        if s1 < s2 and s2 < e1 < e2:
            return AllenRelation.OVERLAPS
        if s1 == s2 and e1 < e2:
            return AllenRelation.STARTS
        if s2 < s1 and e1 < e2:
            return AllenRelation.DURING
        if s2 < s1 and e1 == e2:
            return AllenRelation.FINISHES
        if s1 == s2 and e1 == e2:
            return AllenRelation.EQUALS
        if s1 > e2:
            return AllenRelation.AFTER
        if s1 == e2 and s2 < e2:
            return AllenRelation.MET_BY
        if s2 < s1 < e2 and e1 > e2:
            return AllenRelation.OVERLAPPED_BY
        if s1 == s2 and e1 > e2:
            return AllenRelation.STARTED_BY
        if s1 < s2 and e1 > e2:
            return AllenRelation.CONTAINS
        if s1 < s2 and e1 == e2:
            return AllenRelation.FINISHED_BY

        return AllenRelation.OVERLAPS


class TemporalConsistencyValidator:
    """Algorithm enforcing Allen's Interval Algebra consistency across historical lore entities."""

    @staticmethod
    def validate_participation(
        participant_name: str,
        participant_lifespan: TimeInterval,
        event_name: str,
        event_time: TimeInterval,
    ) -> Tuple[bool, Optional[str]]:
        """A character/participant cannot participate in an event outside their active lifespan."""
        rel = participant_lifespan.relation_to(event_time)
        if rel in (AllenRelation.BEFORE, AllenRelation.AFTER):
            if rel == AllenRelation.BEFORE:
                msg = (
                    f"Temporal Paradox: '{participant_name}' died/ended in year {participant_lifespan.effective_end}, "
                    f"but event '{event_name}' took place later (Year {event_time.start_year})."
                )
            else:
                msg = (
                    f"Temporal Paradox: '{participant_name}' was born/founded in year {participant_lifespan.start_year}, "
                    f"but event '{event_name}' occurred earlier (Year {event_time.effective_end})."
                )
            return False, msg
        return True, None

    @staticmethod
    def validate_causality(
        cause_event: str,
        cause_time: TimeInterval,
        effect_event: str,
        effect_time: TimeInterval,
    ) -> Tuple[bool, Optional[str]]:
        """A cause must precede or start at the same time as its effect."""
        if cause_time.start_year > effect_time.start_year:
            return (
                False,
                f"Causal Paradox: Cause event '{cause_event}' (Year {cause_time.start_year}) "
                f"cannot occur after effect event '{effect_event}' (Year {effect_time.start_year}).",
            )
        return True, None

    @staticmethod
    def validate_artifact_usage(
        artifact_name: str,
        creation_time: TimeInterval,
        user_name: str,
        usage_time: TimeInterval,
    ) -> Tuple[bool, Optional[str]]:
        """An artifact cannot be wielded before it is created."""
        if usage_time.start_year < creation_time.start_year:
            return (
                False,
                f"Artifact Anachronism: '{artifact_name}' was forged in year {creation_time.start_year}, "
                f"but '{user_name}' allegedly wielded it in year {usage_time.start_year}.",
            )
        return True, None
