"""Vendored canonical ARC IHB package used by the Grounding Kernel.

Source of truth: autonomic-resilience-collective/ARC-IHB-Engine.
The Grounding Kernel must not silently substitute alternate fallback math.
"""

from .core import (
    Baseline, PhaseStat, compute_baseline, compute_phases, deviation_series,
    detect_anomalies, completeness, rolling_baseline, rolling_state,
)
from .vnext import (
    SegmentationProvenance, SourceEpoch, BaselineDiagnostics, MissingnessProfile,
    PersistenceEvent, RegimeEvidence, baseline_diagnostics, missingness_profile,
    persistent_deviation_events, regime_evidence, source_comparability_evidence,
)
from .domain import DomainProfile, DEVELOPMENT_PROFILE

__all__ = [
    "Baseline", "PhaseStat", "compute_baseline", "compute_phases", "deviation_series",
    "detect_anomalies", "completeness", "rolling_baseline", "rolling_state",
    "SegmentationProvenance", "SourceEpoch", "BaselineDiagnostics", "MissingnessProfile",
    "PersistenceEvent", "RegimeEvidence", "baseline_diagnostics", "missingness_profile",
    "persistent_deviation_events", "regime_evidence", "source_comparability_evidence",
    "DomainProfile", "DEVELOPMENT_PROFILE",
]
