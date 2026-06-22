from brain_share.graph_weight import cooccurrence_pairs


def update_graph(scan_units, store, canonicalize=None, decay=0.9, prune_min=0.05):
    """주기 배치: decay_all 1회 → 신규 unit co-occurrence 누적 → prune.
    decay는 호출당 정확히 1회 적용된다(scan_units가 비어도/전부 skip이어도).
    이는 의도된 '살아있는 그래프' 동작 — 조용한 기간엔 오래된 관계가 자연 감쇠한다.
    멱등: 이미 처리된 unit_id는 재집계되지 않는다.
    """
    canon = canonicalize or (lambda n: n)

    # Apply decay exactly once per call
    store.decay_all(decay)

    processed = 0
    skipped = 0

    # Process each unit
    for uid, nodes in scan_units:
        if store.is_processed(uid):
            skipped += 1
            continue

        # Canonicalize and filter nodes
        cnodes = [canon(n) for n in nodes if n]

        # Bump each unique node
        for n in set(cnodes):
            store.bump_node(n, 1.0)

        # Upsert edges from cooccurrence pairs
        for a, b in cooccurrence_pairs(cnodes):
            store.upsert_edge(a, b, 1.0)

        # Mark unit as processed
        store.mark_processed(uid)
        processed += 1

    # Prune low-weight edges
    pruned = store.prune(prune_min)

    return {"processed": processed, "skipped": skipped, "pruned": pruned}
