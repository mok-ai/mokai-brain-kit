"""Self-canonicalization batch — turn an agent's existing RAG memory into a
canonical LLM wiki + relation graph, indexed back into a `wiki` collection
so the unified search surfaces it.

Distinct from `synth_daemon` (which processes incoming/<node_id>/ uploads
from leaves).  `selfsynth_batch` processes the agent's OWN knowledge
collection (e.g. kim_knowledge) and writes results to:
  - `<vault_dir>/MEMORY/<slug>.md`  (human-readable canonical wiki)
  - `<wiki_collection>` chroma collection  (machine-searchable, RAG-indexed)
  - `<graph_db>` SQLite relation graph (entities + co-occurrence)

Designed to run weekly/monthly via Task Scheduler. Idempotent on the wiki
side (slug = stable id, upsert overwrites — same topic re-synthesized with
fresh content stays at the same id, no duplicate accumulation).
"""
import os
import io
import datetime
from typing import Callable, Optional

import numpy as np

from brain_share.wiki_synth import synthesize_topic
from brain_share.wiki_store import WikiStore
from brain_share.graph_batch import update_graph
from brain_share.graph_store import SqliteGraphStore


class _WikiIndexer:
    """Adapter: upserts a synthesized wiki page into the target chroma
    collection so unified search finds it. ``embed_fn`` is injected so this
    module never imports a specific embedding library."""

    def __init__(self, collection, embed_fn: Callable[[str], list]):
        self.col = collection
        self.embed = embed_fn

    def upsert(self, id: str, text: str, metadata: dict):
        if not text or not text.strip():
            return
        self.col.upsert(
            ids=[id],
            embeddings=[self.embed(text)],
            documents=[text],
            metadatas=[metadata],
        )

    def search(self, query: str, top_k: int = 5):
        return []  # batch never searches


def cluster_topics(embeddings: np.ndarray, *,
                   over_k: int = 24, merge_threshold: float = 0.06) -> tuple:
    """Over-cluster with KMeans then merge centroids by cosine distance.
    Returns (labels, n_topics). Pure deterministic — fixed seed."""
    from sklearn.cluster import KMeans, AgglomerativeClustering  # heavy, lazy
    n = embeddings.shape[0]
    if n == 0:
        return np.array([], dtype=int), 0
    k = min(over_k, n)
    km = KMeans(n_clusters=k, n_init=4, random_state=42).fit(embeddings)
    if k == 1:
        return np.zeros(n, dtype=int), 1
    agg = AgglomerativeClustering(
        n_clusters=None, distance_threshold=merge_threshold,
        metric="cosine", linkage="average")
    meta = agg.fit_predict(km.cluster_centers_)
    labels = np.array([meta[c] for c in km.labels_])
    return labels, len(set(meta))


def pick_representatives(embeddings: np.ndarray, labels: np.ndarray,
                         topic: int, *, k: int) -> np.ndarray:
    """Return indices of `k` chunks nearest to the topic's centroid."""
    idx = np.where(labels == topic)[0]
    if len(idx) == 0:
        return idx
    center = embeddings[idx].mean(axis=0)
    dist = np.linalg.norm(embeddings[idx] - center, axis=1)
    order = np.argsort(dist)[:k]
    return idx[order]


def run_selfsynth(
    *,
    source_collection,
    wiki_collection,
    vault_dir: str,
    embed_fn: Callable[[str], list],
    llm_synth_fn: Callable[[str], str],
    extractor_fn: Callable[[str], tuple],
    graph_db_path: str,
    slug_prefix: str = "topic",
    namespace: str = "MEMORY",
    over_k: int = 24,
    merge_threshold: float = 0.06,
    reps_per_topic: int = 10,
    updated: Optional[str] = None,
) -> dict:
    """One self-canonicalization pass.

    Reads embeddings+documents from `source_collection`, clusters into
    topics, synthesizes a canonical wiki per topic via injected LLM,
    writes Obsidian .md, upserts into `wiki_collection`, updates the
    relation graph.

    Returns dict: {topics, wikis_made, wiki_count, nodes, edges, log}.

    All heavy deps (chroma collections, embedder, LLM) are injected.
    """
    log_buf = io.StringIO()
    def log(*a): log_buf.write(" ".join(str(x) for x in a) + "\n")

    if updated is None:
        updated = datetime.date.today().isoformat()

    got = source_collection.get(include=["embeddings", "documents"])
    emb = np.asarray(got.get("embeddings") or [], dtype=np.float32)
    docs = got.get("documents") or []
    log(f"[1] source {emb.shape[0] if emb.size else 0}건 임베딩 로드")
    if emb.size == 0:
        return {"topics": 0, "wikis_made": 0, "wiki_count": 0,
                "nodes": 0, "edges": 0, "log": log_buf.getvalue()}

    labels, n_topics = cluster_topics(emb, over_k=over_k,
                                       merge_threshold=merge_threshold)
    log(f"[2] 토픽 자동도출: over_k={over_k} → {n_topics}개")

    indexer = _WikiIndexer(wiki_collection, embed_fn)
    store = WikiStore(vault_dir, indexer)

    scan_units = []
    made = 0
    log(f"[3] 토픽별 정본 합성 + Obsidian + wiki 컬렉션 적재")
    for m in sorted(set(labels.tolist())):
        rep_idx = pick_representatives(emb, labels, m, k=reps_per_topic)
        if len(rep_idx) == 0:
            continue
        chunks = [{"id": f"k{i}", "content": docs[i]} for i in rep_idx]
        slug = f"{slug_prefix}_{int(m):02d}"
        page = synthesize_topic(slug, namespace, chunks, updated,
                                llm_synth_fn, extractor_fn)
        path = store.upsert(page)
        if page.body:
            made += 1
            scan_units.append((slug, page.entities))
            log(f"   - {slug}: {len(page.entities)}E {len(page.relations)}R -> "
                f"{os.path.basename(path) if path else 'X'}")

    log(f"[4] 관계 그래프 갱신")
    gs = SqliteGraphStore(graph_db_path)
    rep = update_graph(scan_units, gs, decay=1.0, prune_min=0.0)
    edges = gs.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    nodes = gs.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    gs.close()
    log(f"   처리 {rep}  → 노드 {nodes} 엣지 {edges}")

    wiki_count = wiki_collection.count()
    log(f"[5] 완료: 위키 {made}개 ({namespace}/), 컬렉션 {wiki_count}건, "
        f"노드 {nodes} 엣지 {edges}")

    return {
        "topics": n_topics,
        "wikis_made": made,
        "wiki_count": wiki_count,
        "nodes": nodes,
        "edges": edges,
        "log": log_buf.getvalue(),
    }
