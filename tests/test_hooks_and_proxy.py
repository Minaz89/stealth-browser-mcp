import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cdp_function_executor import CDPFunctionExecutor
from debug_logger import DebugLogger
from dynamic_hook_ai_interface import dynamic_hook_ai
from dynamic_hook_system import DynamicHook, RequestInfo, dynamic_hook_system
from http_security import EnvironmentBearerTokenVerifier
from proxy_forwarder import AuthenticatedProxyForwarder
from proxy_utils import ProxyConfigError, parse_proxy_config

BLOCK_CODE = 'def process_request(request):\n    return HookAction(action="block")\n'


def make_request(url="https://x.test/a", method="GET", resource_type="XHR"):
    return RequestInfo("r1", "i1", url, method, {}, resource_type=resource_type)


class DynamicHookTests(unittest.TestCase):
    def test_pipe_alternatives_and_case_insensitive_resource_type(self):
        hook = DynamicHook("1", "h", {"url_pattern": "*ads*|*tracking*", "method": "GET|POST", "resource_type": "xhr"}, BLOCK_CODE)
        self.assertTrue(hook.matches(make_request("https://x.test/tracking.js", "POST")))
        self.assertFalse(hook.matches(make_request("https://x.test/app.js")))
        self.assertFalse(hook.matches(make_request("https://ads.test/a", "PUT")))

    def test_custom_condition_receives_request_dict(self):
        hook = DynamicHook("1", "h", {"custom_condition": "request['method'] == 'POST'"}, BLOCK_CODE)
        self.assertTrue(hook.matches(make_request(method="POST")))
        self.assertFalse(hook.matches(make_request(method="GET")))

    def test_hook_code_cannot_reach_os_through_fnmatch(self):
        hook = DynamicHook("1", "h", {}, "def process_request(request):\n    return fnmatch.os\n")
        with self.assertRaises(AttributeError):
            hook._compiled_function({})

    def test_compile_error_is_raised(self):
        with self.assertRaises(ValueError):
            DynamicHook("1", "h", {}, "def broken(:\n")

    def test_simple_hook_values_cannot_inject_code(self):
        target_url = 'https://e.test/"); import os; ("'

        async def run():
            return await dynamic_hook_ai.create_simple_hook("redirect", "*", "redirect", target_url=target_url)

        result = asyncio.run(run())
        self.assertTrue(result.get("success"), result)
        hook = dynamic_hook_system.hooks.pop(result["hook_id"])
        self.assertEqual(hook._compiled_function(make_request().to_dict()).url, target_url)


class ProxyTests(unittest.TestCase):
    def test_credentials_are_percent_decoded(self):
        config = parse_proxy_config("http://us%40r:p%40ss%3Aw@1.2.3.4:8080")
        self.assertEqual((config.username, config.password), ("us@r", "p@ss:w"))
        forwarder = AuthenticatedProxyForwarder("http://us%40r:p%40ss@1.2.3.4:8080")
        self.assertEqual((forwarder.username, forwarder.password), ("us@r", "p@ss"))

    def test_errors_do_not_leak_password(self):
        for url in ("http://user:secretpw@host", "user:secretpw@host"):
            with self.assertRaises(ProxyConfigError) as context:
                parse_proxy_config(url)
            self.assertNotIn("secretpw", str(context.exception))


class TokenVerifierTests(unittest.TestCase):
    def test_non_ascii_token_is_rejected_without_error(self):
        verifier = EnvironmentBearerTokenVerifier("expected-token")
        self.assertIsNone(asyncio.run(verifier.verify_token("tökén")))
        self.assertIsNotNone(asyncio.run(verifier.verify_token("expected-token")))


class DebugLoggerTests(unittest.TestCase):
    def test_zero_limit_returns_no_entries_and_export_does_not_deadlock(self):
        logger = DebugLogger()
        logger._enabled = True
        logger.log_error("c", "m", ValueError("boom"))
        self.assertEqual(logger.get_debug_view_paginated(max_errors=0)["summary"]["returned_errors"], 0)
        with self.subTest("export"):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                path = logger.export_to_file_paginated(str(Path(tmp) / "log.json"), format="json")
                self.assertTrue(Path(path).exists())


class PythonTranslationTests(unittest.TestCase):
    def test_trailing_expression_is_returned_once(self):
        js = CDPFunctionExecutor()._translate_python_to_js("x = None\nx is None")
        self.assertEqual(js, "(() => { let x = null; return (x === null); })()")

    def test_statement_only_code_has_no_return(self):
        js = CDPFunctionExecutor()._translate_python_to_js("x = 1")
        self.assertNotIn("return", js)


if __name__ == "__main__":
    unittest.main()
