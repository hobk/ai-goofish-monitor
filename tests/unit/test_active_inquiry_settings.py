from src.services.active_inquiry_service import mask_secret_value, merge_settings_payload


def test_merge_settings_payload_keeps_existing_masked_secret():
    existing = {
        "captcha_solver_api_key": "old-secret",
        "captcha_solver_endpoint": "https://old.example/solve",
    }
    payload = {
        "captcha_solver_api_key": "********",
        "captcha_solver_endpoint": "https://new.example/solve",
    }

    merged = merge_settings_payload(payload, existing)

    assert merged["captcha_solver_api_key"] == "old-secret"
    assert merged["captcha_solver_endpoint"] == "https://new.example/solve"


def test_mask_secret_value_redacts_configured_key():
    assert mask_secret_value("1184") == "********"
    assert mask_secret_value("") == ""
