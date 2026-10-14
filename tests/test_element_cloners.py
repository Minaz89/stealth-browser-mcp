import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from element_cloner import element_cloner
from file_based_element_cloner import FileBasedElementCloner
from progressive_element_cloner import MAX_STORED_ELEMENTS, progressive_element_cloner
from response_handler import ResponseHandler


SAMPLE_CLONE = {
    "element": {
        "html": {"tagName": "BUTTON", "attributes": [{"name": "id", "value": "go"}]},
        "styles": {"display": "flex", "color": "red", "font-size": "14px"},
        "eventListeners": [{"type": "click", "source": "inline"}, {"type": "focus", "source": "property"}],
        "cssRules": [{"selector": ".btn", "css": "color: red", "source": "https://x.test/app.css"}],
        "pseudoElements": {"::before": {"content": "'*'", "styles": {}}},
        "animations": {"animation": "none", "transition": "all 1s", "transform": "none"},
        "fonts": {"computed": "Arial", "fontSize": "14px", "fontWeight": "400"},
    },
    "children": [{"depth": 1}, {"depth": 2}, {"depth": 3}],
    "url": "https://x.test/",
}


class RenderJsTests(unittest.TestCase):
    def test_selector_is_json_escaped(self):
        selector = 'a[href="/x"], input[name=\'q\'], #a\\:b'
        js = element_cloner._render_js("extract_structure.js", selector=selector, options={"max_depth": 2})
        self.assertIn(f"const selector = {json.dumps(selector)};", js)
        self.assertIn('const options = {"max_depth": 2};', js)
        self.assertNotIn("$SELECTOR$", js)

    def test_placeholder_text_inside_values_is_not_substituted(self):
        js = element_cloner._render_js(
            "extract_assets.js",
            selector="$INCLUDE_FONTS$",
            include_images=True,
            include_backgrounds=False,
            include_fonts=True,
            fetch_external=False,
        )
        self.assertIn('})("$INCLUDE_FONTS$", {', js)
        self.assertIn("const includeBackgrounds = false;", js)

    def test_missing_placeholder_value_raises(self):
        with self.assertRaises(KeyError):
            element_cloner._render_js("extract_related_files.js", analyze_css=True)


class ProgressiveClonerTests(unittest.TestCase):
    def setUp(self):
        self.store = {"elem_1": {"full_data": SAMPLE_CLONE, "timestamp": 1.0}}
        patcher = mock.patch.object(progressive_element_cloner, "_get_store", side_effect=lambda: self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_expand_reads_nested_element_data(self):
        self.assertEqual(progressive_element_cloner.expand_styles("elem_1")["total_available"], 3)
        self.assertEqual(
            progressive_element_cloner.expand_styles("elem_1", categories=["colors"])["styles"],
            {"color": "red"},
        )
        events = progressive_element_cloner.expand_events("elem_1", event_types=["click"])
        self.assertEqual((events["returned_count"], events["total_available"]), (1, 2))
        self.assertEqual(progressive_element_cloner.expand_css_rules("elem_1", ["app.css"])["returned_count"], 1)
        self.assertEqual(progressive_element_cloner.expand_pseudo_elements("elem_1")["available_pseudos"], ["::before"])
        self.assertEqual(progressive_element_cloner.expand_animations("elem_1")["fonts"]["computed"], "Arial")
        children = progressive_element_cloner.expand_children("elem_1", depth_range=(1, 2), max_count=1)
        self.assertEqual((children["returned_count"], children["total_available"]), (1, 3))

    def test_unknown_element_returns_error(self):
        self.assertIn("error", progressive_element_cloner.expand_styles("missing"))

    def test_store_is_capped_to_newest_entries(self):
        saved = {}
        data = {f"elem_{i}": {"full_data": {}, "timestamp": float(i)} for i in range(MAX_STORED_ELEMENTS + 5)}
        with mock.patch("progressive_element_cloner.persistent_storage.set", side_effect=lambda key, value: saved.update(value)):
            progressive_element_cloner._save_store(data)
        self.assertEqual(len(saved), MAX_STORED_ELEMENTS)
        self.assertNotIn("elem_0", saved)
        self.assertIn(f"elem_{MAX_STORED_ELEMENTS + 4}", saved)


class FileBasedClonerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cloner = FileBasedElementCloner(output_dir=self.tmp.name)

    def test_extraction_error_is_not_saved(self):
        error = {"error": "JavaScript error: boom"}
        with mock.patch("file_based_element_cloner.element_cloner.extract_element_structure", mock.AsyncMock(return_value=error)):
            result = asyncio.run(self.cloner.extract_element_structure_to_file(object(), selector="#x"))
        self.assertEqual(result, error)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_complete_summary_reads_nested_element(self):
        with mock.patch(
            "file_based_element_cloner.comprehensive_element_cloner.extract_complete_element",
            mock.AsyncMock(return_value=json.loads(json.dumps(SAMPLE_CLONE))),
        ):
            result = asyncio.run(self.cloner.extract_complete_element_to_file(object(), "#go"))
        summary = result["summary"]
        self.assertEqual(summary["tag_name"], "BUTTON")
        self.assertEqual(summary["computed_styles_count"], 3)
        self.assertEqual(summary["event_listeners_count"], 2)
        self.assertEqual(summary["children_count"], 3)
        self.assertTrue(Path(result["file_path"]).exists())

    def test_styles_summary_keeps_components_key(self):
        styles = {"computed_styles": {"color": "red"}, "css_rules": []}
        with mock.patch("file_based_element_cloner.element_cloner.extract_element_styles", mock.AsyncMock(return_value=styles)):
            result = asyncio.run(self.cloner.extract_element_styles_to_file(object(), "#go"))
        self.assertEqual(result["components"]["computed_styles_count"], 1)


class ResponseHandlerTests(unittest.TestCase):
    def test_large_response_filename_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            handler = ResponseHandler(max_tokens=1, clone_dir=tmp)
            result = handler.handle_response({"data": "x" * 100}, 'assets_../../evil div > a[href="x"]')
            path = Path(result["file_path"])
            self.assertEqual(path.parent, Path(tmp))
            self.assertTrue(path.name.startswith("assets_.._.._evil_div_a_href_x"))
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
