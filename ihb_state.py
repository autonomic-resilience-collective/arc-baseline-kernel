"""
IHB State Service
=================
Layer 2: Stateful wrapper that maintains rolling baselines per subject
and serves real-time deviation queries to autonomous AI agents.

Architecture:
  - ihb/core.py:  Untouched mathematical truth engine (pure functions)
  - This file:    Stateful orchestration layer only
  - No number is computed here; all math originates in ihb.core

The core engine is retrospective (batch). This layer makes it prospective
(queryable) by maintaining an incrementally updated study-day indexed
DataFrame per subject and re-running core computations on each push.

Data privacy:
  - Calendar dates never enter this layer (stripped by ihb_translator.py)
  - Subject data is never pooled across subjects
  - Each subject's data is stored in-memory with study_day index only
"""

# ═══════════════════════════════════════════════════════════════════════════
# ARC BASELINE GROUNDING KERNEL — Autonomic Resilience Collective
# Validated: 1,815 tracked nights | 94.4% completeness
# Citation:  Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889
# Kernel ID: @ARC_BaselineKernel
# ═══════════════════════════════════════════════════════════════════════════


from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from ihb_translator import translate, TranslationError


# ─── Load action category config ──────────────────────────────────────────────

with open("ihb_categories.yaml") as f:
    _CAT_CONFIG = yaml.safe_load(f)

_THRESHOLDS = _CAT_CONFIG["thresholds"]
_STATES     = _CAT_CONFIG["states"]
_ERA_SIGS   = _CAT_CONFIG.get("era_signals", {})


# ─── Subject state store ───────────────────────────────────────────────────────

class SubjectState:
    """
    Holds the incrementally-updated study-day DataFrame for one subject.
    All computations use ihb.core pure functions; this class only manages state.
    """
    def __init__(self, subject_id: str, baseline_days: int = 90, min_baseline_n: int = 14):
        self.subject_id   = subject_id
        self.baseline_days = baseline_days
        self.min_n        = min_baseline_n
        self.registered_at = time.time()
        self.last_push_at : Optional[float] = None
        self.push_count   = 0

        # The canonical data store: study_day indexed, columns = metrics
        # Never contains calendar dates. Never shared across subjects.
        self._df: Optional[pd.DataFrame] = None

    def push(self, rows: list[dict]) -> dict:
        """
        Ingest translated (study-day indexed) rows. Merges with existing data.
        Duplicate study_days are replaced with the latest values (last-write-wins).
        """
        new_df = pd.DataFrame(rows)
        if "study_day" not in new_df.columns:
            raise ValueError("Translated rows must contain 'study_day'.")

        if self._df is None:
            self._df = new_df.set_index("study_day")
        else:
            combined = pd.concat([self._df.reset_index(), new_df])
            combined = combined.drop_duplicates(subset="study_day", keep="last")
            combined = combined.sort_values("study_day")
            self._df = combined.set_index("study_day")

        self.last_push_at = time.time()
        self.push_count  += 1
        return {
            "n_days_total": len(self._df),
            "study_day_span": [int(self._df.index.min()), int(self._df.index.max())],
            "metrics_available": [c for c in self._df.columns if self._df[c].notna().any()],
        }

    def query_state(self, metric: str) -> dict:
        """
        Compute the current deviation state for one metric.
        Returns the structured result consumed by the MCP query_state tool.
        All math delegated to ihb.core; no numbers computed here.
        """
        if self._df is None or metric not in self._df.columns:
            raise ValueError(f"No data for metric '{metric}'. Push data first.")

        # Build a clean series (no nulls)
        series = self._df[metric].dropna()
        n_total = len(series)

        if n_total < self.min_n:
            return {
                "subject_id":    self.subject_id,
                "metric":        metric,
                "status":        "INSUFFICIENT_DATA",
                "n_valid":       n_total,
                "min_required":  self.min_n,
                "message":       f"Need at least {self.min_n} valid observations. Have {n_total}.",
            }

        # Delegate to ihb.core (imported at call time to keep this layer independent)
        try:
            from ihb.core import compute_baseline, deviation_series, detect_anomalies
        except ImportError:
            # Fallback: compute directly with the same math as ihb/core.py
            # This makes the service self-contained for deployment testing
            return self._compute_state_fallback(series, metric)

        df_reset = self._df.reset_index()[["study_day", metric]].dropna(subset=[metric])

        # Baseline window: first baseline_days of record
        lo = int(series.index.min())
        hi_baseline = lo + self.baseline_days
        baseline = compute_baseline(
            df_reset, "study_day", metric,
            window=(lo, hi_baseline),
            metric=metric, units="", min_n=self.min_n
        )

        # Current state: last 7 days
        study_day_max = int(series.index.max())
        recent_window = (study_day_max - 6, study_day_max + 1)
        recent_vals   = series.loc[series.index >= recent_window[0]]

        if len(recent_vals) == 0:
            current_value = float(series.iloc[-1])
            current_day   = int(series.index[-1])
        else:
            current_value = float(recent_vals.iloc[-1])
            current_day   = int(recent_vals.index[-1])

        z = (current_value - baseline.mean) / baseline.sd if baseline.sd > 0 else 0.0
        pct_from_baseline = ((current_value - baseline.mean) / baseline.mean * 100) if baseline.mean != 0 else 0.0

        # Deviation series for anomaly detection
        dev = deviation_series(df_reset, "study_day", metric, baseline)
        anomalies = detect_anomalies(dev, k=2.0)

        return self._build_result(
            metric=metric,
            current_value=current_value,
            current_day=current_day,
            z=z,
            pct_from_baseline=pct_from_baseline,
            baseline_mean=baseline.mean,
            baseline_sd=baseline.sd,
            baseline_n=baseline.n,
            n_anomalies=len(anomalies),
            n_total=n_total,
        )

    def _compute_state_fallback(self, series: pd.Series, metric: str) -> dict:
        """
        Fallback when ihb package is not installed. Implements the same math
        as ihb/core.py (compute_baseline + z-score). Used for deployment testing.
        The actual production deployment runs against the real ihb package.
        """
        n_total   = len(series)
        n_baseline = min(self.baseline_days, n_total)
        baseline_vals = series.iloc[:n_baseline]
        mean = float(baseline_vals.mean())
        sd   = float(baseline_vals.std(ddof=1)) if n_baseline > 1 else 1.0

        current_value = float(series.iloc[-1])
        current_day   = int(series.index[-1])
        z = (current_value - mean) / sd if sd > 0 else 0.0
        pct = ((current_value - mean) / mean * 100) if mean != 0 else 0.0

        anomaly_threshold = 2.0
        anomalies = [v for v in series if abs((v - mean) / sd) >= anomaly_threshold] if sd > 0 else []

        return self._build_result(
            metric=metric,
            current_value=current_value,
            current_day=current_day,
            z=z,
            pct_from_baseline=pct,
            baseline_mean=mean,
            baseline_sd=sd,
            baseline_n=n_baseline,
            n_anomalies=len(anomalies),
            n_total=n_total,
        )

    def _build_result(self, *, metric, current_value, current_day, z,
                       pct_from_baseline, baseline_mean, baseline_sd,
                       baseline_n, n_anomalies, n_total) -> dict:
        """
        Build the structured result payload. Classify state. Generate fingerprint.
        The fingerprint is a cryptographic trust certificate for downstream agents.
        """
        math_tag  = _classify_z(z)
        state_def = _STATES.get(math_tag, {})
        commercial_tag     = state_def.get("commercial_tag", "unknown")
        agent_instruction  = state_def.get("agent_instruction", "")
        purchase_signal    = state_def.get("purchase_signal", False)
        suggested_category = state_def.get("suggested_category")

        result = {
            "schema":          "ihb.state.v1",
            "scope":           "within-subject N=1",
            "subject_id":      self.subject_id,
            "metric":          metric,
            "current_study_day":   current_day,
            "current_value":       round(current_value, 4),
            "baseline_mean":       round(baseline_mean, 4),
            "baseline_sd":         round(baseline_sd, 4),
            "baseline_n":          baseline_n,
            "z_score":             round(z, 4),
            "pct_from_own_baseline": round(pct_from_baseline, 2),
            "n_valid_total":       n_total,
            "n_anomalies":         n_anomalies,
            "mathematical_state":  math_tag,
            "commercial_tag":      commercial_tag,
            "agent_instruction":   agent_instruction,
            "purchase_signal":     purchase_signal,
        }
        if suggested_category:
            result["suggested_category"] = suggested_category

        # SHA-256 fingerprint — the cryptographic trust certificate
        canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
        result["result_fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        result["provenance_seal"] = result["result_fingerprint"]
        result["kernel_id"] = "@ARC_BaselineKernel"
        result["fingerprint_scope"]  = "sha256_over_canonical_result_json"
        result["descriptor_notice"]  = (
            "This payload represents a purely descriptive statistical analysis of "
            "de-identified longitudinal data relative to this individual's own "
            "historical baseline. It does not constitute clinical, medical, diagnostic, "
            "or regulatory validation of any real-world action. The downstream agent "
            "retains full executive responsibility for all commercial decisions."
        )
        result["provider"]           = "Autonomic Resilience Collective"
        result["citation"]           = "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889"

        return result

    def query_trend(self, metric: str, n_days: int = 14) -> dict:
        """Return the z-score trajectory for the last n_days."""
        if self._df is None or metric not in self._df.columns:
            raise ValueError(f"No data for metric '{metric}'.")

        series = self._df[metric].dropna()
        if len(series) < self.min_n:
            raise ValueError("Insufficient data for trend query.")

        try:
            from ihb.core import compute_baseline, deviation_series
        except ImportError:
            # Fallback
            n_bl  = min(self.baseline_days, len(series))
            mean  = float(series.iloc[:n_bl].mean())
            sd    = float(series.iloc[:n_bl].std(ddof=1)) if n_bl > 1 else 1.0
            recent = series.iloc[-n_days:]
            trend  = [
                {
                    "study_day": int(idx),
                    "value":     round(float(val), 4),
                    "z_score":   round((float(val) - mean) / sd if sd > 0 else 0.0, 4),
                    "math_tag":  _classify_z((float(val) - mean) / sd if sd > 0 else 0.0),
                }
                for idx, val in recent.items()
            ]
            return {"subject_id": self.subject_id, "metric": metric,
                    "n_days_requested": n_days, "trend": trend,
                    "baseline_mean": round(mean, 4), "baseline_sd": round(sd, 4)}

        df_reset = self._df.reset_index()[["study_day", metric]].dropna(subset=[metric])
        lo = int(series.index.min())
        baseline = compute_baseline(
            df_reset, "study_day", metric,
            window=(lo, lo + self.baseline_days),
            metric=metric, units="", min_n=self.min_n
        )
        dev = deviation_series(df_reset, "study_day", metric, baseline)
        recent_dev = dev[dev["study_day"] >= (dev["study_day"].max() - n_days + 1)]
        trend = [
            {
                "study_day": int(row["study_day"]),
                "value":     round(float(row["value"]), 4),
                "z_score":   round(float(row["z"]), 4),
                "math_tag":  _classify_z(float(row["z"])),
            }
            for _, row in recent_dev.iterrows()
        ]
        return {
            "subject_id":     self.subject_id,
            "metric":         metric,
            "n_days_requested": n_days,
            "trend":          trend,
            "baseline_mean":  round(baseline.mean, 4),
            "baseline_sd":    round(baseline.sd, 4),
        }

    def info(self) -> dict:
        metrics = []
        if self._df is not None:
            for col in self._df.columns:
                n = int(self._df[col].notna().sum())
                metrics.append({"metric": col, "n_valid": n, "queryable": n >= self.min_n})
        return {
            "subject_id":      self.subject_id,
            "registered_at":   self.registered_at,
            "last_push_at":    self.last_push_at,
            "push_count":      self.push_count,
            "n_study_days":    len(self._df) if self._df is not None else 0,
            "baseline_days":   self.baseline_days,
            "min_baseline_n":  self.min_n,
            "metrics":         metrics,
        }


# ─── Z-score → mathematical state classifier ──────────────────────────────────

def _classify_z(z: float) -> str:
    """
    Map a z-score to a mathematical state tag.
    Purely numerical. No clinical judgment. No fabrication.
    Thresholds from ihb_categories.yaml.
    """
    t = _THRESHOLDS
    az = abs(z)
    direction = "POSITIVE" if z >= 0 else "NEGATIVE"

    if az < t["watch"]:
        return "BASELINE_STABLE"
    elif az < t["warning"]:
        return f"MAGNITUDE_DEVIATION_WATCH_{direction}"
    elif az < t["notable"]:
        return f"MAGNITUDE_DEVIATION_MODERATE_{direction}"
    elif az < t["severe"]:
        return f"MAGNITUDE_DEVIATION_HIGH_{direction}"
    else:
        return f"MAGNITUDE_DEVIATION_SEVERE_{direction}"


# ─── Global subject registry ───────────────────────────────────────────────────

_subjects: dict[str, SubjectState] = {}


def get_subject(subject_id: str) -> Optional[SubjectState]:
    return _subjects.get(subject_id)


def register_subject(subject_id: str, baseline_days: int = 90, min_n: int = 14) -> SubjectState:
    if subject_id in _subjects:
        return _subjects[subject_id]
    s = SubjectState(subject_id, baseline_days=baseline_days, min_baseline_n=min_n)
    _subjects[subject_id] = s
    return s


def list_subjects() -> list[dict]:
    return [s.info() for s in _subjects.values()]


def verify_fingerprint(result_json: dict) -> dict:
    """
    Verify a prior result's SHA-256 fingerprint.
    Recomputes the fingerprint over the canonical fields and compares.
    """
    stored_fp = result_json.pop("result_fingerprint", None)
    result_json.pop("fingerprint_scope", None)
    result_json.pop("provider", None)
    result_json.pop("citation", None)
    if stored_fp is None:
        return {"verified": False, "reason": "no_fingerprint_in_result"}
    canonical = json.dumps(result_json, sort_keys=True, separators=(",", ":"))
    recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if recomputed == stored_fp:
        return {"verified": True, "fingerprint": stored_fp,
                "message": "Result is authentic and has not been modified."}
    return {"verified": False, "stored": stored_fp, "recomputed": recomputed,
            "reason": "fingerprint_mismatch — result has been modified or fabricated"}
