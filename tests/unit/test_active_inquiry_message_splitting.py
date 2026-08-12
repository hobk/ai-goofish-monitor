from src.services.active_inquiry_service import (
    format_exception_message,
    is_auto_reply_message,
    split_outbound_messages,
)


def test_split_outbound_messages_sends_each_nonempty_line_separately():
    assert split_outbound_messages("你好\n\n请问还在吗\r\n谢谢") == [
        "你好",
        "请问还在吗",
        "谢谢",
    ]


def test_split_outbound_messages_keeps_single_line_message():
    assert split_outbound_messages("你好 对这台挺感兴趣") == ["你好 对这台挺感兴趣"]


def test_auto_reply_messages_are_ignored():
    assert is_auto_reply_message("亲，我现在不在线，商品还在，可以直接拍。有问题请留言") is True
    assert is_auto_reply_message("亲，我现在不在，喜欢可以拍下，有问题留言哦～会尽快回复") is True
    assert is_auto_reply_message("（亲，我现在不在线，商品还在，可以直接拍。有问题请留言 ）") is True
    assert is_auto_reply_message("您好 当前自动回复 商品还在") is True
    assert is_auto_reply_message("电池循环大概多少") is False


def test_format_exception_message_includes_type_when_message_empty():
    assert format_exception_message(TimeoutError()) == "TimeoutError"
