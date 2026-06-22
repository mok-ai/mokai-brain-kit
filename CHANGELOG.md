# Changelog

All notable changes to Mokai Brain Kit are documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

## [3.0.0] - 2026-06-22

### Added
- Shared brain gateway (MCP) with a drop-first sensitivity filter (zero leak) and key authentication.
- LLM wiki synthesis — RAG fragments composed into per-topic canonical wiki pages (Obsidian).
- Automatic topic discovery (embedding clustering + merge).
- Evolving relation graph — keyword co-occurrence weights with time decay, computed without LLM calls.
- Skill bundle (6 skills) with runtime-tool auto-install.
- Identity & guideline setup — assigns an agent name and a working-guideline CLAUDE.md, idempotently.

## [2.1.0] - 2026-06-14
### Changed
- Single source of truth for configuration via `AGENT_NAME`; Obsidian export auto-derives paths.

## [2.0.0] - 2026-06-13
### Added
- Memory transfer pipeline; Solo / Federated modes.

## [1.0.0] - 2026-06-13
### Added
- Initial brain transplant standard: RAG + Obsidian + skills + CLAUDE.md + watchdog.
