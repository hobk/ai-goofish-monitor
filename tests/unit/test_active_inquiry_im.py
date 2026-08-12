from http.cookies import SimpleCookie

from src.services.active_inquiry_im import ActiveInquiryImClient, _extract_response_cookies


def test_extract_response_cookies_reads_set_cookie_getall():
    cookie = SimpleCookie()
    cookie["_m_h5_tk"] = "new_token_123"
    cookie["_m_h5_tk"]["path"] = "/"

    class Headers:
        def getall(self, name, default=None):
            assert name == "Set-Cookie"
            return [cookie.output(header="").strip(), "foo=bar; Path=/"]

    assert _extract_response_cookies(Headers()) == {"_m_h5_tk": "new_token_123", "foo": "bar"}


def test_token_error_message_identifies_captcha_risk_control():
    client = ActiveInquiryImClient("xy", "_m_h5_tk=old_1; unb=123")
    ret_text = "['FAIL_SYS_USER_VALIDATE', 'RGV587_ERROR::SM::哎哟喂,被挤爆啦,请稍后重试']"
    assert "FAIL_SYS_USER_VALIDATE" in ret_text
