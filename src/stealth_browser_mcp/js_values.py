"""Convert nodriver evaluation results into plain Python values.

nodriver's ``Tab.evaluate`` always sends ``serializationOptions`` with deep
serialization, and CDP lets that option override ``returnByValue``. Results
therefore arrive as WebDriver BiDi style ``{"type": ..., "value": ...}``
nodes, either wrapped in a ``RemoteObject`` or already unwrapped one level
by nodriver. This module turns every shape back into ordinary JSON-like data.
"""

from typing import Any, Optional, Tuple

from nodriver import cdp

_SPECIAL_NUMBERS = {
    "NaN": float("nan"),
    "-0": -0.0,
    "Infinity": float("inf"),
    "-Infinity": float("-inf"),
}


def _is_node(value: Any) -> bool:
    """Return True when ``value`` looks like a deep serialized node.

    Args:
        value (Any): Candidate value.

    Returns:
        bool: Whether the value is a dict carrying a string ``type`` key.
    """
    return isinstance(value, dict) and isinstance(value.get("type"), str)


def _is_pair_list(value: Any) -> bool:
    """Return True when ``value`` is a deep serialized object entry list.

    Args:
        value (Any): Candidate value.

    Returns:
        bool: Whether every item is a ``[key, node]`` pair.
    """
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(
            isinstance(item, list) and len(item) == 2 and _is_node(item[1])
            for item in value
        )
    )


def _entries_to_dict(entries: list) -> dict:
    """Convert deep serialized ``[key, node]`` entries into a dict.

    Args:
        entries (list): Entry pairs from an object or map node.

    Returns:
        dict: Converted mapping with string keys.
    """
    result = {}
    for key, node in entries:
        if _is_node(key):
            key = from_deep_serialized(key)
        result[key if isinstance(key, str) else str(key)] = from_deep_serialized(node)
    return result


def from_deep_serialized(node: Any) -> Any:
    """Convert one deep serialized node into a plain Python value.

    Args:
        node (Any): Node shaped like ``{"type": ..., "value": ...}``. Values
            that are not nodes are returned unchanged.

    Returns:
        Any: Plain Python value. Objects and maps become dicts, arrays and
        sets become lists, regexps become ``/pattern/flags`` strings, and
        types with no JSON form (functions, DOM nodes, windows) become a
        ``{"type": ...}`` marker.
    """
    if not _is_node(node):
        return node
    kind = node["type"]
    value = node.get("value")
    if kind in ("undefined", "null"):
        return None
    if kind in ("string", "boolean", "bigint", "date"):
        return value
    if kind == "number":
        return _SPECIAL_NUMBERS.get(value, value) if isinstance(value, str) else value
    if kind in ("array", "set"):
        return [from_deep_serialized(item) for item in value or []]
    if kind in ("object", "map"):
        return _entries_to_dict(value or [])
    if kind == "regexp" and isinstance(value, dict):
        return f"/{value.get('pattern', '')}/{value.get('flags', '')}"
    marker = {"type": kind}
    if value is not None:
        marker["value"] = value
    return marker


def to_python(result: Any) -> Any:
    """Convert whatever nodriver's ``Tab.evaluate`` returned into plain data.

    Args:
        result (Any): A ``RemoteObject``, an unwrapped deep serialized value,
            or an already plain value.

    Returns:
        Any: Plain Python value.
    """
    if isinstance(result, cdp.runtime.RemoteObject):
        if result.value is not None:
            return result.value
        if result.deep_serialized_value is not None:
            return from_deep_serialized(result.deep_serialized_value.to_json())
        if result.type_ == "undefined" or result.subtype == "null":
            return None
        return result.unserializable_value or result.description
    if _is_node(result):
        return from_deep_serialized(result)
    if _is_pair_list(result):
        return _entries_to_dict(result)
    if isinstance(result, list) and all(_is_node(item) for item in result):
        return [from_deep_serialized(item) for item in result]
    return result


def describe_exception(details: cdp.runtime.ExceptionDetails) -> str:
    """Build a readable message from CDP exception details.

    Args:
        details (cdp.runtime.ExceptionDetails): Exception reported by CDP.

    Returns:
        str: Exception description, falling back to the CDP summary text.
    """
    exception = details.exception
    if exception is not None and exception.description:
        return exception.description
    return details.text or "JavaScript evaluation failed"


async def evaluate_to_python(
    tab: Any,
    expression: str,
    await_promise: bool = False,
) -> Tuple[Any, Optional[str]]:
    """Evaluate JavaScript in a tab and return a plain value or an error.

    Args:
        tab (Any): nodriver tab to evaluate in.
        expression (str): JavaScript expression to evaluate.
        await_promise (bool): Await the result when it is a Promise.

    Returns:
        Tuple[Any, Optional[str]]: ``(value, None)`` on success, or
        ``(None, message)`` when the script threw.
    """
    result = await tab.evaluate(expression, await_promise=await_promise)
    if isinstance(result, cdp.runtime.ExceptionDetails):
        return None, describe_exception(result)
    return to_python(result), None
