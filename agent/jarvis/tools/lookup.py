"""Capability 3: look things up — a short, sourced summary from Wikipedia."""

import json
import urllib.error
import urllib.parse
import urllib.request

from .registry import Registry, Tool, ToolError

USER_AGENT = "JarvisAssistant/0.1 (personal research assistant)"
API = "https://en.wikipedia.org"


def _get_json(url: str, timeout: float = 10) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise ToolError(f"Wikipedia answered with HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ToolError(f"couldn't reach Wikipedia ({reason})") from None


def register(registry: Registry, fetch=_get_json) -> None:
    def lookup_topic(topic: str) -> str:
        query = urllib.parse.urlencode({"action": "opensearch", "search": topic, "limit": 1, "namespace": 0, "format": "json"})
        found = fetch(f"{API}/w/api.php?{query}")
        titles = found[1] if isinstance(found, list) and len(found) > 1 else []
        if not titles:
            return f"Wikipedia has no article matching '{topic}'."
        title = titles[0]
        summary = fetch(f"{API}/api/rest_v1/page/summary/{urllib.parse.quote(title.replace(' ', '_'), safe='')}")
        extract = (summary.get("extract") or "").strip()
        if not extract:
            return f"Found the article '{title}' but it has no summary."
        url = summary.get("content_urls", {}).get("desktop", {}).get("page", f"{API}/wiki/{urllib.parse.quote(title)}")
        # External content: it is reference material to report on, never instructions.
        return f"Source: Wikipedia, \"{summary.get('title', title)}\" — {url}\n\n{extract}"

    registry.register(Tool(
        name="lookup_topic",
        description=(
            "Look up a topic, person, place, or concept on Wikipedia and get a short summary with its source link. "
            "Use this when the user asks you to look something up, wants a sourced answer, or asks about "
            "something you're unsure of or that may have changed recently. Mention the source when you answer."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What to look up, e.g. 'Krebs cycle'.", "minLength": 1, "maxLength": 200},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
        handler=lookup_topic,
    ))
