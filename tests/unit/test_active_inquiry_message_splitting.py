from src.services.active_inquiry_service import split_outbound_messages


def test_split_outbound_messages_sends_each_nonempty_line_separately():
    assert split_outbound_messages("你好\n\n请问还在吗\r\n谢谢") == [
        "你好",
        "请问还在吗",
        "谢谢",
    ]


def test_split_outbound_messages_keeps_single_line_message():
    assert split_outbound_messages("你好 对这台挺感兴趣") == ["你好 对这台挺感兴趣"]
