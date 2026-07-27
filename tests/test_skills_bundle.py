"""Tests for the skill-bundle installer's registry rebuild.

The bundle ships no installed_plugins.json on purpose — that file holds
absolute installPaths, and shipping the build machine's paths leaked a
personal account path in every release from 3.0.1 through 3.4.2. The
installer has to rebuild it locally, without trampling plugins the user
already had.
"""
import importlib.util
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]


def bundle_file(name: str) -> Path:
    """The zip package keeps these under skills_bundle/; the GitHub src
    layout keeps them at the root. Same files, two shapes."""
    for cand in (PKG_ROOT / "skills_bundle" / name, PKG_ROOT / name):
        if cand.exists():
            return cand
    raise FileNotFoundError(f"{name} not found in either layout")


def load_installer():
    spec = importlib.util.spec_from_file_location(
        "install_skills_under_test", bundle_file("install_skills.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FOUND = [("claude-plugins-official", "superpowers", "6.1.1")]


def test_registry_uses_local_cache_root():
    m = load_installer()
    reg = m.plan_registry("D:/leaf/.claude/plugins/cache", FOUND, {})
    entry = reg["plugins"]["superpowers@claude-plugins-official"][0]
    assert entry["installPath"].replace("\\", "/").startswith(
        "D:/leaf/.claude/plugins/cache")
    assert entry["version"] == "6.1.1"
    assert reg["version"] == 2


def test_registry_never_contains_the_build_machine_path():
    """Regression for the leak: only the caller-supplied cache root may
    appear. Checked against this machine's real home rather than a
    hardcoded account name — naming the account in the test would ship the
    very string we are trying to keep out of the package."""
    m = load_installer()
    reg = m.plan_registry("E:/agent/.claude/plugins/cache", FOUND, {})
    path = reg["plugins"]["superpowers@claude-plugins-official"][0][
        "installPath"].replace("\\", "/")
    home = str(Path.home()).replace("\\", "/")
    assert home not in path
    assert path.startswith("E:/agent/.claude/plugins/cache")


def test_registry_preserves_unrelated_existing_plugins():
    """Additive installer: a plugin the user installed themselves and that we
    do not ship must survive untouched."""
    m = load_installer()
    existing = {"version": 2, "plugins": {
        "their-own@some-market": [{"scope": "user", "version": "9.9",
                                   "installPath": "X:/keep/me"}]}}
    reg = m.plan_registry("C:/x/cache", FOUND, existing)
    assert reg["plugins"]["their-own@some-market"][0]["installPath"] == \
        "X:/keep/me"
    assert "superpowers@claude-plugins-official" in reg["plugins"]


def test_reinstall_keeps_original_installed_at():
    m = load_installer()
    existing = {"version": 2, "plugins": {
        "superpowers@claude-plugins-official": [
            {"installedAt": "2026-01-01T00:00:00.000Z", "version": "5.1.0"}]}}
    reg = m.plan_registry("C:/x/cache", FOUND, existing)
    e = reg["plugins"]["superpowers@claude-plugins-official"][0]
    assert e["installedAt"] == "2026-01-01T00:00:00.000Z"
    assert e["version"] == "6.1.1"
    assert e["lastUpdated"] != e["installedAt"]


def test_marketplaces_get_local_install_location():
    m = load_installer()
    shipped = {"claude-plugins-official": {
        "source": {"source": "github", "repo": "anthropics/x"}}}
    km = m.plan_marketplaces("D:/leaf/.claude/plugins/marketplaces", shipped,
                             {})
    loc = km["claude-plugins-official"]["installLocation"].replace("\\", "/")
    assert loc == "D:/leaf/.claude/plugins/marketplaces/claude-plugins-official"
    assert km["claude-plugins-official"]["source"]["repo"] == "anthropics/x"


def test_marketplaces_keep_user_entries():
    m = load_installer()
    km = m.plan_marketplaces("D:/m", {"ours": {"source": {}}},
                             {"theirs": {"source": {"repo": "u/v"}}})
    assert "theirs" in km and "ours" in km


def test_scan_cache_walks_market_plugin_version(tmp_path):
    m = load_installer()
    (tmp_path / "mk" / "plug" / "1.2.3").mkdir(parents=True)
    assert m.scan_cache(tmp_path) == [("mk", "plug", "1.2.3")]


def test_scan_cache_missing_dir_is_empty(tmp_path):
    m = load_installer()
    assert m.scan_cache(tmp_path / "nope") == []


def test_shipped_bundle_has_no_personal_path_and_no_local_registry():
    """Guards the actual artifact, not just the logic."""
    import zipfile
    z = bundle_file("plugins.zip")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert not any("installed_plugins.json" in n for n in names)
        assert not any(".in_use" in n or "__pycache__" in n for n in names)
        text = b"".join(zf.read(n) for n in names
                        if n.endswith(".json")).decode("utf-8", "replace")
        assert str(Path.home()).replace("\\", "/") not in \
            text.replace("\\\\", "/").replace("\\", "/")
        assert "installLocation" not in text


def test_no_source_file_leaks_the_build_machine_home():
    """The 3.0.0 sweep grepped for company identifiers by hand and still
    shipped a personal path for eleven releases — once inside a nested zip,
    once in a skill doc. This is that sweep, automated, over everything the
    package ships (including archives).
    """
    import zipfile
    home_variants = {
        str(Path.home()),
        str(Path.home()).replace("\\", "/"),
        str(Path.home()).replace("\\", "\\\\"),
    }
    offenders = []

    def scan(label: str, blob: bytes):
        try:
            t = blob.decode("utf-8")
        except UnicodeDecodeError:
            return
        if any(h in t for h in home_variants):
            offenders.append(label)

    text_ext = (".py", ".md", ".json", ".txt", ".vbs", ".ps1", ".cfg", ".ini")
    for p in PKG_ROOT.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(PKG_ROOT).as_posix()
        if p.suffix == ".zip":
            with zipfile.ZipFile(p) as zf:      # look inside archives too
                for n in zf.namelist():
                    if n.endswith(text_ext):
                        scan(f"{rel}!{n}", zf.read(n))
        elif p.suffix in text_ext:
            scan(rel, p.read_bytes())

    assert not offenders, ("build machine home path leaked into: "
                           + ", ".join(sorted(offenders)))
