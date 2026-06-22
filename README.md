# Mokai Brain Kit

> An on-premises AI knowledge kit that turns a company's scattered memory into one shared AI brain.

Mokai Brain Kit installs on top of an existing RAG + Obsidian + Claude Code setup and adds a **shared gateway**, an **LLM-synthesized canonical wiki**, and an **evolving keyword relation graph** — so your team's AI answers from a single, trustworthy company brain instead of scattered fragments. Everything stays on-premises; no data leaves your network.

## Features

- **Shared gateway (MCP)** — sub-users read the main brain over MCP with a **sensitivity filter (zero leak** of finance / customer / secret data) and key auth, over the LAN.
- **LLM wiki synthesis** — an LLM composes scattered RAG fragments into per-topic **canonical wiki pages** (*find → trust*), stored in Obsidian.
- **Evolving relation graph** — keyword relationships are learned from **co-occurrence weights with time decay**, without touching the source text and **without LLM cost**.
- **Topic auto-discovery** — topics emerge from the data automatically (embedding clustering + merge).
- **Skill bundle** — 6 developer skills bundled, with runtime-tool auto-install.
- **Identity & guideline setup** — assigns the AI a **name** and a working-guideline `CLAUDE.md`, **idempotently** (an existing identity is never overwritten).

## Architecture

Three cooperating memory layers:

| Layer | Role |
|-------|------|
| **Find** | RAG (ChromaDB) — semantic search over raw fragments |
| **Trust** | Obsidian wiki — LLM-synthesized canonical pages |
| **Connect** | Relation graph (SQLite) — evolving keyword weights |

Nodes are **symmetric** (HUB / LEAF), differing only by role. **Privacy by design**: fully on-premises, no external data egress, and a drop-first sensitivity filter so internal data is never exposed to readers.

## Quick Start

Requires **Python 3.12+** and **Claude Code**.

```bash
python install.py            # install brain_share modules (additive, data-preserving)
python install_skills.py     # install the skill bundle + runtime tools
python setup_identity.py --name myagent --role "My Company"
```

Every step is **additive and idempotent** — existing data and identity are never overwritten, and an uninstall simply removes what was added.

## Requirements

- Python 3.12+
- [Claude Code](https://claude.com/claude-code)
- Python packages: `numpy`, `scikit-learn`, `pyyaml`, `mcp`, `chromadb`

## How it stays safe

- **On-premises** — your knowledge never leaves your own machines (no external upload).
- **Zero-leak filter** — sensitive categories (accounting, customer, secrets) are blocked from shared reads by default.
- **Data-preserving** — installs alongside existing memory; nothing is deleted or migrated.

## License

[MIT](LICENSE) © 2026 Mokai
