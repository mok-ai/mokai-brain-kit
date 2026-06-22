import re
import numpy as np

def normalize_surface(s: str) -> str:
    s = s.strip().strip("[](){}<>\"'`")
    s = re.sub(r"\s+", " ", s)
    # 영문은 소문자화(한글/숫자는 그대로)
    return "".join(c.lower() if c.isascii() else c for c in s)

def _cos(u, v):
    u = np.asarray(u, dtype=np.float32); v = np.asarray(v, dtype=np.float32)
    nu = np.linalg.norm(u); nv = np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return 0.0
    return float(np.dot(u, v) / (nu * nv))

def merge_aliases(nodes, embed_fn, threshold=0.93):
    # 정규화 표면형 기준으로 unique 노드 임베딩
    surfaces = {n: normalize_surface(n) for n in nodes}
    uniq = sorted(set(surfaces.values()))
    embs = {s: embed_fn(s) for s in uniq}
    # 그리디 클러스터: 각 표면형을 기존 canonical 와 비교
    canon = {}                  # surface -> canonical surface
    canon_list = []
    for s in uniq:
        assigned = None
        for c in canon_list:
            if _cos(embs[s], embs[c]) >= threshold:
                assigned = c
                break
        if assigned is None:
            canon_list.append(s)
            assigned = s
        canon[s] = assigned
    return {n: canon[surfaces[n]] for n in nodes}
