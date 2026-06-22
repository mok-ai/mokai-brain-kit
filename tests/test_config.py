import json, pytest
from brain_share.config import load_config, BrainShareConfig

def _write(tmp_path, data):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)

def test_load_valid_hub(tmp_path):
    path = _write(tmp_path, {
        "role": "HUB", "read_key": "k1", "share_port": 9211,
        "blocked_divisions": ["ACCT"], "blocked_tag_patterns": ["회계"],
        "blocked_keyword_patterns": ["secret"], "allowed_collections": ["knowledge"],
        "vault_dir": "C:/x/obsidian",
    })
    cfg = load_config(path)
    assert isinstance(cfg, BrainShareConfig)
    assert cfg.role == "HUB" and cfg.read_key == "k1" and cfg.share_port == 9211
    assert cfg.blocked_divisions == ["ACCT"]

def test_invalid_role(tmp_path):
    path = _write(tmp_path, {"role": "BOSS", "read_key": "k"})
    with pytest.raises(ValueError):
        load_config(path)

def test_hub_requires_key(tmp_path):
    path = _write(tmp_path, {"role": "HUB", "read_key": ""})
    with pytest.raises(ValueError):
        load_config(path)

def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("C:/no/such/cfg.json")

def test_load_valid_leaf_no_key(tmp_path):
    path = _write(tmp_path, {"role": "LEAF"})
    cfg = load_config(path)
    assert cfg.role == "LEAF" and cfg.read_key == ""
