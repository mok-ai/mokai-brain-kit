from dataclasses import dataclass, field
import yaml

_FM_KEYS = ["topic", "namespace", "sensitivity", "updated",
            "sources", "promote", "entities", "relations"]

@dataclass
class WikiPage:
    topic: str = ""
    namespace: str = ""
    sensitivity: str = "internal"
    updated: str = ""
    sources: list = field(default_factory=list)
    promote: str = "none"
    entities: list = field(default_factory=list)
    relations: list = field(default_factory=list)
    body: str = ""

def render_page(page: WikiPage) -> str:
    fm = {k: getattr(page, k) for k in _FM_KEYS}
    y = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{y}\n---\n{page.body}"

def parse_page(md: str) -> WikiPage:
    if md.startswith("---\n"):
        rest = md[4:]
        end = rest.find("\n---")
        if end != -1:
            fm_text = rest[:end]
            body = rest[end + 4:]
            if body.startswith("\n"):
                body = body[1:]
            data = yaml.safe_load(fm_text) or {}
            return WikiPage(
                topic=data.get("topic", ""), namespace=data.get("namespace", ""),
                sensitivity=data.get("sensitivity", "internal"),
                updated=data.get("updated", ""), sources=data.get("sources", []) or [],
                promote=data.get("promote", "none"),
                entities=data.get("entities", []) or [],
                relations=data.get("relations", []) or [], body=body,
            )
    return WikiPage(body=md)
