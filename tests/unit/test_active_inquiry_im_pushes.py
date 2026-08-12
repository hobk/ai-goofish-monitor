from src.services.active_inquiry_im import ActiveInquiryImClient


def _push(*raws):
    return {"body": {"syncPushPackage": {"data": [{"data": raw} for raw in raws]}}}


def test_parse_pushes_returns_all_messages(monkeypatch):
    client = ActiveInquiryImClient("acct", "unb=buyer")
    decoded = [
        {"1": {"2": "cid@goofish", "3": "m1", "10": {"senderUserId": "s1@goofish", "reminderContent": "第一条"}}},
        {"1": {"2": "cid@goofish", "3": "m2", "10": {"senderUserId": "s1@goofish", "reminderContent": "飞了不到10次"}}},
    ]
    calls = iter(decoded)
    monkeypatch.setattr(client, "_decode_push_data", lambda raw: next(calls))

    messages = client._parse_pushes(_push("ignored-1", "ignored-2"))

    assert [m.text for m in messages] == ["第一条", "飞了不到10次"]
    assert messages[1].message_id == "m2"
