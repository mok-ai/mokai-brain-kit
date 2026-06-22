from brain_share.config import BrainShareConfig

def _tags_text(metadata: dict) -> str:
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        return tags
    if isinstance(tags, (list, tuple)):
        return ",".join(str(t) for t in tags)
    return str(tags)

def is_blocked(result: dict, config: BrainShareConfig) -> bool:
    meta = result.get("metadata", {}) or {}
    content = str(result.get("content", ""))
    content_l = content.lower()
    collection = result.get("collection", "")

    if config.allowed_collections and collection not in config.allowed_collections:
        return True
    if meta.get("division") in config.blocked_divisions:
        return True
    hay = (_tags_text(meta) + " " + content)
    for pat in config.blocked_tag_patterns:
        if pat and pat in hay:
            return True
    for kw in config.blocked_keyword_patterns:
        if kw and kw.lower() in content_l:
            return True
    return False

def filter_results(results, config: BrainShareConfig):
    return [r for r in results if not is_blocked(r, config)]
