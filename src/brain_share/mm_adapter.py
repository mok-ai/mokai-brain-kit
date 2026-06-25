"""
mm_adapter.py — Lazy MemoryManager wiring for brain_share.

Imports MemoryManager at call-time (never at module import) so that loading
brain_share.mm_adapter does NOT start the embedding model, touch the live
C:/main_ai data, or instantiate ChromaDB.  Tests can inject a fake
memory_manager module before calling make_backends().
"""

import os
import sys
from pathlib import Path

from brain_share.wiki_store import WikiStore
from brain_share.sensitivity_filter import filter_results


class _MMIndexer:
    """Wraps a MemoryManager so WikiStore can use its 'wiki' collection."""

    def __init__(self, mm):
        self.mm = mm

    def upsert(self, id, text, metadata):
        self.mm.collections["wiki"].upsert(
            ids=[id],
            embeddings=[self.mm._embed_query(text)],
            documents=[text],
            metadatas=[metadata],
        )

    def search(self, query, top_k):
        try:
            return self.mm.search(query, collections=["wiki"], top_k=top_k)
        except Exception:
            return []


def make_backends(config):
    """
    Lazily import MemoryManager, wire up WikiStore, and return three callables:

        wiki_search(q, k)  → list[dict]  (wiki collection only)
        rag_search(q, k)   → list[dict]  (all MemoryManager collections)
        related_fn(e, k)   → list[dict]  (filtered by sensitivity config)

    Parameters
    ----------
    config : BrainShareConfig

    Returns
    -------
    (wiki_search, rag_search, related_fn)
    """
    # Resolve path to the memory module directory.
    # No hardcoded default — must be set explicitly via MEMORY_PATH env or
    # auto-derived from the config file's parent directory.
    memory_path = os.environ.get("MEMORY_PATH")
    if not memory_path:
        cfg_path = getattr(config, "_source_path", None) or getattr(config, "source_path", None)
        if cfg_path:
            memory_path = str(Path(cfg_path).resolve().parent)
    if not memory_path:
        raise RuntimeError(
            "MEMORY_PATH not set. Either export MEMORY_PATH=<agent_memory_root> "
            "or run the gateway from the directory that holds memory_manager.py."
        )
    if memory_path not in sys.path:
        sys.path.insert(0, memory_path)

    # Lazy import — real MemoryManager loads heavy ML deps; tests inject a fake.
    from memory_manager import MemoryManager  # noqa: PLC0415

    mm = MemoryManager()
    store = WikiStore(config.vault_dir, _MMIndexer(mm))

    # UNFILTERED — results MUST pass through gateway_core.resolve_query (filter_results) before reaching any caller.
    def wiki_search(q, k=5):
        return store.search(q, k)

    # UNFILTERED — results MUST pass through gateway_core.resolve_query (filter_results) before reaching any caller.
    def rag_search(q, k=5):
        return mm.search(q, top_k=k)

    def related_fn(e, k=5):
        return filter_results(mm.search(e, top_k=k), config)

    return (wiki_search, rag_search, related_fn)
