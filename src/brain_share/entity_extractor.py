import json

_PROMPT = (
    "다음 텍스트에서 엔티티(프로젝트/PC/사람/결정/고객)와 관계를 추출해 "
    "JSON으로만 답하라. 형식: "
    '{"entities":["..."],"relations":[{"from":"..","type":"affects|depends|owns|about","to":".."}]}\n\n텍스트:\n'
)

def _extract_json(text: str):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None

def extract_entities(text: str, llm_fn):
    raw = llm_fn(_PROMPT + text)
    data = _extract_json(raw or "")
    if not isinstance(data, dict):
        return ([], [])
    ents = [str(e) for e in data.get("entities", []) if e]
    rels = [r for r in data.get("relations", []) if isinstance(r, dict)
            and {"from", "type", "to"} <= set(r.keys())]
    return (ents, rels)

def backlinks(entities, known_topics):
    known = set(known_topics)
    hits = sorted({e for e in entities if e in known})
    return [f"[[{t}]]" for t in hits]
