from brain_share.wiki_page import WikiPage

_SYNTH_PROMPT = (
    "아래 조각들을 하나의 주제 '{topic}' 정본 위키 페이지로 합성하라. "
    "중복 제거, 모순은 최신 우선으로 해소, 마크다운 본문만 출력(frontmatter 금지).\n\n조각:\n{joined}"
)


def synthesize_topic(topic, namespace, chunks, updated, llm_fn, extractor_fn) -> WikiPage:
    if not chunks:
        return WikiPage(topic=topic, namespace=namespace, sensitivity="internal",
                        updated=updated, sources=[], promote="pending",
                        entities=[], relations=[], body="")
    joined = "\n\n".join(f"[{c.get('id','?')}] {c.get('content','')}" for c in chunks)
    body = llm_fn(_SYNTH_PROMPT.format(topic=topic, joined=joined)) or ""
    entities, relations = extractor_fn(body)
    return WikiPage(topic=topic, namespace=namespace, sensitivity="internal",
                    updated=updated, sources=[c.get("id", "?") for c in chunks],
                    promote="pending", entities=entities, relations=relations, body=body)
