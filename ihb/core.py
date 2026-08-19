"""
ihb.core - The Individualized Homeostatic Baseline computation.

This module is the reference implementation of the IHB method. It is pure,
deterministic code. It performs no file I/O, no plotting, and calls no AI.
Given the same inputs it always returns the same outputs.

DESIGN RULE (do not break this): every number an IHB report ever shows must
originate here. Narrative, formatting, and presentation happen elsewhere and
only ever consume values this module has already computed. Nothing downstream
is permitted to estimate, infer, or regenerate a number.

The method is within-subject. Every statistic is expressed relative to the
individual's own baseline, never to a population. There is no external
reference distribution anywhere in this file, by design.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional
import math

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Baseline:
    """An individual's homeostatic baseline for one metric, from one window."""
    metric: str
    units: str
    window_start: float          # study-day, inclusive
    window_end: float            # study-day, exclusive
    n: int
    mean: float
    sd: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PhaseStat:
    """Within-subject summary of one labelled phase against the baseline."""
    name: str
    start: float                 # study-day, inclusive
    end: float                   # study-day, exclusive
    n: int
    mean: float
    sd: float
    ci95_low: float
    ci95_high: float
    pct_vs_baseline: float       # signed % deviation of the phase mean
    z_of_mean: float             # phase mean expressed in individual baseline SDs

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Window selection
# --------------------------------------------------------------------------

def select_window(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    start: float,
    end: float,
) -> pd.Series:
    """Return valid (non-null) metric values with study_day in [start, end).

    Half-open intervals so that adjacent phases never double-count a day.
    """
    mask = (df[study_day_col] >= start) & (df[study_day_col] < end)
    return df.loc[mask, value_col].dropna()


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------

def compute_baseline(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    window: tuple[float, float],
    metric: str,
    units: str,
    min_n: int = 14,
) -> Baseline:
    """Compute the individual baseline (mean and SD) from a chosen window.

    Fails loud: if the window contains fewer than `min_n` valid observations
    the baseline is not trustworthy and we refuse rather than return a fragile
    number. A bad baseline silently corrupts every downstream statistic.
    """
    start, end = window
    s = select_window(df, study_day_col, value_col, start, end)
    n = int(s.shape[0])
    if n < min_n:
        raise ValueError(
            f"Baseline window [{start}, {end}) for '{metric}' has only {n} valid "
            f"observations; need at least {min_n}. Widen the window or check the data. "
            f"Refusing to compute an untrustworthy baseline."
        )
    return Baseline(
        metric=metric,
        units=units,
        window_start=float(start),
        window_end=float(end),
        n=n,
        mean=float(s.mean()),
        sd=float(s.std(ddof=1)),
    )


# --------------------------------------------------------------------------
# Phase statistics
# --------------------------------------------------------------------------

def compute_phase(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    name: str,
    start: float,
    end: float,
    baseline: Baseline,
) -> Optional[PhaseStat]:
    """Summarise one phase relative to the individual baseline.

    Returns None for an empty phase (no valid observations in the window),
    so callers can simply skip phases the subject has no data for rather than
    emitting misleading zero-count rows.
    """
    s = select_window(df, study_day_col, value_col, start, end)
    n = int(s.shape[0])
    if n == 0:
        return None

    mean = float(s.mean())
    sd = float(s.std(ddof=1)) if n > 1 else 0.0
    ci = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0

    pct = (mean - baseline.mean) / baseline.mean * 100.0
    z = (mean - baseline.mean) / baseline.sd if baseline.sd > 0 else 0.0

    return PhaseStat(
        name=name,
        start=float(start),
        end=float(end),
        n=n,
        mean=round(mean, 1),
        sd=round(sd, 1),
        ci95_low=round(mean - ci, 1),
        ci95_high=round(mean + ci, 1),
        pct_vs_baseline=round(pct, 1),
        z_of_mean=round(z, 2),
    )


def compute_phases(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    phases: list[dict],
    baseline: Baseline,
) -> list[PhaseStat]:
    """Summarise an ordered list of phases. Empty phases are dropped."""
    out: list[PhaseStat] = []
    for p in phases:
        ps = compute_phase(
            df, study_day_col, value_col,
            name=p["name"], start=p["start"], end=p["end"],
            baseline=baseline,
        )
        if ps is not None:
            out.append(ps)
    return out


# --------------------------------------------------------------------------
# Per-observation deviation and anomaly scoring
# --------------------------------------------------------------------------

def deviation_series(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    baseline: Baseline,
) -> pd.DataFrame:
    """Return per-observation deviation scores against the individual baseline.

    Columns: study_day, value, z (deviation in individual baseline SDs),
    pct (signed % deviation from the individual baseline mean).
    """
    d = df[[study_day_col, value_col]].dropna(subset=[value_col]).copy()
    d = d.rename(columns={study_day_col: "study_day", value_col: "value"})
    if baseline.sd > 0:
        d["z"] = (d["value"] - baseline.mean) / baseline.sd
    else:
        d["z"] = 0.0
    d["pct"] = (d["value"] - baseline.mean) / baseline.mean * 100.0
    return d.sort_values("study_day").reset_index(drop=True)


def detect_anomalies(
    dev: pd.DataFrame,
    k: float = 2.0,
) -> pd.DataFrame:
    """Flag observations whose deviation exceeds +/- k individual SDs.

    Returns the flagged rows with a 'direction' column (+1 above baseline,
    -1 below). Anomaly here means 'unusual for this person', not 'abnormal'
    against any population.
    """
    flagged = dev[dev["z"].abs() >= k].copy()
    flagged["direction"] = np.sign(flagged["z"]).astype(int)
    return flagged.reset_index(drop=True)


# --------------------------------------------------------------------------
# Completeness
# --------------------------------------------------------------------------

def completeness(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
) -> dict:
    """Coverage of the observation span: valid nights vs the full day range."""
    days = df[study_day_col]
    span = int(days.max() - days.min()) + 1
    n_valid = int(df[value_col].notna().sum())
    pct = round(n_valid / span * 100.0, 1) if span > 0 else 0.0
    return {
        "span_days": span,
        "n_valid": n_valid,
        "completeness_pct": pct,
        "first_study_day": int(days.min()),
        "last_study_day": int(days.max()),
    }


# --------------------------------------------------------------------------
# Rolling baseline (the everyday, no-event mode)
# --------------------------------------------------------------------------

def rolling_baseline(
    df: pd.DataFrame,
    study_day_col: str,
    value_col: str,
    *,
    baseline_days: int = 90,
    recent_days: int = 14,
    gap_days: int = 0,
    min_obs: int = 20,
) -> pd.DataFrame:
    """Score every day against the subject's own recent self.

    For each day, the baseline is a trailing window of `baseline_days` ending
    just before the recent window, and the current state is the average of the
    last `recent_days`. Deviation is reported as % and as individual SDs (z).

    This is the no-event mode: nothing is anchored, nothing is compared to a
    population, the reference simply moves with the person. Setting recent_days=1
    scores each single day against its own trailing baseline; larger values
    smooth toward an Oura-style 'recent trend vs longer baseline' comparison.

    Windows are measured in CALENDAR days, not in number of observations, so gaps
    in wear time do not distort the window length. Days without enough trailing
    history yield no score yet (the same way Oura takes ~2 weeks to 'learn' you),
    which is correct rather than a failure.
    """
    d = df[[study_day_col, value_col]].dropna(subset=[value_col]).copy()
    d = d.sort_values(study_day_col)
    s = d.set_index(study_day_col)[value_col]

    earliest = int(s.index.min())  # first real observation day

    full = pd.RangeIndex(earliest, int(s.index.max()) + 1)
    s = s.reindex(full)  # continuous daily axis; missing days are NaN

    recent = s.rolling(recent_days, min_periods=1).mean() if recent_days > 1 else s
    shift = recent_days + gap_days
    prior = s.shift(shift)
    base_mean = prior.rolling(baseline_days, min_periods=min_obs).mean()
    base_sd = prior.rolling(baseline_days, min_periods=min_obs).std(ddof=1)

    out = pd.DataFrame({
        "study_day": full,
        "value": recent.values,
        "base_mean": base_mean.values,
        "base_sd": base_sd.values,
    })

    # Fail-quiet guard: only score a day whose baseline window genuinely reaches
    # back the full `baseline_days`. min_obs alone can be satisfied by a cluster
    # of observations far narrower than baseline_days, which would silently score
    # against a truncated baseline mislabelled as `baseline_days` long. The first
    # scorable day is the earliest day whose baseline window starts at or after
    # the first real observation.
    min_scorable_day = earliest + shift + baseline_days - 1
    out = out[out["study_day"] >= min_scorable_day]

    # A baseline with no spread (or too few points for an SD) cannot produce a
    # meaningful deviation; drop rather than emit inf/NaN.
    out = out[out["base_sd"] > 0]

    out["pct"] = (out["value"] - out["base_mean"]) / out["base_mean"] * 100.0
    out["z"] = (out["value"] - out["base_mean"]) / out["base_sd"]
    out = out.dropna(subset=["value", "base_mean", "base_sd", "pct", "z"]).reset_index(drop=True)
    return out


def rolling_state(roll: pd.DataFrame, k: float = 2.0) -> dict:
    """A small 'where am I right now' summary a companion could speak from.

    Reports the latest standing, the share of scored days spent above/within/
    below the person's own moving baseline, and the current consecutive run on
    one side. All within-subject; no population anywhere.
    """
    if roll.empty:
        return {"available": False}

    above = (roll["z"] >= k).mean() * 100.0
    below = (roll["z"] <= -k).mean() * 100.0
    within = 100.0 - above - below

    def _standing(z: float) -> str:
        return "above" if z >= k else ("below" if z <= -k else "within")

    standings = [_standing(z) for z in roll["z"]]
    standing = standings[-1]
    # consecutive days ending now in the SAME standing as the latest day, so the
    # reported run matches the standing label rather than mixing two meanings.
    run = 1
    for i in range(len(standings) - 1, 0, -1):
        if standings[i] == standings[i - 1]:
            run += 1
        else:
            break

    last = roll.iloc[-1]

    return {
        "available": True,
        "latest_study_day": int(last["study_day"]),
        "latest_value": round(float(last["value"]), 1),
        "latest_base_mean": round(float(last["base_mean"]), 1),
        "latest_pct": round(float(last["pct"]), 1),
        "latest_z": round(float(last["z"]), 2),
        "standing": standing,
        "current_run_days": int(run),
        "pct_days_above": round(float(above), 1),
        "pct_days_within": round(float(within), 1),
        "pct_days_below": round(float(below), 1),
    }
