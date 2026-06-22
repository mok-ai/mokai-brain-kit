import hmac
from brain_share.sensitivity_filter import filter_results


def check_key(provided: str, config) -> bool:
    if not provided or not config.read_key:
        return False
    return hmac.compare_digest(str(provided), str(config.read_key))


def resolve_query(query, top_k, wiki_search, rag_search, config):
    out = filter_results(wiki_search(query, top_k), config)
    seen = {r["id"] for r in out}
    if len(out) < top_k:
        extra = filter_results(rag_search(query, top_k + len(seen)), config)
        for r in extra:
            if r["id"] in seen:
                continue
            out.append(r); seen.add(r["id"])
            if len(out) >= top_k:
                break
    return out[:top_k]


def resolve_related(entity, top_k, related_fn, config):
    return filter_results(related_fn(entity, top_k), config)
