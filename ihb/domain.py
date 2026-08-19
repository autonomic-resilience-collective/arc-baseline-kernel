"""ihb.domain - domain-specific parameter profiles for a domain-agnostic IHB core.

The IHB architecture is reusable across domains, but its operating parameters are
not assumed to be universal. This module makes that boundary explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal

SegmentationMode = Literal["context_defined", "signal_inferred", "context_assisted", "unspecified"]


@dataclass(frozen=True)
class DomainProfile:
    """Parameters that a domain must justify before operational use.

    Defaults are conservative software defaults, not claims that these values are
    scientifically optimal for physiology, ecology, habitat systems, or any other
    domain. Each application should document the evidence supporting its profile.
    """
    name: str
    baseline_days: int = 90
    min_baseline_n: int = 14
    magnitude_threshold_abs_z: float = 2.0
    persistence_min_observations: int = 3
    require_consecutive_days: bool = True
    segmentation_mode: SegmentationMode = "unspecified"
    profile_version: str = "0.1"
    scientific_rationale: str = ""

    def __post_init__(self) -> None:
        if self.baseline_days < 1:
            raise ValueError("baseline_days must be >= 1")
        if self.min_baseline_n < 2:
            raise ValueError("min_baseline_n must be >= 2")
        if self.magnitude_threshold_abs_z <= 0:
            raise ValueError("magnitude_threshold_abs_z must be > 0")
        if self.persistence_min_observations < 1:
            raise ValueError("persistence_min_observations must be >= 1")

    def as_dict(self) -> dict:
        return asdict(self)


DEVELOPMENT_PROFILE = DomainProfile(
    name="development_only",
    scientific_rationale="Software default for deterministic testing; domain validation required before operational use.",
)
