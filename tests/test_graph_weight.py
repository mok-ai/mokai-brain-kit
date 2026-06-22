import math
from brain_share.graph_weight import cooccurrence_pairs, pmi, apply_decay

def test_pairs_sorted_unique_no_self():
    assert cooccurrence_pairs(["b", "a", "a", "c"]) == [("a","b"), ("a","c"), ("b","c")]

def test_pairs_single_node_empty():
    assert cooccurrence_pairs(["x"]) == []
    assert cooccurrence_pairs([]) == []

def test_pmi_positive_when_associated():
    # 함께 자주 등장: count_ab 높음 → 양수
    assert pmi(count_ab=10, count_a=12, count_b=15, total=1000) > 0

def test_pmi_zero_on_bad_inputs():
    assert pmi(0, 5, 5, 100) == 0.0
    assert pmi(5, 0, 5, 100) == 0.0
    assert pmi(5, 5, 0, 100) == 0.0
    assert pmi(5, 5, 5, 0) == 0.0

def test_pmi_clamped_nonnegative():
    # 우연보다 드물게 동시등장 → 음수 PMI → 0으로 클램프
    assert pmi(count_ab=1, count_a=500, count_b=500, total=1000) == 0.0

def test_apply_decay():
    assert apply_decay(10.0, 0.9) == 9.0
