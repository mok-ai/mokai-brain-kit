"""Direct chroma wiki collection search — bypasses RAG API's reranker/hybrid
that can suppress canonical wiki entries. Used by memory_mcp as a first
result stream before falling back to RAG API results.

Heavy deps (chromadb, sentence-transformers) are imported lazily on first
use so unit tests inject fakes and never load real models.
"""
import logging

log = logging.getLogger("brain_share.wiki_search")


def _default_client_factory(path):
    import chromadb  # lazy
    return chromadb.PersistentClient(path=path)


_EMBEDDER_CACHE = {}


def _default_embedder(model_name: str = "intfloat/multilingual-e5-large"):
    """Return callable(text) -> list[float]. Cached across calls."""
    if model_name in _EMBEDDER_CACHE:
        return _EMBEDDER_CACHE[model_name]
    try:
        import sentence_transformers  # lazy
        if sentence_transformers is None:
            return None
        model = sentence_transformers.SentenceTransformer(model_name)
    except Exception as e:
        log.warning("embedder load failed: %s", e)
        return None
    def _embed(text: str):
        return model.encode(text).tolist()
    _EMBEDDER_CACHE[model_name] = _embed
    return _embed


def search_wiki(query: str, top_k: int, *, chroma_path: str,
                collection_name: str, embedder_fn=None,
                client_factory=None, model_name: str = "intfloat/multilingual-e5-large") -> list:
    """Return top_k wiki entries from the specified chroma collection.
    Returns [] on any failure (missing collection, embedder unavailable, etc.).
    Result items: {id, content, score, collection: "wiki", metadata}."""
    if embedder_fn is None:
        embedder_fn = _default_embedder(model_name)
    if embedder_fn is None:
        return []
    client_factory = client_factory or _default_client_factory
    try:
        client = client_factory(chroma_path)
        col = client.get_collection(collection_name)
    except Exception as e:
        log.warning("wiki collection unavailable: %s", e)
        return []
    try:
        qe = embedder_fn(query)
        res = col.query(query_embeddings=[qe], n_results=top_k,
                        include=["documents", "distances", "metadatas"])
    except Exception as e:
        log.warning("wiki query failed: %s", e)
        return []
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    out = []
    for i, id_ in enumerate(ids):
        # chroma cosine distance: score = 1 - dist/2 (matches memory_manager convention)
        d = dists[i] if i < len(dists) else 1.0
        score = round(1.0 - (d / 2.0), 4)
        out.append({
            "id": id_,
            "content": docs[i] if i < len(docs) else "",
            "score": score,
            "collection": "wiki",
            "metadata": metas[i] if i < len(metas) else {},
        })
    return out


def merge_and_dedupe(primary: list, secondary: list, top_k: int) -> list:
    """Concat primary+secondary, dedupe by id (primary wins), cap at top_k."""
    seen = set()
    out = []
    for row in primary + secondary:
        rid = row.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
        if len(out) >= top_k:
            break
    return out
