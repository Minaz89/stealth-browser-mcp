"""Advanced element cloning system with complete styling and JS extraction."""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

import requests

try:
    from .debug_logger import debug_logger
    from .js_values import evaluate_to_python
except ImportError:
    from debug_logger import debug_logger
    from js_values import evaluate_to_python

JS_DIR = Path(__file__).parent / "js"
PLACEHOLDER_PATTERN = re.compile(r"\$([A-Z_]+)\$")


class ElementCloner:
    """Advanced element cloning with full fidelity extraction."""

    def __init__(self):
        self.framework_patterns = {
            'react': [r'_react', r'__reactInternalInstance', r'__reactFiber'],
            'vue': [r'__vue__', r'_vnode', r'\$el'],
            'angular': [r'ng-', r'__ngContext__', r'ɵ'],
            'jquery': [r'jQuery', r'\$\.', r'__jquery']
        }

    async def extract_element_styles(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        include_computed: bool = True,
        include_css_rules: bool = True,
        include_pseudo: bool = True,
        include_inheritance: bool = False
    ) -> Dict[str, Any]:
        """
        Extract complete styling information from an element.

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            include_computed (bool): Include computed styles
            include_css_rules (bool): Include matching CSS rules
            include_pseudo (bool): Include pseudo-element styles
            include_inheritance (bool): Include style inheritance chain

        Returns:
            Dict[str, Any]: Dict with styling data
        """
        try:
            return await self.extract_element_styles_cdp(
                tab=tab,
                element=element,
                selector=selector,
                include_computed=include_computed,
                include_css_rules=include_css_rules,
                include_pseudo=include_pseudo,
                include_inheritance=include_inheritance
            )
        except Exception as e:
            debug_logger.log_error("element_cloner", "extract_styles", e)
            return {"error": str(e)}

    def _render_js(self, filename: str, **values: Any) -> str:
        """
        Load a JavaScript template and substitute its placeholders.

        Placeholders use the ``$NAME$`` form and are replaced in a single pass
        with the JSON encoding of the matching keyword argument, so strings
        such as selectors are always valid, safely escaped JS literals.

        Args:
            filename (str): Template file name inside the ``js`` directory.
            **values (Any): Placeholder values keyed by lowercase name.

        Returns:
            str: JavaScript source ready to evaluate.
        """
        js_file = JS_DIR / filename
        if not js_file.exists():
            raise FileNotFoundError(f"JavaScript file not found: {js_file}")
        js_code = js_file.read_text(encoding='utf-8')
        literals = {name.upper(): json.dumps(value) for name, value in values.items()}

        def substitute(match: re.Match) -> str:
            name = match.group(1)
            if name not in literals:
                raise KeyError(f"Missing value for placeholder ${name}$ in {filename}")
            return literals[name]

        return PLACEHOLDER_PATTERN.sub(substitute, js_code)

    async def _run_extractor(self, tab, operation: str, filename: str, **values: Any) -> Dict[str, Any]:
        """
        Render a JavaScript extractor, evaluate it, and normalize the result.

        Args:
            tab (Any): Browser tab instance
            operation (str): Operation name used in logs
            filename (str): Template file name inside the ``js`` directory
            **values (Any): Placeholder values for the template

        Returns:
            Dict[str, Any]: Extracted data, or a dict with an ``error`` key
        """
        js_code = self._render_js(filename, **values)
        data, error = await evaluate_to_python(tab, js_code)
        if error:
            return {"error": f"JavaScript error: {error}"}
        if not isinstance(data, dict):
            debug_logger.log_warning("element_cloner", operation, f"Got unexpected type: {type(data)}")
            return {"error": f"Unexpected return type: {type(data)}", "raw_data": str(data)[:500]}
        debug_logger.log_info("element_cloner", operation, "Extraction completed")
        return data

    async def extract_element_structure(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        include_children: bool = False,
        include_attributes: bool = True,
        include_data_attributes: bool = True,
        max_depth: int = 3
    ) -> Dict[str, Any]:
        """
        Extract complete HTML structure and DOM information.

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            include_children (bool): Include child elements
            include_attributes (bool): Include all attributes
            include_data_attributes (bool): Include data-* attributes specifically
            max_depth (int): Maximum depth for children extraction

        Returns:
            Dict[str, Any]: Dict with structure data
        """
        try:
            if not selector:
                return {"error": "Selector is required"}
            options = {
                'include_children': include_children,
                'include_attributes': include_attributes,
                'include_data_attributes': include_data_attributes,
                'max_depth': max_depth
            }
            return await self._run_extractor(
                tab, "extract_structure", 'extract_structure.js', selector=selector, options=options
            )
        except Exception as e:
            debug_logger.log_error("element_cloner", "extract_structure", e)
            return {"error": str(e)}

    async def extract_element_events(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        include_inline: bool = True,
        include_listeners: bool = True,
        include_framework: bool = True,
        analyze_handlers: bool = True
    ) -> Dict[str, Any]:
        """
        Extract complete event listener and JavaScript handler information.

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            include_inline (bool): Include inline event handlers (onclick, etc.)
            include_listeners (bool): Include addEventListener attached handlers
            include_framework (bool): Include framework-specific handlers (React, Vue, etc.)
            analyze_handlers (bool): Analyze handler functions for details

        Returns:
            Dict[str, Any]: Dict with event data
        """
        try:
            if not selector:
                return {"error": "Selector is required"}
            options = {
                'include_inline': include_inline,
                'include_listeners': include_listeners,
                'include_framework': include_framework,
                'analyze_handlers': analyze_handlers
            }
            return await self._run_extractor(
                tab, "extract_events", 'extract_events.js', selector=selector, options=options
            )
        except Exception as e:
            debug_logger.log_error("element_cloner", "extract_events", e)
            return {"error": str(e)}

    async def extract_element_animations(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        include_css_animations: bool = True,
        include_transitions: bool = True,
        include_transforms: bool = True,
        analyze_keyframes: bool = True
    ) -> Dict[str, Any]:
        """
        Extract CSS animations, transitions, and transforms.

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            include_css_animations (bool): Include CSS @keyframes animations
            include_transitions (bool): Include CSS transitions
            include_transforms (bool): Include CSS transforms
            analyze_keyframes (bool): Analyze keyframe rules

        Returns:
            Dict[str, Any]: Dict with animation data
        """
        try:
            if not selector:
                return {"error": "Selector is required"}
            options = {
                'include_css_animations': include_css_animations,
                'include_transitions': include_transitions,
                'include_transforms': include_transforms,
                'analyze_keyframes': analyze_keyframes
            }
            return await self._run_extractor(
                tab, "extract_animations", 'extract_animations.js', selector=selector, options=options
            )
        except Exception as e:
            debug_logger.log_error("element_cloner", "extract_animations", e)
            return {"error": str(e)}

    async def extract_element_assets(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        include_images: bool = True,
        include_backgrounds: bool = True,
        include_fonts: bool = True,
        fetch_external: bool = False
    ) -> Dict[str, Any]:
        """
        Extract all assets related to an element (images, fonts, etc.).

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            include_images (bool): Include img src and related images
            include_backgrounds (bool): Include background images
            include_fonts (bool): Include font information
            fetch_external (bool): Whether to fetch external assets for analysis

        Returns:
            Dict[str, Any]: Dict with asset data
        """
        try:
            if not selector:
                return {"error": "Selector is required"}
            asset_data = await self._run_extractor(
                tab,
                "extract_assets",
                'extract_assets.js',
                selector=selector,
                include_images=include_images,
                include_backgrounds=include_backgrounds,
                include_fonts=include_fonts,
                fetch_external=fetch_external,
            )
            if fetch_external and "error" not in asset_data:
                asset_data['external_assets'] = {}
                for bg_img in asset_data.get('background_images', []):
                    url = bg_img.get('url', '') if isinstance(bg_img, dict) else ''
                    if not self._is_http_url(url):
                        continue
                    try:
                        response = await asyncio.to_thread(requests.get, url, timeout=5)
                        asset_data['external_assets'][url] = {
                            'content_type': response.headers.get('content-type'),
                            'size': len(response.content),
                            'status': response.status_code
                        }
                    except Exception as e:
                        debug_logger.log_warning("element_cloner", "extract_assets", f"Could not fetch asset {url}: {e}")
            return asset_data
        except Exception as e:
            debug_logger.log_error("element_cloner", "extract_assets", e)
            return {"error": str(e)}

    async def extract_related_files(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        analyze_css: bool = True,
        analyze_js: bool = True,
        follow_imports: bool = False,
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """
        Discover and analyze related CSS/JS files for context.

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            analyze_css (bool): Analyze linked CSS files
            analyze_js (bool): Analyze linked JS files
            follow_imports (bool): Follow @import and module imports
            max_depth (int): Maximum depth for following imports

        Returns:
            Dict[str, Any]: Dict with related file data
        """
        try:
            file_data = await self._run_extractor(
                tab,
                "extract_related_files",
                'extract_related_files.js',
                analyze_css=analyze_css,
                analyze_js=analyze_js,
                follow_imports=follow_imports,
                max_depth=max_depth,
            )
            if follow_imports and max_depth > 0 and "error" not in file_data:
                await self._fetch_and_analyze_files(file_data)
            return file_data
        except Exception as e:
            debug_logger.log_error("element_cloner", "extract_related_files", e)
            return {"error": str(e)}

    @staticmethod
    def _is_http_url(url: Any) -> bool:
        """
        Check whether a value is an absolute http or https URL.

        Args:
            url (Any): Candidate URL

        Returns:
            bool: True when the URL uses the http or https scheme
        """
        return isinstance(url, str) and urlparse(url).scheme in ("http", "https")

    async def _fetch_text(self, url: str) -> Optional[str]:
        """
        Fetch a text resource without blocking the event loop.

        Args:
            url (str): Absolute http or https URL

        Returns:
            Optional[str]: Response body for a 200 response, otherwise None
        """
        response = await asyncio.to_thread(requests.get, url, timeout=10)
        return response.text if response.status_code == 200 else None

    async def _fetch_and_analyze_files(self, file_data: Dict[str, Any]) -> None:
        """
        Fetch and analyze external CSS/JS files for additional context.

        Args:
            file_data (Dict[str, Any]): Data structure containing file info, updated in place

        Returns:
            None
        """
        seen = set()
        for stylesheet in file_data.get('stylesheets', []):
            href = stylesheet.get('href')
            if not self._is_http_url(href) or href in seen:
                continue
            seen.add(href)
            try:
                content = await self._fetch_text(href)
                if content is None:
                    continue
                imports = re.findall(r'@import\s+["\']([^"\']+)["\']', content)
                stylesheet['imports'] = [urljoin(href, imp) for imp in imports]
                stylesheet['custom_properties'] = re.findall(r'--[\w-]+:\s*[^;]+', content)
            except Exception as e:
                debug_logger.log_warning("element_cloner", "fetch_css", f"Could not fetch CSS file {href}: {e}")
        for script in file_data.get('scripts', []):
            src = script.get('src')
            if not self._is_http_url(src) or src in seen:
                continue
            seen.add(src)
            try:
                content = await self._fetch_text(src)
                if content is None:
                    continue
                script['detected_frameworks'] = [
                    framework
                    for framework, patterns in self.framework_patterns.items()
                    if any(re.search(pattern, content, re.IGNORECASE) for pattern in patterns)
                ]
                script['module_imports'] = re.findall(r'import.*from\s+["\']([^"\']+)["\']', content)
            except Exception as e:
                debug_logger.log_warning("element_cloner", "fetch_js", f"Could not fetch JS file {src}: {e}")

    async def clone_element_complete(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        extraction_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Master function that extracts all element data using specialized functions.

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            extraction_options (Optional[Dict[str, Any]]): Dict specifying what to extract and options for each
                Example: {
                    'styles': {'include_computed': True, 'include_pseudo': True},
                    'structure': {'include_children': True, 'max_depth': 2},
                    'events': {'include_framework': True, 'analyze_handlers': True},
                    'animations': {'analyze_keyframes': True},
                    'assets': {'fetch_external': True},
                    'related_files': {'follow_imports': True, 'max_depth': 1}
                }

        Returns:
            Dict[str, Any]: Complete element clone data
        """
        try:
            default_options = {
                'styles': {'include_computed': True, 'include_css_rules': True, 'include_pseudo': True},
                'structure': {'include_children': False, 'include_attributes': True},
                'events': {'include_framework': True, 'analyze_handlers': False},
                'animations': {'analyze_keyframes': True},
                'assets': {'fetch_external': False},
                'related_files': {'follow_imports': False}
            }
            if extraction_options:
                for key, value in extraction_options.items():
                    if key in default_options:
                        default_options[key].update(value)
                    else:
                        default_options[key] = value
            if element is None and selector:
                element = await tab.select(selector)
            if not element:
                return {"error": "Element not found"}
            result = {
                "url": tab.url,
                "timestamp": time.time(),
                "selector": selector,
                "extraction_options": default_options
            }
            extractors = {
                'styles': self.extract_element_styles,
                'structure': self.extract_element_structure,
                'events': self.extract_element_events,
                'animations': self.extract_element_animations,
                'assets': self.extract_element_assets,
                'related_files': self.extract_related_files,
            }
            tasks = [
                (name, extractor(tab, element, selector=selector, **default_options[name]))
                for name, extractor in extractors.items()
                if name in default_options
            ]
            results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            for (name, _), outcome in zip(tasks, results):
                result[name] = {"error": str(outcome)} if isinstance(outcome, Exception) else outcome
            debug_logger.log_info("element_cloner", "clone_complete", f"Complete element clone extracted with {len(tasks)} data types")
            return result
        except Exception as e:
            debug_logger.log_error("element_cloner", "clone_complete", e)
            return {"error": str(e)}

    async def extract_element_styles_cdp(
        self,
        tab,
        element=None,
        selector: Optional[str] = None,
        include_computed: bool = True,
        include_css_rules: bool = True,
        include_pseudo: bool = True,
        include_inheritance: bool = False
    ) -> Dict[str, Any]:
        """
        Extract complete styling information using direct CDP calls (no JavaScript evaluation).
        This prevents hanging issues by using nodriver's native CDP methods.

        Args:
            tab (Any): Browser tab instance
            element (Any): Element object or None to use selector
            selector (Optional[str]): CSS selector if element is None
            include_computed (bool): Include computed styles
            include_css_rules (bool): Include matching CSS rules
            include_pseudo (bool): Include pseudo-element styles
            include_inheritance (bool): Include style inheritance chain

        Returns:
            Dict[str, Any]: Dict with styling data
        """
        try:
            import nodriver.cdp as cdp

            await tab.send(cdp.dom.enable())
            await tab.send(cdp.css.enable())

            if element is None and selector:
                element = await tab.select(selector)
            if not element:
                return {"error": "Element not found"}

            if hasattr(element, 'node_id'):
                node_id = element.node_id
            elif hasattr(element, 'backend_node_id'):
                node_info = await tab.send(cdp.dom.describe_node(backend_node_id=element.backend_node_id))
                node_id = node_info.node.node_id
            else:
                return {"error": "Could not get node ID from element"}

            result = {"method": "cdp_direct"}

            if include_computed:
                debug_logger.log_info("element_cloner", "extract_styles_cdp", "Getting computed styles via CDP")
                computed_styles_list = await tab.send(cdp.css.get_computed_style_for_node(node_id))
                result["computed_styles"] = {prop.name: prop.value for prop in computed_styles_list}

            matched_styles = ()
            if include_css_rules or include_pseudo or include_inheritance:
                debug_logger.log_info("element_cloner", "extract_styles_cdp", "Getting matched styles via CDP")
                matched_styles = await tab.send(cdp.css.get_matched_styles_for_node(node_id))

            if include_css_rules:
                inline_style, attributes_style, matched_rules = matched_styles[0], matched_styles[1], matched_styles[2]
                result["css_rules"] = []
                for rule_match in matched_rules or []:
                    if rule_match.rule and rule_match.rule.style:
                        result["css_rules"].append({
                            "selector": rule_match.rule.selector_list.text if rule_match.rule.selector_list else "unknown",
                            "css_text": rule_match.rule.style.css_text or "",
                            "source": rule_match.rule.origin.value if rule_match.rule.origin else "unknown"
                        })
                if inline_style:
                    result["inline_style"] = {
                        "css_text": inline_style.css_text or "",
                        "properties": len(inline_style.css_properties) if inline_style.css_properties else 0
                    }
                if attributes_style:
                    result["attributes_style"] = {
                        "css_text": attributes_style.css_text or "",
                        "properties": len(attributes_style.css_properties) if attributes_style.css_properties else 0
                    }

            if include_pseudo and len(matched_styles) > 3 and matched_styles[3]:
                result["pseudo_elements"] = {}
                for pseudo_match in matched_styles[3]:
                    if pseudo_match.pseudo_type:
                        result["pseudo_elements"][pseudo_match.pseudo_type.value] = {
                            "matches": len(pseudo_match.matches) if pseudo_match.matches else 0
                        }

            if include_inheritance and len(matched_styles) > 4 and matched_styles[4]:
                result["inheritance_chain"] = []
                for inherited_entry in matched_styles[4]:
                    if inherited_entry.inline_style:
                        result["inheritance_chain"].append({
                            "inline_css": inherited_entry.inline_style.css_text or "",
                            "properties": len(inherited_entry.inline_style.css_properties) if inherited_entry.inline_style.css_properties else 0
                        })

            debug_logger.log_info("element_cloner", "extract_styles_cdp", f"CDP extraction completed with {len(result.get('css_rules', []))} CSS rules")
            return result

        except Exception as e:
            debug_logger.log_error("element_cloner", "extract_styles_cdp", e)
            return {"error": f"CDP extraction failed: {str(e)}"}


element_cloner = ElementCloner()
