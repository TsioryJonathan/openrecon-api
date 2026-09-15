from enum import Enum


class Confidence(str, Enum):
    """
    Confidence level for a Finding or a relation.

    - CONFIRMED: multiple independent sources agree, or direct evidence.
    - LIKELY: at least one strong source, or two weak independent sources.
    - POSSIBLE: single weak source, or inferred from context.

    Never present POSSIBLE as a certainty. The level must be recorded alongside
    the reason it was assigned (stored in Finding.confidence_reason).
    """

    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
