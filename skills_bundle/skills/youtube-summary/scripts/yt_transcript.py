#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yt_transcript.py - 유튜브 자막 추출 + 정리 (youtube-summary 스킬용)

사용법:
    python yt_transcript.py <youtube_url> [--lang ko,en] [--max-chars N] [--cookies-from-browser chrome]

- 수동 자막을 우선 시도하고, 없으면 자동생성 자막을 사용한다.
- 자동자막의 롤링 중복을 제거하고 30초 간격 타임스탬프를 붙여 출력한다.
- 의존성: yt-dlp (PATH).
"""
import sys
import os
import re
import json
import glob
import shutil
import tempfile
import subprocess
import argparse

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

YTDLP = shutil.which("yt-dlp") or "yt-dlp"
TAG_RE = re.compile(r"<[^>]+>")
CUE_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.\d{3}\s*-->")


def fetch(url, langs, cookies):
    tmp = tempfile.mkdtemp(prefix="ytsub_")
    out = os.path.join(tmp, "%(id)s.%(ext)s")
    cmd = [YTDLP, "--skip-download", "--no-warnings",
           "--write-subs", "--write-auto-subs",
           "--sub-langs", langs, "--sub-format", "vtt",
           "--retries", "8", "--retry-sleep", "5",
           "--write-info-json", "-o", out, url]
    if cookies:
        cmd += ["--cookies-from-browser", cookies]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return tmp, (p.stderr or "")


def lang_rank(path, langs):
    order = [l.strip() for l in langs.split(",")]
    parts = os.path.basename(path).rsplit(".", 2)   # <id>.<lang>.vtt
    code = parts[1] if len(parts) == 3 else ""
    for i, l in enumerate(order):
        if code.startswith(l):
            return i
    return len(order) + 1


def parse_vtt(path, interval=30):
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    items, cur = [], 0
    for line in raw.splitlines():
        s = line.strip()
        m = CUE_RE.match(s)
        if m:
            h, mi, se = m.groups()
            cur = int(h) * 3600 + int(mi) * 60 + int(se)
            continue
        if not s or "-->" in s or s.upper() == "WEBVTT":
            continue
        if s.startswith(("Kind:", "Language:", "NOTE")):
            continue
        text = TAG_RE.sub("", line).strip()
        if text:
            items.append((cur, text))
    # 롤링 중복 제거
    cleaned, last = [], None
    for sec, text in items:
        if text == last:
            continue
        if last is not None and text.startswith(last):
            cleaned[-1] = (cleaned[-1][0], text)   # 직전 줄을 더 완성된 줄로 교체
            last = text
            continue
        cleaned.append((sec, text))
        last = text
    # 타임스탬프 라벨링
    out, last_emit = [], -10 ** 9
    for sec, text in cleaned:
        if sec - last_emit >= interval:
            h, mi, se = sec // 3600, (sec % 3600) // 60, sec % 60
            label = "[%02d:%02d]" % (mi, se) if h == 0 else "[%d:%02d:%02d]" % (h, mi, se)
            out.append("%s %s" % (label, text))
            last_emit = sec
        else:
            out.append(text)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--lang", default="ko,en")
    ap.add_argument("--max-chars", type=int, default=0)
    ap.add_argument("--cookies-from-browser", default=None)
    a = ap.parse_args()

    info, transcript, err = None, None, ""
    tmp, err = fetch(a.url, a.lang, a.cookies_from_browser)
    tmps = [tmp]
    ij = glob.glob(os.path.join(tmp, "*.info.json"))
    if ij:
        with open(ij[0], encoding="utf-8") as f:
            info = json.load(f)
    vtts = glob.glob(os.path.join(tmp, "*.vtt"))
    if vtts:
        vtts.sort(key=lambda p: lang_rank(p, a.lang))
        transcript = parse_vtt(vtts[0])

    if info:
        dur = info.get("duration") or 0
        print("# %s" % info.get("title", "(제목 없음)"))
        print("- 채널: %s" % info.get("uploader", "?"))
        if dur:
            print("- 길이: %d분 %d초" % (dur // 60, dur % 60))
        print("- 조회수: %s" % info.get("view_count", "?"))
        print("- 업로드: %s" % info.get("upload_date", "?"))
        print("- URL: %s" % info.get("webpage_url", a.url))
        print()

    if transcript:
        print("## 자막")
        if a.max_chars and len(transcript) > a.max_chars:
            transcript = transcript[:a.max_chars] + "\n...(이하 생략)"
        print(transcript)
    else:
        low = err.lower()
        if "429" in err or "too many requests" in low:
            print("YouTube 자막 서버가 요청을 일시 제한(429)하고 있습니다.")
            print("→ 잠시 후(보통 30분 내) 다시 시도하거나, 브라우저를 완전히 종료한 뒤 --cookies-from-browser chrome 옵션을 사용하세요.")
        elif "cookie" in low:
            print("브라우저 쿠키 DB가 잠겨 있습니다(브라우저 실행 중).")
            print("→ 해당 브라우저를 완전히 종료한 뒤 다시 시도하세요.")
        else:
            print("자막을 찾을 수 없습니다. 자막이 비공개거나 지정한 언어가 없을 수 있습니다.")
        sys.stderr.write("[stderr] " + (err[-400:] if err else "") + "\n")
        for t in tmps:
            shutil.rmtree(t, ignore_errors=True)
        sys.exit(2)

    for t in tmps:
        shutil.rmtree(t, ignore_errors=True)


if __name__ == "__main__":
    main()
