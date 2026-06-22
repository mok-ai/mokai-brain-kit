# Contributing to Mokai Brain Kit

Thanks for your interest in improving Mokai Brain Kit!

## Getting started
1. Fork and clone the repository.
2. Install dependencies: `pip install numpy scikit-learn pyyaml mcp chromadb pytest`.
3. Run the tests: `python -m pytest tests -q`.

## Guidelines
- **Tests first** — the core logic is fully unit-tested with injected dependencies (no model/network needed). Keep it that way; add tests with every change.
- **No data leaks** — the sensitivity filter is the security core. Any change to read paths must preserve the zero-leak guarantee and add a test proving it.
- **Additive & idempotent** — installers must never overwrite a user's existing data or identity.
- Keep modules small and focused (one responsibility per file).

## Pull requests
- Describe what changed and why.
- Ensure `python -m pytest tests -q` passes.
- Update `CHANGELOG.md` under the appropriate version.

## License
By contributing, you agree that your contributions are licensed under the MIT License.
