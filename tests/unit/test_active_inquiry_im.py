import asyncio
from http.cookies import SimpleCookie

from src.services.active_inquiry_im import _extract_response_cookies


def test_extract_response_cookies_reads_set_cookie_getall():
    cookie = SimpleCookie()
    cookie["_m_h5_tk"] = "new_token_123"
    cookie["_m_h5_tk"]["path"] = "/"

    class Headers:
        def getall(self, name, default=None):
            assert name == "Set-Cookie"
            return [cookie.output(header="").strip(), "foo=bar; Path=/"]

    assert _extract_response_cookies(Headers()) == {"_m_h5_tk": "new_token_123", "foo": "bar"}
