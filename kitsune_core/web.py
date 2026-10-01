"""Kitsune web subsystem. Extracted without changing the original function bodies."""

from .foundation import *

def do_web_search(query, max_results=5, max_attempts=3):
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # older package name
        except ImportError:
            return (
                "Web search unavailable: the 'ddgs' package isn't installed. "
                "Install it with: pip install ddgs"
            )

    import time
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            with DDGS(timeout=20) as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if results:
                break
        except Exception as e:
            last_error = e
            results = []
        if attempt < max_attempts:
            time.sleep(1.5)
    else:
        results = []

    if not results:
        if last_error:
            return f"Web search failed after {max_attempts} attempts (backend timeouts): {last_error}"
        return "No results found."

    lines = []
    for r in results:
        title = r.get("title", "").strip()
        body = r.get("body", "").strip()
        url = r.get("href", "").strip()
        lines.append(f"- {title}\n  {body}\n  {url}")
    return "\n".join(lines)

