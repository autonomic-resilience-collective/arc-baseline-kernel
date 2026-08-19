"""IHB vNext state engine for the ARC Baseline Grounding Kernel.

This is the neutral measurement layer. It characterizes measured state relative
to an entity's own observed reference and reports evidence quality/provenance.
It does not prescribe treatment, purchasing, underwriting, ecological action, or
other domain decisions.

The v1 service remains available during transition. This v2 layer is isolated so
scientific hardening can be tested without silently changing existing clients.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

import pandas as pd

from ihb.core import compute_baseline, deviation_series
from ihb.vnext import baseline_diagnostics, missingness_profile, regime_evidence, source_comparability_evidence
from ihb_translator import translate as translate_csv, TranslationError


class VNextSubjectState:
    def __init__(
        self,
        subject_id: str,
        *,
        baseline_days: int = 90,
        min_baseline_n: int = 14,
        magnitude_threshold_abs_z: float = 2.0,
        persistence_min_observations: int = 3,
        require_consecutive_days: bool = True,
        segmentation_mode: str = "unspecified",
    ):
        if baseline_days < 1 or min_baseline_n < 2 or persistence_min_observations < 1:
            raise ValueError("Invalid vNext profile parameters")
        self.subject_id = subject_id
        self.profile = {
            "baseline_days": int(baseline_days),
            "min_baseline_n": int(min_baseline_n),
            "magnitude_threshold_abs_z": float(magnitude_threshold_abs_z),
            "persistence_min_observations": int(persistence_min_observations),
            "require_consecutive_days": bool(require_consecutive_days),
            "segmentation_mode": segmentation_mode,
            "profile_notice": "Development/domain profile; parameters require domain-specific validation before operational claims.",
        }
        self.registered_at = time.time()
        self._epochs: dict[str, dict] = {}
        self._active_epoch_id: Optional[str] = None
        self._active_source_key: Optional[str] = None
        self._epoch_counter = 0

    @staticmethod
    def _source_key(source: dict) -> str:
        material = {
            "vendor": source.get("vendor", "unknown"),
            "device_model": source.get("device_model", "unknown"),
            "algorithm_version": source.get("algorithm_version", "unknown"),
            "firmware_version": source.get("firmware_version", "unknown"),
            "metric_definition": source.get("metric_definition", ""),
            "source_id": source.get("source_id", ""),
        }
        return json.dumps(material, sort_keys=True, separators=(",", ":"))

    def _new_epoch(self, source: dict) -> str:
        self._epoch_counter += 1
        key = self._source_key(source)
        digest = hashlib.sha256(f"{self.subject_id}|{self._epoch_counter}|{key}".encode()).hexdigest()[:12]
        epoch_id = f"src-{self._epoch_counter:03d}-{digest}"
        self._epochs[epoch_id] = {
            "source_epoch_id": epoch_id,
            "source": {
                "source_id": source.get("source_id", ""),
                "vendor": source.get("vendor", "unknown"),
                "device_model": source.get("device_model", "unknown"),
                "algorithm_version": source.get("algorithm_version", "unknown"),
                "firmware_version": source.get("firmware_version", "unknown"),
                "metric_definition": source.get("metric_definition", ""),
            },
            "created_at": time.time(),
            "df": None,
            "push_count": 0,
        }
        self._active_epoch_id = epoch_id
        self._active_source_key = key
        return epoch_id

    def push_csv(
        self,
        csv_text: str,
        *,
        vendor: Optional[str] = None,
        anchor_date: Optional[str] = None,
        source_id: str = "",
        device_model: str = "unknown",
        algorithm_version: str = "unknown",
        firmware_version: str = "unknown",
        metric_definition: str = "",
        force_new_epoch: bool = False,
    ) -> dict:
        translated = translate_csv(csv_text, vendor=vendor, anchor_date=anchor_date, subject_id=self.subject_id)
        source = {
            "source_id": source_id,
            "vendor": translated.get("vendor") or vendor or "unknown",
            "device_model": device_model,
            "algorithm_version": algorithm_version,
            "firmware_version": firmware_version,
            "metric_definition": metric_definition,
        }
        key = self._source_key(source)
        if force_new_epoch or self._active_epoch_id is None or key != self._active_source_key:
            epoch_id = self._new_epoch(source)
            transition = True
        else:
            epoch_id = self._active_epoch_id
            transition = False

        epoch = self._epochs[epoch_id]
        new_df = pd.DataFrame(translated["rows"])
        if epoch["df"] is None:
            epoch["df"] = new_df
        else:
            combined = pd.concat([epoch["df"], new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset="study_day", keep="last").sort_values("study_day")
            epoch["df"] = combined.reset_index(drop=True)
        epoch["push_count"] += 1

        df = epoch["df"]
        return {
            "schema": "ihb.push.v2",
            "subject_id": self.subject_id,
            "source_epoch_id": epoch_id,
            "source_transition_created": transition,
            "source": epoch["source"],
            "n_study_days_in_epoch": int(df["study_day"].nunique()),
            "study_day_span": [int(df["study_day"].min()), int(df["study_day"].max())],
            "metrics_available": [c for c in df.columns if c != "study_day" and df[c].notna().any()],
            "anchor_date_stripped": translated.get("anchor_date_stripped", False),
            "input_sha256": translated.get("input_sha256"),
            "warnings": translated.get("warnings", []),
            "primary_record": "observed_only",
        }

    def query_state(self, metric: str, *, source_epoch_id: Optional[str] = None, analysis_mode: str = "prospective") -> dict:
        epoch_id = source_epoch_id or self._active_epoch_id
        if not epoch_id or epoch_id not in self._epochs:
            raise ValueError("No source epoch available. Push data first.")
        epoch = self._epochs[epoch_id]
        df = epoch["df"]
        if df is None or metric not in df.columns:
            raise ValueError(f"No data for metric '{metric}' in source epoch '{epoch_id}'.")

        valid = df[["study_day", metric]].dropna().sort_values("study_day")
        n_total = int(len(valid))
        if n_total < self.profile["min_baseline_n"]:
            return {
                "schema": "ihb.state.v2",
                "subject_id": self.subject_id,
                "metric": metric,
                "source_epoch_id": epoch_id,
                "status": "INSUFFICIENT_DATA",
                "n_valid": n_total,
                "min_required": self.profile["min_baseline_n"],
                "measurement_layer": "neutral",
            }

        lo = int(valid["study_day"].min())
        hi = lo + self.profile["baseline_days"]
        try:
            baseline = compute_baseline(valid, "study_day", metric, (lo, hi), metric, "", min_n=self.profile["min_baseline_n"])
        except ValueError as exc:
            return {
                "schema": "ihb.state.v2",
                "subject_id": self.subject_id,
                "metric": metric,
                "source_epoch_id": epoch_id,
                "status": "INSUFFICIENT_BASELINE",
                "message": str(exc),
                "measurement_layer": "neutral",
            }

        dev = deviation_series(valid, "study_day", metric, baseline)
        current = dev.iloc[-1]
        q = baseline_diagnostics(valid, "study_day", metric, (lo, hi), min_n=self.profile["min_baseline_n"])
        miss = missingness_profile(valid, "study_day", metric)
        regime = regime_evidence(
            dev,
            magnitude_threshold=self.profile["magnitude_threshold_abs_z"],
            persistence_min_observations=self.profile["persistence_min_observations"],
            require_consecutive_days=self.profile["require_consecutive_days"],
            analysis_mode=analysis_mode,
        )

        result = {
            "schema": "ihb.state.v2",
            "scope": "within-entity longitudinal",
            "measurement_layer": "neutral",
            "primary_record": "IHB-primary: observed data only",
            "subject_id": self.subject_id,
            "metric": metric,
            "source_epoch_id": epoch_id,
            "source": epoch["source"],
            "current_study_day": int(current["study_day"]),
            "current_value": round(float(current["value"]), 4),
            "baseline": baseline.as_dict(),
            "baseline_diagnostics": q.as_dict(),
            "deviation": {
                "z_score": round(float(current["z"]), 4),
                "pct_from_own_baseline": round(float(current["pct"]), 2),
                "direction": "positive" if float(current["z"]) >= 0 else "negative",
            },
            "regime_evidence": regime,
            "missingness": miss.as_dict(),
            "segmentation_provenance": {
                "mode": self.profile["segmentation_mode"],
                "outcome_metric_used_to_define_boundary": None,
                "notice": "No phase boundary is inferred by this query; persistence is evaluated on the observed sequence.",
            },
            "analysis_mode": analysis_mode,
            "domain_profile": self.profile,
            "interpretation_notice": "Descriptive measurement evidence only. Domain interpretation and action policy are downstream responsibilities.",
            "provider": "Autonomic Resilience Collective",
            "citation": "Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889",
        }
        canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
        result["result_fingerprint"] = hashlib.sha256(canonical.encode()).hexdigest()
        result["fingerprint_scope"] = "sha256_over_canonical_result_json_before_fingerprint"
        return result

    def list_epochs(self) -> list[dict]:
        out = []
        for epoch_id, epoch in self._epochs.items():
            df = epoch["df"]
            out.append({
                "source_epoch_id": epoch_id,
                "active": epoch_id == self._active_epoch_id,
                "source": epoch["source"],
                "push_count": epoch["push_count"],
                "n_rows": int(len(df)) if df is not None else 0,
                "study_day_span": ([int(df["study_day"].min()), int(df["study_day"].max())] if df is not None and not df.empty else None),
            })
        return out

    def compare_epochs(self, epoch_a: str, epoch_b: str, metric: str, *, min_overlap: int = 30) -> dict:
        if epoch_a not in self._epochs or epoch_b not in self._epochs:
            raise ValueError("Unknown source epoch")
        a = self._epochs[epoch_a]["df"]
        b = self._epochs[epoch_b]["df"]
        if a is None or b is None or metric not in a.columns or metric not in b.columns:
            raise ValueError(f"Metric '{metric}' is not present in both epochs")
        evidence = source_comparability_evidence(
            a[["study_day", metric]], b[["study_day", metric]],
            study_day_col="study_day", a_value_col=metric, b_value_col=metric, min_overlap=min_overlap,
        )
        return {
            "schema": "ihb.source_comparability.v2",
            "subject_id": self.subject_id,
            "metric": metric,
            "epoch_a": {"source_epoch_id": epoch_a, "source": self._epochs[epoch_a]["source"]},
            "epoch_b": {"source_epoch_id": epoch_b, "source": self._epochs[epoch_b]["source"]},
            "evidence": evidence,
            "decision": "NOT_AUTOMATICALLY_AUTHORIZED",
            "rule": "validate_before_harmonize",
        }


_registry: dict[str, VNextSubjectState] = {}


def register_v2(subject_id: str, **kwargs) -> VNextSubjectState:
    if subject_id in _registry:
        return _registry[subject_id]
    state = VNextSubjectState(subject_id, **kwargs)
    _registry[subject_id] = state
    return state


def get_v2(subject_id: str) -> Optional[VNextSubjectState]:
    return _registry.get(subject_id)


def list_v2() -> list[dict]:
    return [{"subject_id": sid, "source_epochs": st.list_epochs(), "profile": st.profile} for sid, st in _registry.items()]
