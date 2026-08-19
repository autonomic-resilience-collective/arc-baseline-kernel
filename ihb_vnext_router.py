"""FastAPI router for IHB state schema v2."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ihb_vnext_state import register_v2, get_v2, list_v2

router = APIRouter(prefix="/v2", tags=["IHB vNext neutral measurement"])


class RegisterV2Request(BaseModel):
    subject_id: str
    baseline_days: int = 90
    min_baseline_n: int = 14
    magnitude_threshold_abs_z: float = 2.0
    persistence_min_observations: int = 3
    require_consecutive_days: bool = True
    segmentation_mode: str = "unspecified"


class PushV2Request(BaseModel):
    subject_id: str
    csv_data: str
    vendor: Optional[str] = None
    anchor_date: Optional[str] = None
    source_id: str = ""
    device_model: str = "unknown"
    algorithm_version: str = "unknown"
    firmware_version: str = "unknown"
    metric_definition: str = ""
    force_new_epoch: bool = False


class QueryV2Request(BaseModel):
    subject_id: str
    metric: str
    source_epoch_id: Optional[str] = None
    analysis_mode: str = Field("prospective", pattern="^(prospective|retrospective)$")


class CompareEpochsRequest(BaseModel):
    subject_id: str
    epoch_a: str
    epoch_b: str
    metric: str
    min_overlap: int = 30


@router.get("/manifest")
def manifest_v2():
    return {
        "schema": "ihb.service.v2",
        "status": "development-scientific-hardening",
        "measurement_layer": "neutral",
        "canonical_method": "individualized longitudinal deviation and temporal-state framework",
        "primary_record": "observed_only",
        "source_rule": "validate_before_harmonize",
        "state_rule": "magnitude evidence is reported separately from persistence/regime evidence",
        "action_policy": "downstream_domain_adapter",
        "endpoints": ["/v2/register", "/v2/push", "/v2/query_state", "/v2/source_epochs/{subject_id}", "/v2/compare_sources", "/v2/subjects"],
    }


@router.post("/register")
def register(req: RegisterV2Request):
    try:
        st = register_v2(
            req.subject_id,
            baseline_days=req.baseline_days,
            min_baseline_n=req.min_baseline_n,
            magnitude_threshold_abs_z=req.magnitude_threshold_abs_z,
            persistence_min_observations=req.persistence_min_observations,
            require_consecutive_days=req.require_consecutive_days,
            segmentation_mode=req.segmentation_mode,
        )
        return {"status": "registered", "subject_id": req.subject_id, "profile": st.profile}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/push")
def push(req: PushV2Request):
    st = get_v2(req.subject_id)
    if not st:
        raise HTTPException(404, "Subject not registered in v2. Call /v2/register first.")
    try:
        return st.push_csv(
            req.csv_data,
            vendor=req.vendor,
            anchor_date=req.anchor_date,
            source_id=req.source_id,
            device_model=req.device_model,
            algorithm_version=req.algorithm_version,
            firmware_version=req.firmware_version,
            metric_definition=req.metric_definition,
            force_new_epoch=req.force_new_epoch,
        )
    except Exception as exc:
        raise HTTPException(422, str(exc))


@router.post("/query_state")
def query_state(req: QueryV2Request):
    st = get_v2(req.subject_id)
    if not st:
        raise HTTPException(404, "Subject not registered in v2")
    try:
        return st.query_state(req.metric, source_epoch_id=req.source_epoch_id, analysis_mode=req.analysis_mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/source_epochs/{subject_id}")
def source_epochs(subject_id: str):
    st = get_v2(subject_id)
    if not st:
        raise HTTPException(404, "Subject not registered in v2")
    return {"subject_id": subject_id, "epochs": st.list_epochs(), "rule": "new source => new epoch by default"}


@router.post("/compare_sources")
def compare_sources(req: CompareEpochsRequest):
    st = get_v2(req.subject_id)
    if not st:
        raise HTTPException(404, "Subject not registered in v2")
    try:
        return st.compare_epochs(req.epoch_a, req.epoch_b, req.metric, min_overlap=req.min_overlap)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/subjects")
def subjects():
    return {"subjects": list_v2()}
