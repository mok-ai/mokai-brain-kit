def is_blocked_node(name: str, config) -> bool:
    low = str(name).lower()
    for pat in config.blocked_tag_patterns:
        if pat and pat.lower() in low:
            return True
    for kw in config.blocked_keyword_patterns:
        if kw and kw.lower() in low:
            return True
    return False

def graph_neighbors(keyword: str, top_k: int, store, config) -> list:
    if is_blocked_node(keyword, config):
        return []
    raw = store.neighbors(keyword, top_k=top_k * 4 + 8)
    out = []
    for n in raw:
        if "node" not in n:
            continue
        if is_blocked_node(n["node"], config):
            continue
        out.append(n)
        if len(out) >= top_k:
            break
    return out
