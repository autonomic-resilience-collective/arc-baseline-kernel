from ihb_vnext_state import VNextSubjectState


def _csv(values):
    lines = ["study_day,hrv_rmssd"]
    lines += [f"{i},{v}" for i, v in enumerate(values)]
    return "\n".join(lines)


def test_v2_output_is_neutral_and_separates_regime_from_magnitude():
    values = [100.0] * 20 + [130.0]
    st = VNextSubjectState("s1", baseline_days=20, min_baseline_n=14, magnitude_threshold_abs_z=2.0, persistence_min_observations=3)
    st.push_csv(_csv(values), vendor="studyday", source_id="oura-g3", device_model="Oura Gen 3")
    out = st.query_state("hrv_rmssd")
    assert out["measurement_layer"] == "neutral"
    assert "commercial_tag" not in out
    assert "purchase_signal" not in out
    assert out["primary_record"].startswith("IHB-primary")
    assert "regime_evidence" in out


def test_source_change_creates_new_epoch_by_default():
    st = VNextSubjectState("s2", baseline_days=14, min_baseline_n=14)
    first = st.push_csv(_csv([100.0 + i for i in range(20)]), vendor="studyday", source_id="device-a", device_model="A")
    second = st.push_csv(_csv([110.0 + i for i in range(20)]), vendor="studyday", source_id="device-b", device_model="B")
    assert first["source_epoch_id"] != second["source_epoch_id"]
    assert second["source_transition_created"] is True
    assert len(st.list_epochs()) == 2


def test_same_source_continues_existing_epoch():
    st = VNextSubjectState("s3", baseline_days=14, min_baseline_n=14)
    first = st.push_csv(_csv([100.0 + i for i in range(20)]), vendor="studyday", source_id="same", device_model="A")
    second = st.push_csv(_csv([100.0 + i for i in range(20)]), vendor="studyday", source_id="same", device_model="A")
    assert first["source_epoch_id"] == second["source_epoch_id"]
    assert second["source_transition_created"] is False
