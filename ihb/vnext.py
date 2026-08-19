"""ihb.vnext - methodological hardening primitives for IHB vNext.

This module extends, but does not silently redefine, the published IHB core.
It implements the explicit distinctions identified during computational-biology
review: baseline diagnostics, missingness provenance, magnitude-versus-regime
separation, persistence logic, segmentation provenance, and source comparability.

Design principles
-----------------
* Deterministic and within-entity. No population reference distributions.
* Observed data are authoritative. Imputation, if used elsewhere, must be a
  separately labelled sensitivity analysis and never overwrite primary IHB data.
* A large deviation is not automatically a state transition. Magnitude evidence
  and persistence/regime evidence are reported separately.
* Different measurement sources are not pooled by default. Comparability is an
  evidence question; this module reports evidence but does not manufacture it.
* Domain-agnostic architecture does not imply domain-independent parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, Literal
import math

import numpy as np
import pandas as pd


SegmentationMode = Literal["context_defined", "signal_inferred", "context_assisted", "unspecified"]
AnalysisMode = Literal["prospective", "retrospective"]


@dataclass(frozen=True)
class SegmentationProvenance:
    """How phase/regime boundaries were established."""
    mode: SegmentationMode = "unspecified"
    source: str = ""
    outcome_metric_used_to_define_boundary: bool = False
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SourceEpoch:
    """Identity of one measurement-source epoch.

    A source change creates a new epoch by default. Pooling epochs requires
    explicit external comparability evidence; correlation alone is not enough.
    """
    source_id: str
    vendor: str = "unknown"
    device_model: str = "unknown"
    algorithm_version: str = "unknown"
    firmware_version: str = "unknown"
    metric_definition: str = ""
    start_study_day: Optional[int] = None
    end_study_day: Optional[int] = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BaselineDiagnostics:
    """Descriptive diagnostics for the reference window, not a validity verdict."""
    n_observed: int
    span_days: int
    completeness_pct: float
    mean: Optional[float]
    sd: Optional[float]
    lag1_autocorr: Optional[float]
    skew: Optional[float]
    variance_ratio_halves: Optional[float]
    zero_variance: bool
    observed_minimum_met: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["warnings"] = list(self.warnings)
        return d


@dataclass(frozen=True)
class MissingnessProfile:
    span_days: int
    n_observed: int
    n_missing: int
    missing_pct: float
    longest_gap_days: int
    gap_intervals: tuple[tuple[int, int], ...]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["gap_intervals"] = [list(x) for x in self.gap_intervals]
        return d


@dataclass(frozen=True)
class PersistenceEvent:
    start_study_day: int
    end_study_day: int
    n_observations: int
    direction: int
    threshold_abs_z: float
    max_abs_z: float
    mean_z: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RegimeEvidence:
    latest_study_day: Optional[int]
    latest_z: Optional[float]
    magnitude_threshold_abs_z: float
    instantaneous_deviation: bool
    persistent_deviation: bool
    persistence_min_observations: int
    current_persistent_event: Optional[PersistenceEvent]
    analysis_mode: AnalysisMode

    def as_dict(self) -> dict:
        d = asdict(self)
        if self.current_persistent_event is not None:
            d["current_persistent_event"] = self.current_persistent_event.as_dict()
        return d


def _safe_float(value) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def baseline_diagnostics(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    window: tuple[float, float],
    *,
    min_n: int = 14,
) -> BaselineDiagnostics:
    """Describe the statistical structure of an IHB baseline window.

    No Gaussianity or independence claim is made. These diagnostics expose
    features that can matter to a mean/SD baseline: missingness, serial
    dependence, skew and changing variance. Threshold interpretation belongs in
    a domain profile or validation protocol, not in this generic function.
    """
    start, end = window
    sub = df[(df[study_day_col] >= start) & (df[study_day_col] < end)][[study_day_col, value_col]].copy()
    if sub.empty:
        return BaselineDiagnostics(0, max(0, int(math.ceil(end - start))), 0.0, None, None, None, None, None, True, False, ("NO_OBSERVED_DATA",))

    sub = sub.sort_values(study_day_col)
    s = sub[value_col].dropna().astype(float)
    n = int(s.shape[0])
    span = max(0, int(math.ceil(end - start)))
    completeness = round((n / span * 100.0), 2) if span > 0 else 0.0

    mean = _safe_float(s.mean()) if n else None
    sd = _safe_float(s.std(ddof=1)) if n > 1 else None
    zero_variance = bool(sd is None or sd == 0.0)

    lag1 = _safe_float(s.autocorr(lag=1)) if n >= 4 else None
    skew = _safe_float(s.skew()) if n >= 3 else None

    variance_ratio = None
    if n >= 8:
        split = n // 2
        v1 = _safe_float(s.iloc[:split].var(ddof=1))
        v2 = _safe_float(s.iloc[split:].var(ddof=1))
        if v1 is not None and v2 is not None and v1 > 0 and v2 > 0:
            variance_ratio = round(max(v1, v2) / min(v1, v2), 4)

    warnings: list[str] = []
    if n < min_n:
        warnings.append("INSUFFICIENT_OBSERVED_BASELINE_N")
    if zero_variance:
        warnings.append("ZERO_OR_UNDEFINED_BASELINE_VARIANCE")
    if completeness < 100.0:
        warnings.append("BASELINE_CONTAINS_MISSING_DAYS")

    return BaselineDiagnostics(
        n_observed=n,
        span_days=span,
        completeness_pct=completeness,
        mean=mean,
        sd=sd,
        lag1_autocorr=(round(lag1, 4) if lag1 is not None else None),
        skew=(round(skew, 4) if skew is not None else None),
        variance_ratio_halves=variance_ratio,
        zero_variance=zero_variance,
        observed_minimum_met=(n >= min_n),
        warnings=tuple(warnings),
    )


def missingness_profile(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    window: Optional[tuple[int, int]] = None,
) -> MissingnessProfile:
    """Report where observations are absent on the study-day axis.

    `window` is half-open [start, end). If omitted, the observed study-day span
    is used. Missing days and explicit nulls are both treated as missing.
    """
    if df.empty:
        return MissingnessProfile(0, 0, 0, 0.0, 0, tuple())

    if window is None:
        start = int(df[study_day_col].min())
        end = int(df[study_day_col].max()) + 1
    else:
        start, end = int(window[0]), int(window[1])
    if end <= start:
        return MissingnessProfile(0, 0, 0, 0.0, 0, tuple())

    sub = df[(df[study_day_col] >= start) & (df[study_day_col] < end)][[study_day_col, value_col]].copy()
    observed_by_day = sub.groupby(study_day_col)[value_col].apply(lambda x: bool(x.notna().any())).to_dict()
    missing_days = [d for d in range(start, end) if not observed_by_day.get(d, False)]

    gaps: list[tuple[int, int]] = []
    if missing_days:
        g0 = prev = missing_days[0]
        for d in missing_days[1:]:
            if d == prev + 1:
                prev = d
            else:
                gaps.append((g0, prev))
                g0 = prev = d
        gaps.append((g0, prev))

    span = end - start
    n_missing = len(missing_days)
    n_observed = span - n_missing
    longest = max((b - a + 1 for a, b in gaps), default=0)
    return MissingnessProfile(
        span_days=span,
        n_observed=n_observed,
        n_missing=n_missing,
        missing_pct=round(n_missing / span * 100.0, 2),
        longest_gap_days=longest,
        gap_intervals=tuple(gaps),
    )


def persistent_deviation_events(
    dev: pd.DataFrame,
    *,
    magnitude_threshold: float = 2.0,
    min_observations: int = 3,
    require_consecutive_days: bool = True,
) -> list[PersistenceEvent]:
    """Detect sustained same-direction deviations from a baseline.

    This intentionally separates persistence from magnitude. A single large
    z-score can be an instantaneous deviation without becoming a regime event.
    """
    if dev.empty or "study_day" not in dev or "z" not in dev:
        return []
    d = dev[["study_day", "z"]].dropna().sort_values("study_day").copy()
    if d.empty:
        return []

    events: list[PersistenceEvent] = []
    current: list[tuple[int, float]] = []
    current_dir: Optional[int] = None

    def flush() -> None:
        nonlocal current, current_dir
        if current_dir is not None and len(current) >= min_observations:
            zs = [z for _, z in current]
            events.append(PersistenceEvent(
                start_study_day=current[0][0],
                end_study_day=current[-1][0],
                n_observations=len(current),
                direction=current_dir,
                threshold_abs_z=float(magnitude_threshold),
                max_abs_z=round(max(abs(z) for z in zs), 4),
                mean_z=round(float(np.mean(zs)), 4),
            ))
        current = []
        current_dir = None

    prev_day: Optional[int] = None
    for row in d.itertuples(index=False):
        day, z = int(row.study_day), float(row.z)
        direction = 1 if z >= magnitude_threshold else (-1 if z <= -magnitude_threshold else 0)
        day_break = require_consecutive_days and prev_day is not None and day != prev_day + 1
        if direction == 0 or day_break or (current_dir is not None and direction != current_dir):
            flush()
        if direction != 0:
            if current_dir is None:
                current_dir = direction
            current.append((day, z))
        prev_day = day
    flush()
    return events


def regime_evidence(
    dev: pd.DataFrame,
    *,
    magnitude_threshold: float = 2.0,
    persistence_min_observations: int = 3,
    require_consecutive_days: bool = True,
    analysis_mode: AnalysisMode = "retrospective",
) -> RegimeEvidence:
    """Return current magnitude evidence and persistence evidence separately."""
    if dev.empty or "study_day" not in dev or "z" not in dev:
        return RegimeEvidence(None, None, float(magnitude_threshold), False, False,
                              int(persistence_min_observations), None, analysis_mode)

    d = dev[["study_day", "z"]].dropna().sort_values("study_day")
    if d.empty:
        return RegimeEvidence(None, None, float(magnitude_threshold), False, False,
                              int(persistence_min_observations), None, analysis_mode)
    last = d.iloc[-1]
    latest_day = int(last["study_day"])
    latest_z = float(last["z"])
    instantaneous = abs(latest_z) >= magnitude_threshold

    events = persistent_deviation_events(
        d,
        magnitude_threshold=magnitude_threshold,
        min_observations=persistence_min_observations,
        require_consecutive_days=require_consecutive_days,
    )
    current_event = next((e for e in reversed(events) if e.end_study_day == latest_day), None)
    return RegimeEvidence(
        latest_study_day=latest_day,
        latest_z=round(latest_z, 4),
        magnitude_threshold_abs_z=float(magnitude_threshold),
        instantaneous_deviation=bool(instantaneous),
        persistent_deviation=(current_event is not None),
        persistence_min_observations=int(persistence_min_observations),
        current_persistent_event=current_event,
        analysis_mode=analysis_mode,
    )


def source_comparability_evidence(
    a: pd.DataFrame,
    b: pd.DataFrame,
    *,
    study_day_col: str = "study_day",
    a_value_col: str = "value",
    b_value_col: str = "value",
    min_overlap: int = 30,
) -> dict:
    """Describe overlap evidence between two measurement sources.

    This function deliberately does NOT decide that sources are interchangeable.
    It reports overlap, correlation and systematic difference so a domain-
    appropriate validation rule can decide whether pooling is justified.
    """
    aa = a[[study_day_col, a_value_col]].rename(columns={a_value_col: "a"})
    bb = b[[study_day_col, b_value_col]].rename(columns={b_value_col: "b"})
    pair = pd.merge(aa, bb, on=study_day_col, how="inner").dropna()
    n = int(len(pair))
    out = {
        "n_overlap": n,
        "min_overlap_requested": int(min_overlap),
        "minimum_overlap_met": bool(n >= min_overlap),
        "pearson_r": None,
        "mean_bias_b_minus_a": None,
        "mae": None,
        "rmse": None,
        "sd_ratio_b_over_a": None,
        "pooling_authorized": False,
        "notice": "Evidence only. Pooling requires an explicit domain-specific comparability decision.",
    }
    if n < 2:
        return out
    av = pair["a"].astype(float)
    bv = pair["b"].astype(float)
    diff = bv - av
    if av.std(ddof=1) > 0 and bv.std(ddof=1) > 0:
        out["pearson_r"] = round(float(av.corr(bv)), 4)
        out["sd_ratio_b_over_a"] = round(float(bv.std(ddof=1) / av.std(ddof=1)), 4)
    out["mean_bias_b_minus_a"] = round(float(diff.mean()), 4)
    out["mae"] = round(float(diff.abs().mean()), 4)
    out["rmse"] = round(float(np.sqrt(np.mean(np.square(diff)))), 4)
    return out
