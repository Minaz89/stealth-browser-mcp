import asyncio
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nodriver as uc

from browser_manager import BrowserManager
from models import PageState

RUN_BROWSER_TESTS = os.getenv("STEALTH_BROWSER_TESTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

HEADLESS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)

SAMPLE_COOKIE_JSON = {
    "name": "session",
    "value": "abc123",
    "domain": "example.com",
    "path": "/",
    "expires": -1,
    "size": 13,
    "httpOnly": True,
    "secure": True,
    "session": True,
    "priority": "Medium",
    "sameParty": False,
    "sourceScheme": "Secure",
    "sourcePort": 443,
}


class FakeTab:
    """Stand-in tab that answers evaluate() from a table and send() with a fixed value."""

    def __init__(self, send_result):
        self.send_result = send_result
        self.evaluations = {
            "window.location.href": "https://example.com/",
            "document.title": "Example Domain",
            "document.readyState": "complete",
            "Object.keys(localStorage)": [],
            "Object.keys(sessionStorage)": [],
        }

    async def send(self, command):
        # Drain the generator the way nodriver's Connection.send does, then
        # hand back whatever shape the test wants get_page_state to receive.
        try:
            next(command)
        except StopIteration:
            pass
        return self.send_result

    async def evaluate(self, expression, *args, **kwargs):
        import json

        if expression.startswith("JSON.stringify("):
            inner = expression[len("JSON.stringify("):-1].strip()
            while inner.startswith("(") and inner.endswith(")"):
                inner = inner[1:-1].strip()
            if inner.startswith("{"):
                return json.dumps({"width": 1920, "height": 1080, "devicePixelRatio": 1})
            return json.dumps(self.evaluations.get(inner))
        return self.evaluations.get(expression)


def _manager_with_tab(tab):
    manager = BrowserManager()

    async def get_tab(instance_id):
        return tab

    manager.get_tab = get_tab
    return manager


class CookiesToDictsTests(unittest.TestCase):
    def test_list_of_cookie_dataclasses(self):
        cookie = uc.cdp.network.Cookie.from_json(SAMPLE_COOKIE_JSON)
        result = BrowserManager._cookies_to_dicts([cookie])
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result[0]["name"], "session")
        self.assertEqual(result[0]["value"], "abc123")

    def test_raw_json_dict_shape(self):
        result = BrowserManager._cookies_to_dicts({"cookies": [SAMPLE_COOKIE_JSON]})
        self.assertEqual(result, [SAMPLE_COOKIE_JSON])

    def test_list_of_dicts_passes_through(self):
        result = BrowserManager._cookies_to_dicts([SAMPLE_COOKIE_JSON])
        self.assertEqual(result, [SAMPLE_COOKIE_JSON])

    def test_none_and_empty(self):
        self.assertEqual(BrowserManager._cookies_to_dicts(None), [])
        self.assertEqual(BrowserManager._cookies_to_dicts([]), [])
        self.assertEqual(BrowserManager._cookies_to_dicts({}), [])


class GetPageStateTests(unittest.TestCase):
    def test_page_state_with_cookie_dataclasses(self):
        cookie = uc.cdp.network.Cookie.from_json(SAMPLE_COOKIE_JSON)
        manager = _manager_with_tab(FakeTab([cookie]))

        state = asyncio.run(manager.get_page_state("instance-1"))

        self.assertIsInstance(state, PageState)
        self.assertEqual(state.url, "https://example.com/")
        self.assertEqual(state.title, "Example Domain")
        self.assertEqual(state.ready_state, "complete")
        self.assertEqual(state.cookies[0]["name"], "session")
        self.assertEqual(state.viewport["width"], 1920)

    def test_page_state_with_legacy_dict_shape(self):
        manager = _manager_with_tab(FakeTab({"cookies": [SAMPLE_COOKIE_JSON]}))

        state = asyncio.run(manager.get_page_state("instance-1"))

        self.assertEqual(state.cookies, [SAMPLE_COOKIE_JSON])


@unittest.skipUnless(
    RUN_BROWSER_TESTS,
    "Set STEALTH_BROWSER_TESTS=1 to run tests that launch a real browser.",
)
class GetPageStateBrowserTests(unittest.TestCase):
    def test_real_page_state(self):
        from models import BrowserOptions

        async def run():
            manager = BrowserManager()
            instance = await manager.spawn_browser(
                BrowserOptions(headless=True, user_agent=HEADLESS_USER_AGENT)
            )
            try:
                await manager.navigate(
                    instance.instance_id,
                    "data:text/html,<title>state-test</title><p>hi</p>",
                )
                return await manager.get_page_state(instance.instance_id)
            finally:
                await manager.close_instance(instance.instance_id)

        state = asyncio.run(run())

        self.assertIsInstance(state, PageState)
        self.assertEqual(state.title, "state-test")
        self.assertEqual(state.ready_state, "complete")
        self.assertIsInstance(state.cookies, list)


if __name__ == "__main__":
    unittest.main()
