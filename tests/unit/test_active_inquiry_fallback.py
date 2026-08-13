from src.services.active_inquiry_service import build_fallback_message, is_low_value_ai_message


def test_rejects_ack_only_ai_reply():
    assert is_low_value_ai_message("好的 循环挺低的") is True
    assert is_low_value_ai_message("循环挺低的 那无炸机进水维修吧") is False


def test_fallback_after_cycle_answer_moves_to_next_question():
    record = {"商品信息": {"商品标题": "大疆 Neo2 畅飞套装"}}
    messages = [
        {"direction": "out", "content": "电池循环和自检能发下吗"},
        {"direction": "in", "content": "循环次数：7，9，11"},
    ]
    text = build_fallback_message(record, messages, {"bargain_percent": 15}, "consulting")
    assert "循环挺低" in text
    assert "炸机" in text or "进水" in text or "维修" in text
