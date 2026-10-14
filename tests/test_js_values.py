import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nodriver import cdp

from js_values import evaluate_to_python, from_deep_serialized, to_python


DEEP_OBJECT = {
    "type": "object",
    "value": [
        ["name", {"type": "string", "value": "card"}],
        ["count", {"type": "number", "value": 3}],
        ["ratio", {"type": "number", "value": "NaN"}],
        ["missing", {"type": "undefined"}],
        ["tags", {"type": "array", "value": [{"type": "string", "value": "a"}, {"type": "boolean", "value": True}]}],
        ["nested", {"type": "object", "value": [["deep", {"type": "null"}]]}],
        ["pattern", {"type": "regexp", "value": {"pattern": "a+", "flags": "g"}}],
        ["node", {"type": "node", "value": {"nodeType": 1}}],
    ],
}


class FakeTab:
    """Tab stand-in whose evaluate() returns a preset value."""

    def __init__(self, result):
        self.result = result
        self.expressions = []

    async def evaluate(self, expression, await_promise=False, return_by_value=False):
        self.expressions.append((expression, await_promise))
        return self.result


class FromDeepSerializedTests(unittest.TestCase):
    def test_nested_object_converts_to_plain_data(self):
        value = from_deep_serialized(DEEP_OBJECT)
        self.assertEqual(value["name"], "card")
        self.assertEqual(value["count"], 3)
        self.assertNotEqual(value["ratio"], value["ratio"])
        self.assertIsNone(value["missing"])
        self.assertEqual(value["tags"], ["a", True])
        self.assertEqual(value["nested"], {"deep": None})
        self.assertEqual(value["pattern"], "/a+/g")
        self.assertEqual(value["node"], {"type": "node", "value": {"nodeType": 1}})

    def test_non_node_values_pass_through(self):
        self.assertEqual(from_deep_serialized("plain"), "plain")
        self.assertEqual(from_deep_serialized(5), 5)


class ToPythonTests(unittest.TestCase):
    def test_unwrapped_object_entries(self):
        self.assertEqual(to_python(DEEP_OBJECT["value"])["count"], 3)

    def test_unwrapped_array_nodes(self):
        nodes = [{"type": "string", "value": "x"}, {"type": "number", "value": 1}]
        self.assertEqual(to_python(nodes), ["x", 1])

    def test_remote_object_with_deep_value(self):
        remote = cdp.runtime.RemoteObject(
            type_="object",
            deep_serialized_value=cdp.runtime.DeepSerializedValue.from_json(DEEP_OBJECT),
        )
        self.assertEqual(to_python(remote)["tags"], ["a", True])

    def test_primitives_and_plain_lists_unchanged(self):
        self.assertEqual(to_python("text"), "text")
        self.assertEqual(to_python([1, 2]), [1, 2])
        self.assertIsNone(to_python(None))


class EvaluateToPythonTests(unittest.TestCase):
    def test_exception_details_become_error(self):
        details = cdp.runtime.ExceptionDetails(
            exception_id=1,
            text="Uncaught",
            line_number=0,
            column_number=0,
            exception=cdp.runtime.RemoteObject(type_="object", description="Error: boom"),
        )
        value, error = asyncio.run(evaluate_to_python(FakeTab(details), "throw new Error('boom')"))
        self.assertIsNone(value)
        self.assertEqual(error, "Error: boom")

    def test_success_returns_converted_value(self):
        tab = FakeTab(DEEP_OBJECT["value"])
        value, error = asyncio.run(evaluate_to_python(tab, "({})", await_promise=True))
        self.assertIsNone(error)
        self.assertEqual(value["name"], "card")
        self.assertEqual(tab.expressions, [("({})", True)])


if __name__ == "__main__":
    unittest.main()
