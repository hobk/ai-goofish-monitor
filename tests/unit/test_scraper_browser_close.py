import asyncio

import pytest

from src import scraper


class FakeBrowser:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_close_browser_does_not_prompt_for_input_in_headless_debug(monkeypatch):
    fake_browser = FakeBrowser()

    def fail_input(prompt):
        raise AssertionError("headless debug cleanup must not prompt for stdin")

    monkeypatch.setattr("builtins.input", fail_input)

    await scraper._close_browser_after_task(fake_browser, debug_limit=1, headless=True)

    assert fake_browser.closed is True
