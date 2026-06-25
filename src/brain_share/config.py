import json
from dataclasses import dataclass, field

@dataclass
class BrainShareConfig:
    role: str = "HUB"
    read_key: str = ""
    share_port: int = 9211
    blocked_divisions: list[str] = field(default_factory=list)
    blocked_tag_patterns: list[str] = field(default_factory=list)
    blocked_keyword_patterns: list[str] = field(default_factory=list)
    allowed_collections: list[str] = field(default_factory=list)
    vault_dir: str = ""
    # Path of the JSON file load_config() read from. Used by mm_adapter to
    # derive MEMORY_PATH when the env var isn't set.
    source_path: str = ""

def load_config(path: str) -> BrainShareConfig:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    role = d.get("role", "HUB")
    if role not in ("HUB", "LEAF"):
        raise ValueError(f"role must be HUB or LEAF, got {role}")
    read_key = d.get("read_key", "")
    if role == "HUB" and not read_key:
        raise ValueError("HUB requires non-empty read_key")
    return BrainShareConfig(
        role=role, read_key=read_key, share_port=int(d.get("share_port", 9211)),
        blocked_divisions=list(d.get("blocked_divisions", [])),
        blocked_tag_patterns=list(d.get("blocked_tag_patterns", [])),
        blocked_keyword_patterns=list(d.get("blocked_keyword_patterns", [])),
        allowed_collections=list(d.get("allowed_collections", [])),
        vault_dir=d.get("vault_dir", ""),
        source_path=str(path),
    )
