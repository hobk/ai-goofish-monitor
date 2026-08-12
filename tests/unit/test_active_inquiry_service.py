from src.services.active_inquiry_service import extract_recommendation_score, should_start_inquiry


def test_extract_recommendation_score_reads_multiple_ai_shapes():
    assert extract_recommendation_score({"recommendation_score": 82}) == 82
    assert extract_recommendation_score({"recommendation_score": "76%"}) == 76
    assert extract_recommendation_score({"value_score": 88}) == 88
    assert extract_recommendation_score({"is_recommended": True}) == 100
    assert extract_recommendation_score({"is_recommended": False}) == 0


def test_should_start_inquiry_uses_enabled_threshold_and_status():
    record = {"ai_analysis": {"recommendation_score": 71}}
    settings = {"enabled": True, "threshold": 70}
    assert should_start_inquiry(record, settings) is True

    assert should_start_inquiry(record, {"enabled": False, "threshold": 70}) is False
    assert should_start_inquiry(record, {"enabled": True, "threshold": 80}) is False
    assert should_start_inquiry({"ai_analysis": {"is_recommended": False}}, settings) is False
