import math

def cooccurrence_pairs(nodes: list) -> list:
    uniq = sorted(set(n for n in nodes if n))
    pairs = []
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            pairs.append((uniq[i], uniq[j]))
    return pairs

def pmi(count_ab: float, count_a: float, count_b: float, total: float) -> float:
    if count_ab <= 0 or count_a <= 0 or count_b <= 0 or total <= 0:
        return 0.0
    val = math.log((count_ab * total) / (count_a * count_b))
    return val if val > 0 else 0.0

def apply_decay(weight: float, factor: float) -> float:
    return weight * factor
