"""Monthly memory consolidation pass — find what has rotted, propose nothing
destructive.

Why this exists: an agent that only ever appends its successes quietly
converges on one way of doing things. Memory needs a periodic read-back that
merges duplicates, corrects principles that no longer hold, and retires what
is dead — otherwise the corpus grows but stops being true.

What this module does NOT do: delete or rewrite anything. It produces a
report. Deciding that two pages are really the same fact, or that a principle
is now wrong, is a judgement call — that belongs to the agent (or its
operator) reading this report, not to a similarity threshold.

Dependency-free by design (no embeddings): the shortlist only has to be good
enough for a human-or-LLM review pass once a month.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STALE_DAYS = 180
DEFAULT_THRESHOLD = 0.55
_DAY = 86400.0

_LINK_RE = re.compile(r"\[\[([^\]|#]+)")
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


@dataclass
class MemoryPage:
    name: str
    description: str
    type: str
    body: str
    mtime: float
    path: str

    @property
    def text(self) -> str:
        return f"{self.description}\n{self.body}"


# ────────────────────────────── parsing ───────────────────────────────

def parse_page(path, text: str, mtime: float = 0.0) -> MemoryPage:
    """Split frontmatter from body. Never raises — a malformed page still
    has to appear in the report (that may be exactly what needs fixing)."""
    name = Path(str(path)).stem
    description = ""
    ptype = ""
    body = text

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            head, body = parts[1], parts[2]
            for line in head.splitlines():
                m = re.match(r"\s*(name|description|type)\s*:\s*(.+?)\s*$",
                             line)
                if not m:
                    continue
                key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
                if key == "name" and val:
                    name = val
                elif key == "description":
                    description = val
                elif key == "type":
                    ptype = val
    return MemoryPage(name=name, description=description, type=ptype,
                      body=body.strip(), mtime=mtime, path=str(path))


def load_pages(memory_dir) -> list[MemoryPage]:
    """Read every *.md under memory_dir. Unreadable files are skipped rather
    than aborting the pass."""
    out = []
    d = Path(memory_dir)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.md")):
        try:
            out.append(parse_page(p, p.read_text(encoding="utf-8"),
                                  mtime=p.stat().st_mtime))
        except Exception:
            continue
    return out


# ───────────────────────────── similarity ─────────────────────────────

def _tokens(s: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(s or "") if len(t) > 1}


def similarity(a: str, b: str) -> float:
    """Jaccard overlap of word tokens. Cheap, symmetric, no model needed."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def find_duplicate_candidates(pages, threshold: float = DEFAULT_THRESHOLD):
    """Pairs of pages similar enough to be worth a human look.

    Each unordered pair appears once, sorted most-similar first.
    """
    out = []
    for i, a in enumerate(pages):
        for b in pages[i + 1:]:
            s = similarity(a.text, b.text)
            if s >= threshold and s > 0:
                out.append((a, b, s))
    out.sort(key=lambda t: t[2], reverse=True)
    return out


# ────────────────────────── staleness / links ─────────────────────────

def find_stale(pages, now: float, days: int = DEFAULT_STALE_DAYS):
    """Pages untouched for `days`. Old is not wrong — but a principle nobody
    has revisited in six months deserves a re-read."""
    cutoff = now - days * _DAY
    old = [p for p in pages if p.mtime < cutoff]
    old.sort(key=lambda p: p.mtime)
    return old


def find_broken_links(pages):
    """[[wiki links]] pointing at a page that doesn't exist.

    A link may name either the frontmatter `name` or the filename stem — and
    those routinely differ (a page titled "세션 요약 2026-07-26" lives in
    session_recent_20260726.md). Matching on only one of them reports
    hundreds of false positives, which trains the reader to ignore the
    section. A trailing `.md` is accepted too.

    A dangling link is legitimate when written (it marks something worth
    writing later), so this is a prompt, not an error.
    """
    known = set()
    for p in pages:
        known.add(p.name)
        known.add(Path(p.path).stem)

    out = []
    for p in pages:
        self_names = {p.name, Path(p.path).stem}
        for target in dict.fromkeys(_LINK_RE.findall(p.body)):
            t = target.strip()
            if t.lower().endswith(".md"):
                t = t[:-3]
            if t and t not in self_names and t not in known:
                out.append((p.name, t))
    return out


# ────────────────────────────── report ────────────────────────────────

def _fmt_age(now: float, mtime: float) -> str:
    return f"{int((now - mtime) / _DAY)}일 전"


def render_report(pages, *, now: float, stale_days: int = DEFAULT_STALE_DAYS,
                  threshold: float = DEFAULT_THRESHOLD,
                  agent_name: str = "agent", top: int = 30) -> str:
    """Markdown report. Proposes only — nothing is modified."""
    dupes = find_duplicate_candidates(pages, threshold=threshold)
    stale = find_stale(pages, now=now, days=stale_days)
    broken = find_broken_links(pages)

    L = [
        f"# 기억 정리 리포트 — {agent_name}",
        "",
        f"- 대상 페이지: **{len(pages)}건**",
        f"- 중복 후보(유사도 ≥ {threshold}): **{len(dupes)}쌍**",
        f"- {stale_days}일 이상 미갱신: **{len(stale)}건**",
        f"- 끊긴 링크: **{len(broken)}건**",
        "",
        "> 이 리포트는 **아무것도 자동 삭제하지 않습니다.** 병합·정정·폐기 판단은",
        "> 사람 또는 에이전트가 각 항목을 읽고 내립니다.",
        "",
        "## 중복 후보",
        "",
    ]
    if dupes:
        L += ["| 유사도 | A | B |", "|---|---|---|"]
        L += [f"| {s:.2f} | `{a.name}` | `{b.name}` |"
              for a, b, s in dupes[:top]]
        if len(dupes) > top:
            L.append(f"| … | _(외 {len(dupes) - top}쌍)_ | |")
    else:
        L.append("_없음_")

    L += ["", f"## {stale_days}일 이상 오래된 페이지", ""]
    if stale:
        L += ["| 마지막 갱신 | 페이지 | 설명 |", "|---|---|---|"]
        L += [f"| {_fmt_age(now, p.mtime)} | `{p.name}` | {p.description} |"
              for p in stale[:top]]
        if len(stale) > top:
            L.append(f"| … | _(외 {len(stale) - top}건)_ | |")
    else:
        L.append("_없음_")

    L += ["", "## 끊긴 링크", ""]
    if broken:
        L += ["| 출처 | 가리키는 곳 |", "|---|---|"]
        L += [f"| `{src}` | `{dst}` |" for src, dst in broken[:top]]
        if len(broken) > top:
            L.append(f"| … | _(외 {len(broken) - top}건)_ |")
        L += ["", "_아직 안 쓴 페이지를 가리키는 링크는 정상입니다 — "
              "'나중에 쓸 것' 표시입니다._"]
    else:
        L.append("_없음_")

    L += ["", "---", "", "*Mokai Brain Kit — memory_consolidation*"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    """python -m brain_share.memory_consolidation --dir <memory md dir>"""
    import argparse
    import os
    import sys
    import time

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description="Monthly memory consolidation report (read-only)")
    ap.add_argument("--dir", required=True, help="directory holding *.md")
    ap.add_argument("--out", default=None, help="write report here")
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--agent", default=os.environ.get("AGENT_NAME", "agent"))
    a = ap.parse_args(argv)

    pages = load_pages(a.dir)
    md = render_report(pages, now=time.time(), stale_days=a.stale_days,
                       threshold=a.threshold, agent_name=a.agent)
    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md, encoding="utf-8")
        print(f"{len(pages)} pages -> {p}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
