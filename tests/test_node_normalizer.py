from brain_share.node_normalizer import normalize_surface, merge_aliases

def test_normalize_surface():
    assert normalize_surface("  Joy  Due  ") == "joy due"
    assert normalize_surface("[ACME]") == "acme"

def test_merge_aliases_groups_similar():
    # ACME/ACMEE 는 거의 같은 벡터, OTHER 는 멀게
    vec = {
        "acme":  [1.0, 0.0],
        "acmee": [0.99, 0.01],
        "other":  [0.0, 1.0],
    }
    def embed(s): return vec[s]
    m = merge_aliases(["ACME", "ACMEE", "OTHER"], embed, threshold=0.95)
    # ACME, ACMEE 는 같은 canonical 로
    assert m["ACME"] == m["ACMEE"]
    assert m["OTHER"] != m["ACME"]

def test_merge_aliases_below_threshold_separate():
    vec = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    m = merge_aliases(["a", "b"], lambda s: vec[s], threshold=0.95)
    assert m["a"] != m["b"]

def test_normalize_surface_korean_unchanged():
    assert normalize_surface("  한글  ") == "한글"
    assert normalize_surface("Acme 회사") == "acme 회사"
