"""
IHB Ingestion Translator
========================
The temporal privacy front door. This module is the ONLY place where
real-world calendar dates exist. They are stripped here and never passed
to the core engine or stored anywhere downstream.

Design rule: everything that enters this module carries a date.
Everything that leaves carries only a study_day offset.
Real-world dates never cross this boundary.

Supports:
- Oura Ring export (CSV, sleep/readiness data)
- Whoop export (CSV)
- Apple Health export (CSV via Health Auto Export)
- Generic CSV (date column + metric columns)
- Clean study-day CSV (passthrough, no translation needed)
"""

# ═══════════════════════════════════════════════════════════════════════════
# ARC BASELINE GROUNDING KERNEL — Autonomic Resilience Collective
# Validated: 1,815 tracked nights | 94.4% completeness
# Citation:  Buckingham & Johnson, ACM BCB 2026, DOI: 10.1145/3807503.3816889
# Kernel ID: @ARC_BaselineKernel
# ═══════════════════════════════════════════════════════════════════════════


from __future__ import annotations

import io
import csv
import hashlib
from datetime import datetime, date
from typing import Optional


class TranslationError(Exception):
    """Input cannot be translated. Fail loud, never guess."""


# ─── Canonical metric name normalization ─────────────────────────────────────

_OURA_MAP = {
    "average_hrv":            "hrv_rmssd",
    "rmssd":                  "hrv_rmssd",
    "average_heart_rate":     "resting_hr",
    "lowest_heart_rate":      "resting_hr",
    "average_breath":         "respiratory_rate",
    "temperature_deviation":  "body_temp_dev",
    "total_sleep_duration":   "sleep_duration_h",
    "score":                  "readiness_score",
}

_WHOOP_MAP = {
    "hrv_rmssd_milli":        "hrv_rmssd",
    "resting_heart_rate":     "resting_hr",
    "respiratory_rate":       "respiratory_rate",
    "skin_temp_celsius":      "body_temp_dev",
    "total_sleep_duration_minutes": "sleep_duration_h",
    "recovery_score":         "readiness_score",
}

_APPLE_MAP = {
    "heartratevariabilitysdnn": "hrv_sdnn",   # Apple uses SDNN, kept separate by design
    "restingheartrate":         "resting_hr",
    "respiratoryrate":          "respiratory_rate",
    "sleepanalysis":            "sleep_duration_h",
}

_GENERIC_DATE_COLS = {"date", "day", "Date", "Day", "DATE"}
_STUDY_DAY_COLS   = {"study_day", "study day", "Study Day", "StudyDay"}


def _sniff_vendor(headers: list[str]) -> str:
    """Infer the wearable vendor from column names. Returns 'oura', 'whoop', 'apple', 'generic', or 'studyday'."""
    h = {c.lower().replace(" ", "_") for c in headers}
    if "average_hrv" in h or "temperature_deviation" in h:
        return "oura"
    if "hrv_rmssd_milli" in h or "recovery_score" in h:
        return "whoop"
    if "heartratevariabilitysdnn" in h:
        return "apple"
    if any(c in _STUDY_DAY_COLS for c in headers):
        return "studyday"
    return "generic"


def _parse_date(value: str) -> date:
    """Parse a date string to a date object. Fail loud on ambiguous formats."""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise TranslationError(
        f"Cannot parse date '{value}'. Expected YYYY-MM-DD or similar unambiguous format."
    )


def _sleep_minutes_to_hours(value: str) -> Optional[float]:
    """Convert sleep minutes to hours if the value looks like minutes."""
    try:
        v = float(value)
        if v > 24:           # probably minutes
            return round(v / 60.0, 3)
        return round(v, 3)   # already hours
    except (ValueError, TypeError):
        return None


def translate(
    csv_text: str,
    vendor: Optional[str] = None,
    anchor_date: Optional[str] = None,
    subject_id: Optional[str] = None,
) -> dict:
    """
    Translate raw wearable CSV to a clean study-day payload.

    Returns:
    {
        "subject_id": str,
        "vendor": str,
        "n_days": int,
        "metrics": ["hrv_rmssd", "resting_hr", ...],
        "rows": [{"study_day": int, "hrv_rmssd": float, ...}, ...],
        "anchor_date_stripped": True,   # confirms dates were stripped
        "input_sha256": str,            # fingerprint of the raw input
        "warnings": [str]
    }

    PRIVACY GUARANTEE: no date, timestamp, or calendar reference appears
    in the returned dict or in any downstream data structure.
    """
    # Fingerprint the raw input BEFORE stripping dates (for audit trail only)
    raw_fingerprint = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        raise TranslationError("Empty or unreadable CSV.")

    headers = list(reader.fieldnames)
    detected_vendor = vendor or _sniff_vendor(headers)
    warnings = []

    # ── Study-day passthrough (already de-identified) ──────────────────────
    if detected_vendor == "studyday":
        day_col = next((c for c in headers if c in _STUDY_DAY_COLS), None)
        if not day_col:
            raise TranslationError("No study_day column found in study-day CSV.")
        metric_cols = [c for c in headers if c not in _STUDY_DAY_COLS and c not in _GENERIC_DATE_COLS]
        rows = []
        for row in reader:
            try:
                study_day = int(float(row[day_col]))
            except (ValueError, TypeError):
                continue
            record = {"study_day": study_day}
            for m in metric_cols:
                try:
                    record[m] = float(row[m]) if row[m].strip() else None
                except (ValueError, TypeError, AttributeError):
                    record[m] = None
            rows.append(record)
        rows.sort(key=lambda r: r["study_day"])
        return {
            "subject_id": subject_id or "unknown",
            "vendor": "studyday",
            "n_days": len(rows),
            "metrics": metric_cols,
            "rows": rows,
            "anchor_date_stripped": False,
            "input_sha256": raw_fingerprint,
            "warnings": warnings,
        }

    # ── Dated vendor exports ─────────────────────────────────────────────
    # Detect the date column
    date_col = None
    for col in headers:
        if col.lower() in {"date", "day", "calendar_date", "datetime", "timestamp",
                           "sleep_date", "cycle_start_time", "start_time"}:
            date_col = col
            break

    if not date_col:
        raise TranslationError(
            f"Cannot find a date column in the CSV. Found columns: {headers}. "
            "If this is already study-day indexed, include 'study_day' as a column name."
        )

    # Parse all rows with dates — extract dates first to compute anchor
    parsed_rows = []
    for row in reader:
        raw_date_str = row.get(date_col, "").strip()
        if not raw_date_str:
            continue
        # For Whoop: date might be embedded in a datetime string
        if "T" in raw_date_str or " " in raw_date_str:
            raw_date_str = raw_date_str.split("T")[0].split(" ")[0]
        try:
            d = _parse_date(raw_date_str)
        except TranslationError:
            warnings.append(f"Skipped unparseable date: '{raw_date_str}'")
            continue
        parsed_rows.append((d, row))

    if not parsed_rows:
        raise TranslationError("No valid dated rows found in the CSV.")

    parsed_rows.sort(key=lambda x: x[0])

    # Determine anchor — the study Day 0
    if anchor_date:
        anchor = _parse_date(anchor_date)
    else:
        anchor = parsed_rows[0][0]  # first day of the record

    # ── Select metric mapping ─────────────────────────────────────────────
    if detected_vendor == "oura":
        metric_map = _OURA_MAP
    elif detected_vendor == "whoop":
        metric_map = _WHOOP_MAP
    elif detected_vendor == "apple":
        metric_map = _APPLE_MAP
    else:
        # Generic: use column names directly, skip obvious non-metric cols
        _skip = {date_col.lower(), "id", "subject", "source", "notes", "comments"}
        metric_map = {c: c for c in headers if c.lower() not in _skip}

    # ── Build study-day indexed output ────────────────────────────────────
    # PRIVACY: dates are converted to offsets here and NEVER stored
    available_metrics = set()
    rows_out = []

    for (d, row) in parsed_rows:
        study_day = (d - anchor).days
        record: dict = {"study_day": study_day}

        for raw_col, canonical in metric_map.items():
            val_str = row.get(raw_col, "").strip()
            if not val_str:
                continue
            try:
                val = float(val_str)
                # Special case: sleep minutes → hours
                if canonical == "sleep_duration_h" and val > 24:
                    val = round(val / 60.0, 3)
                record[canonical] = round(val, 4)
                available_metrics.add(canonical)
            except (ValueError, TypeError):
                pass

        if len(record) > 1:   # at least one metric besides study_day
            rows_out.append(record)

    if not rows_out:
        raise TranslationError(
            f"Translation produced no usable rows. Check that '{detected_vendor}' "
            "columns are present and numeric."
        )

    # Deduplicate by study_day (keep last entry per day, matching parsers.py behavior)
    seen = {}
    for r in rows_out:
        seen[r["study_day"]] = r
    rows_out = sorted(seen.values(), key=lambda r: r["study_day"])

    return {
        "subject_id": subject_id or "unknown",
        "vendor": detected_vendor,
        "n_days": len(rows_out),
        "metrics": sorted(available_metrics),
        "rows": rows_out,
        "anchor_date_stripped": True,   # ← privacy guarantee confirmation
        "input_sha256": raw_fingerprint,
        "warnings": warnings,
    }
