"""Tests for the monthly memory consolidation pass."""
import pytest

from brain_share.memory_consolidation import (
    MemoryPage,
    find_broken_links,
    find_duplicate_candidates,
    find_stale,
    parse_page,
    render_report,
    similarity,
)

FM = """---
name: project_alpha
description: "알파 프로젝트 진행 상황"
metadata:
  type: project
---

본문입니다. [[project_beta]] 를 참조.
"""


def page(name, body="", desc="", mtime=0.0, ptype="project"):
    return MemoryPage(name=name, description=desc, type=ptype, body=body,
                      mtime=mtime, path=f"{name}.md")


# ────────────────────────────── parsing ───────────────────────────────

def test_parse_page_reads_frontmatter_and_body():
    p = parse_page("project_alpha.md", FM, mtime=123.0)
    assert p.name == "project_alpha"
    assert p.description == "알파 프로젝트 진행 상황"
    assert p.type == "project"
    assert "본문입니다" in p.body
    assert p.mtime == 123.0


def test_parse_page_without_frontmatter_falls_back_to_filename():
    p = parse_page("loose_note.md", "그냥 본문", mtime=1.0)
    assert p.name == "loose_note"
    assert p.description == ""
    assert p.body == "그냥 본문"


def test_parse_page_tolerates_malformed_frontmatter():
    """A half-written file must not abort the whole monthly pass."""
    p = parse_page("broken.md", "---\nname: [unclosed\n---\nbody", mtime=1.0)
    assert p.name in ("broken", "[unclosed")
    assert "body" in p.body


# ───────────────────────────── similarity ─────────────────────────────

def test_similarity_identical_is_one():
    assert similarity("조이듀 블로그 자동 발행", "조이듀 블로그 자동 발행") == 1.0


def test_similarity_disjoint_is_zero():
    assert similarity("코인 급등봇", "옵시디언 볼트 경로") == 0.0


def test_similarity_is_symmetric_and_partial():
    a, b = "조이듀 블로그 자동 발행 파이프라인", "조이듀 블로그 발행 검증"
    s = similarity(a, b)
    assert 0.0 < s < 1.0
    assert s == similarity(b, a)


def test_similarity_handles_empty():
    assert similarity("", "") == 0.0
    assert similarity("무언가", "") == 0.0


# ──────────────────────────── duplicates ──────────────────────────────

def test_finds_near_duplicate_pair():
    pages = [
        page("blog_publish_a", "조이듀 블로그 자동 발행 파이프라인 매일 11시 실행",
             desc="블로그 자동 발행"),
        page("blog_publish_b", "조이듀 블로그 자동 발행 파이프라인 매일 11시 가동",
             desc="블로그 자동 발행"),
        page("coin_bot", "업비트 급등봇 백테스트 손실 구간 분석"),
    ]
    dupes = find_duplicate_candidates(pages, threshold=0.5)
    names = {tuple(sorted((a.name, b.name))) for a, b, _ in dupes}
    assert ("blog_publish_a", "blog_publish_b") in names
    assert not any("coin_bot" in n for n in names)


def test_duplicate_pairs_are_not_double_reported():
    pages = [page("a", "같은 내용 같은 내용"), page("b", "같은 내용 같은 내용")]
    assert len(find_duplicate_candidates(pages, threshold=0.3)) == 1


def test_page_is_never_its_own_duplicate():
    pages = [page("solo", "어떤 내용")]
    assert find_duplicate_candidates(pages, threshold=0.0) == []


def test_threshold_is_respected():
    pages = [page("a", "완전히 다른 하나"), page("b", "전혀 무관한 둘")]
    assert find_duplicate_candidates(pages, threshold=0.9) == []


# ────────────────────────────── staleness ─────────────────────────────

def test_find_stale_uses_cutoff():
    day = 86400.0
    now = 100 * day
    pages = [page("fresh", mtime=now - 10 * day),
             page("old", mtime=now - 90 * day)]
    stale = find_stale(pages, now=now, days=60)
    assert [p.name for p in stale] == ["old"]


def test_find_stale_sorted_oldest_first():
    day = 86400.0
    now = 100 * day
    pages = [page("mid", mtime=now - 70 * day),
             page("oldest", mtime=now - 95 * day)]
    assert [p.name for p in find_stale(pages, now=now, days=60)] == [
        "oldest", "mid"]


# ──────────────────────────── broken links ────────────────────────────

def test_find_broken_links_reports_missing_target():
    pages = [page("a", "관련 [[b_exists]] 그리고 [[c_missing]]"),
             page("b_exists", "본문")]
    broken = find_broken_links(pages)
    assert broken == [("a", "c_missing")]


def test_broken_links_ignore_self_reference():
    pages = [page("a", "나 자신 [[a]]")]
    assert find_broken_links(pages) == []


def test_link_may_name_the_filename_instead_of_the_title():
    """Frontmatter name and filename routinely differ — a page titled
    '세션 요약 2026-07-26' lives in session_recent_20260726.md. Matching on
    only one of them floods the report with false positives."""
    target = MemoryPage(name="세션 요약 2026-07-26", description="", type="",
                        body="", mtime=0.0,
                        path="session_recent_20260726.md")
    src = page("a", "지난 대화 [[session_recent_20260726]] 참조")
    assert find_broken_links([src, target]) == []


def test_link_with_md_extension_still_resolves():
    pages = [page("a", "[[b.md]] 참조"), page("b", "본문")]
    assert find_broken_links(pages) == []


def test_self_reference_by_filename_is_not_broken():
    p = MemoryPage(name="제목", description="", type="", body="[[real_file]]",
                   mtime=0.0, path="real_file.md")
    assert find_broken_links([p]) == []


# ────────────────────────────── report ────────────────────────────────

def test_report_lists_every_section_and_never_deletes():
    day = 86400.0
    now = 100 * day
    pages = [page("a", "같은 내용 [[ghost]]", mtime=now - 90 * day),
             page("b", "같은 내용", mtime=now)]
    md = render_report(pages, now=now, stale_days=60, threshold=0.3,
                       agent_name="kim")
    assert "중복 후보" in md
    assert "오래된" in md
    assert "끊긴 링크" in md
    assert "ghost" in md
    # The report proposes; a human/LLM disposes.
    assert "삭제하지 않습니다" in md or "자동 삭제" in md


def test_report_on_empty_memory_dir_is_still_valid():
    md = render_report([], now=0.0, stale_days=60, threshold=0.5,
                       agent_name="kim")
    assert "0" in md and "중복 후보" in md
