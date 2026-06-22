---
name: youtube-summary
description: Analyze and summarize the CONTENT of a YouTube video by extracting its transcript/subtitles. 유튜브 영상 링크를 주며 "이 영상 요약해줘 / 무슨 내용이야 / 분석해줘"라고 하거나, 강의·튜토리얼·인터뷰·경쟁사 채널 영상의 내용 파악, 영상을 끝까지 보지 않고 핵심만 알고 싶을 때 사용. Use whenever the user provides a YouTube URL (youtube.com or youtu.be) and wants to know what it is about.
---

# YouTube 영상 내용 분석·요약

유튜브 URL에서 자막(스크립트)을 받아, 영상을 보지 않고 내용을 파악·요약한다.

## 워크플로우

1. 사용자가 준 유튜브 URL을 확인한다 (`youtube.com/watch?v=...` 또는 `youtu.be/...`).
2. 자막 추출 스크립트를 실행한다:

   ```powershell
   python "C:\Users\neole\.claude\skills\youtube-summary\scripts\yt_transcript.py" "<URL>"
   ```

   - 한국어 자막을 우선, 없으면 영어, 그래도 없으면 자동생성 자막을 사용한다.
   - 다른 언어를 원하면 `--lang ja,en` 처럼 지정한다.
   - 매우 긴 영상은 `--max-chars 40000` 으로 앞부분만 받는다.

3. 출력된 제목·메타데이터와 `[MM:SS]` 타임스탬프 자막을 읽고, 사용자가 요청한 형태로 정리한다.
   - 기본: 한 줄 요약 + 구간별 핵심(타임스탬프) + 결론/시사점.
   - 사용자가 특정 관점(마케팅 인사이트, 경쟁사 전략, 따라할 점 등)을 말하면 그 관점으로 분석한다.

## 출력 형식 (기본)

- **한 줄 요약**: 영상이 무엇에 관한 것인지.
- **핵심 내용**: 타임스탬프와 함께 5~10개 불릿.
- **시사점/결론**: (요청 시) 사용자의 사업·관심사 관점의 한마디.

## 주의사항

- 자막이 아예 없는 영상(자막 비공개)은 분석 불가 → 사용자에게 명확히 알린다.
- "Sign in to confirm you're not a bot" 등 봇 차단이 나오면 브라우저 쿠키를 사용한다:
  ```powershell
  python "C:\Users\neole\.claude\skills\youtube-summary\scripts\yt_transcript.py" "<URL>" --cookies-from-browser chrome
  ```
- 자동생성 자막은 오타·동음이의 오류가 있을 수 있으니, 고유명사·숫자는 추정임을 표시한다.
- 의존성(`yt-dlp`)은 이미 설치되어 있다. 없으면 `pip install -U yt-dlp`.
