"""IHB vNext evidence primitives for the Grounding Kernel.

Deterministic, within-entity, observed-data-first functions implementing
baseline diagnostics, missingness provenance, persistence/regime separation,
and source comparability evidence. These functions do not prescribe actions.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, Literal
import math
import numpy as np
import pandas as pd

AnalysisMode = Literal["prospective", "retrospective"]


@dataclass(frozen=True)
class BaselineDiagnostics:
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
        d = asdict(self); d["warnings"] = list(self.warnings); return d


@dataclass(frozen=True)
class MissingnessProfile:
    span_days: int
    n_observed: int
    n_missing: int
    missing_pct: float
    longest_gap_days: int
    gap_intervals: tuple[tuple[int, int], ...]
    def as_dict(self) -> dict:
        d = asdict(self); d["gap_intervals"] = [list(x) for x in self.gap_intervals]; return d


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


def _safe_float(value):
    try: x = float(value)
    except (TypeError, ValueError): return None
    return x if math.isfinite(x) else None


def baseline_diagnostics(df, study_day_col, value_col, window, *, min_n=14):
    start, end = window
    sub = df[(df[study_day_col] >= start) & (df[study_day_col] < end)][[study_day_col, value_col]].copy().sort_values(study_day_col)
    s = sub[value_col].dropna().astype(float)
    n = int(s.shape[0]); span = max(0, int(math.ceil(end - start)))
    completeness = round(n / span * 100.0, 2) if span else 0.0
    mean = _safe_float(s.mean()) if n else None
    sd = _safe_float(s.std(ddof=1)) if n > 1 else None
    lag1 = _safe_float(s.autocorr(lag=1)) if n >= 4 else None
    skew = _safe_float(s.skew()) if n >= 3 else None
    vr = None
    if n >= 8:
        split = n // 2; v1 = _safe_float(s.iloc[:split].var(ddof=1)); v2 = _safe_float(s.iloc[split:].var(ddof=1))
        if v1 and v2 and v1 > 0 and v2 > 0: vr = round(max(v1, v2) / min(v1, v2), 4)
    warnings = []
    if n < min_n: warnings.append("INSUFFICIENT_OBSERVED_BASELINE_N")
    if sd is None or sd == 0: warnings.append("ZERO_OR_UNDEFINED_BASELINE_VARIANCE")
    if completeness < 100: warnings.append("BASELINE_CONTAINS_MISSING_DAYS")
    return BaselineDiagnostics(n, span, completeness, mean, sd, round(lag1,4) if lag1 is not None else None,
                               round(skew,4) if skew is not None else None, vr, bool(sd is None or sd == 0), n >= min_n, tuple(warnings))


def missingness_profile(df, study_day_col, value_col, window=None):
    if df.empty: return MissingnessProfile(0,0,0,0.0,0,tuple())
    if window is None:
        start, end = int(df[study_day_col].min()), int(df[study_day_col].max()) + 1
    else: start, end = int(window[0]), int(window[1])
    if end <= start: return MissingnessProfile(0,0,0,0.0,0,tuple())
    sub = df[(df[study_day_col]>=start)&(df[study_day_col]<end)][[study_day_col,value_col]].copy()
    observed = sub.groupby(study_day_col)[value_col].apply(lambda x: bool(x.notna().any())).to_dict()
    miss = [d for d in range(start,end) if not observed.get(d,False)]
    gaps=[]
    if miss:
        g0=prev=miss[0]
        for d in miss[1:]:
            if d==prev+1: prev=d
            else: gaps.append((g0,prev)); g0=prev=d
        gaps.append((g0,prev))
    span=end-start; nm=len(miss)
    return MissingnessProfile(span, span-nm, nm, round(nm/span*100.0,2), max((b-a+1 for a,b in gaps),default=0), tuple(gaps))


def persistent_deviation_events(dev, *, magnitude_threshold=2.0, min_observations=3, require_consecutive_days=True):
    if dev.empty or "study_day" not in dev or "z" not in dev: return []
    d=dev[["study_day","z"]].dropna().sort_values("study_day")
    events=[]; current=[]; current_dir=None; prev_day=None
    def flush():
        nonlocal current,current_dir
        if current_dir is not None and len(current)>=min_observations:
            zs=[z for _,z in current]
            events.append(PersistenceEvent(current[0][0],current[-1][0],len(current),current_dir,float(magnitude_threshold),round(max(abs(z) for z in zs),4),round(float(np.mean(zs)),4)))
        current=[]; current_dir=None
    for row in d.itertuples(index=False):
        day,z=int(row.study_day),float(row.z)
        direction=1 if z>=magnitude_threshold else (-1 if z<=-magnitude_threshold else 0)
        day_break=require_consecutive_days and prev_day is not None and day!=prev_day+1
        if direction==0 or day_break or (current_dir is not None and direction!=current_dir): flush()
        if direction!=0:
            if current_dir is None: current_dir=direction
            current.append((day,z))
        prev_day=day
    flush(); return events


def regime_evidence(dev, *, magnitude_threshold=2.0, persistence_min_observations=3, require_consecutive_days=True, analysis_mode="retrospective"):
    if dev.empty or "study_day" not in dev or "z" not in dev:
        return {"latest_study_day":None,"latest_z":None,"magnitude_threshold_abs_z":float(magnitude_threshold),"instantaneous_deviation":False,"persistent_deviation":False,"persistence_min_observations":int(persistence_min_observations),"current_persistent_event":None,"analysis_mode":analysis_mode}
    d=dev[["study_day","z"]].dropna().sort_values("study_day"); last=d.iloc[-1]; latest_day=int(last["study_day"]); latest_z=float(last["z"])
    events=persistent_deviation_events(d,magnitude_threshold=magnitude_threshold,min_observations=persistence_min_observations,require_consecutive_days=require_consecutive_days)
    current=next((e for e in reversed(events) if e.end_study_day==latest_day),None)
    return {"latest_study_day":latest_day,"latest_z":round(latest_z,4),"magnitude_threshold_abs_z":float(magnitude_threshold),"instantaneous_deviation":abs(latest_z)>=magnitude_threshold,"persistent_deviation":current is not None,"persistence_min_observations":int(persistence_min_observations),"current_persistent_event":current.as_dict() if current else None,"analysis_mode":analysis_mode}


def source_comparability_evidence(a,b,*,study_day_col="study_day",a_value_col="value",b_value_col="value",min_overlap=30):
    aa=a[[study_day_col,a_value_col]].rename(columns={a_value_col:"a"}); bb=b[[study_day_col,b_value_col]].rename(columns={b_value_col:"b"})
    pair=pd.merge(aa,bb,on=study_day_col,how="inner").dropna(); n=int(len(pair))
    out={"n_overlap":n,"min_overlap_requested":int(min_overlap),"minimum_overlap_met":n>=min_overlap,"pearson_r":None,"mean_bias_b_minus_a":None,"mae":None,"rmse":None,"sd_ratio_b_over_a":None,"pooling_authorized":False,"notice":"Evidence only. Pooling requires an explicit domain-specific comparability decision."}
    if n<2: return out
    av=pair["a"].astype(float); bv=pair["b"].astype(float); diff=bv-av
    if av.std(ddof=1)>0 and bv.std(ddof=1)>0:
        out["pearson_r"]=round(float(av.corr(bv)),4); out["sd_ratio_b_over_a"]=round(float(bv.std(ddof=1)/av.std(ddof=1)),4)
    out["mean_bias_b_minus_a"]=round(float(diff.mean()),4); out["mae"]=round(float(diff.abs().mean()),4); out["rmse"]=round(float(np.sqrt(np.mean(np.square(diff)))),4)
    return out
