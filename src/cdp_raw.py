"""Raw CDP commands that bypass nodriver's typed response parsing.

nodriver 0.47 parses some CDP responses into dataclasses whose required
fields no longer exist in current Chrome. ``Network.Cookie.from_json``
requires ``sameParty``, which Chrome stopped sending, so the parse raises
inside nodriver's websocket listener, the response is never delivered, and
the caller hangs. Sending the command as a raw generator returns the plain
JSON result instead.
"""

from typing import Any, Dict, Generator, List, Optional


def raw_command(method: str, params: Optional[Dict[str, Any]] = None) -> Generator[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Build a CDP command generator that returns the unparsed JSON result.

    Args:
        method (str): CDP method name, for example "Network.getCookies".
        params (Optional[Dict[str, Any]]): Command parameters.

    Returns:
        Generator[Dict[str, Any], Dict[str, Any], Dict[str, Any]]: Generator accepted by ``tab.send``.
    """
    response = yield {"method": method, "params": params or {}}
    return response


async def get_cookies(tab: Any, urls: Optional[List[str]] = None, all_cookies: bool = False) -> List[Dict[str, Any]]:
    """
    Read cookies as plain CDP JSON dicts.

    Args:
        tab (Any): nodriver tab to send the command through.
        urls (Optional[List[str]]): Limit cookies to these URLs.
        all_cookies (bool): Return every browser cookie when no URLs are given.

    Returns:
        List[Dict[str, Any]]: Cookies with CDP field names such as httpOnly and sameSite.
    """
    if urls:
        result = await tab.send(raw_command("Network.getCookies", {"urls": list(urls)}))
    elif all_cookies:
        result = await tab.send(raw_command("Network.getAllCookies"))
    else:
        result = await tab.send(raw_command("Network.getCookies"))
    cookies = result.get("cookies", []) if isinstance(result, dict) else []
    return [cookie for cookie in cookies if isinstance(cookie, dict)]
