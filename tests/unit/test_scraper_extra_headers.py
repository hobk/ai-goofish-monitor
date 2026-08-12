from src.scraper import _build_extra_headers


def test_build_extra_headers_drops_browser_navigation_only_headers():
    raw_headers = {
        "User-Agent": "Mozilla/5.0 test",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept": "*/*",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://www.goofish.com/im",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "sec-ch-ua": '"Chromium";v="151"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Cookie": "secret=value",
    }

    assert _build_extra_headers(raw_headers) == {
        "User-Agent": "Mozilla/5.0 test",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
