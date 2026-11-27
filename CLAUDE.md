# podcastz – notes for AI coding assistants

podcastz is a framework for learning through self-prepared podcasts: an AI session (with the plugin in `plugin/` or by following a project's `AGENTS.md`) interviews the user, researches, writes a two-voice dialogue script and reviews it against sources; the `podcastz` CLI turns scripts into audio. See `README.md` and `docs/design.md`.

If a `CLAUDE.local.md` exists next to this file, read it too: it holds the maintainer's private context and is never committed.

## Layout

- `core/` – Python package and CLI `podcastz` (stdlib only at runtime). Modules: `project.py` (project folder, state, segment plan, script parsing), `check.py` (validation gate), `pricing.py` (+ `data/languages.json`, `data/pricing.json`), `tts.py` (OpenAI, ElevenLabs), `audio.py` (ffmpeg normalisation, mixing, timing manifest), `cli.py`, project template in `templates/project/`.
- `plugin/` – Claude Code plugin (skills `setup`, `prepare`, `research`, `script`, `review`, `audio`; hooks reporting the session to the app); marketplace in `.claude-plugin/marketplace.json`.
- `app/` – desktop app, Tauri 2 (Rust) + Svelte 5; runs the CLI per task with `--json`. `cd app; npm run check`, `cd app/src-tauri; cargo clippy --all-targets -- -D warnings; cargo test`.
- `CHANGELOG.md` – release notes, shown by the app and used as the GitHub Release body; every version needs an entry (a Rust test checks it, and that `tauri.conf.json`, `Cargo.toml` and `package.json` carry the same version).
- `docs/design.md` – architecture, including the planned desktop app (Tauri 2 + Python sidecar) and packaging.

## Working on the code

- `cd core; uv sync --group dev; uv run --group dev pytest -q` runs the tests; `ffmpeg` on PATH enables the audio test.
- `uv tool install --editable core` puts `podcastz` on PATH for trying it on real project folders.
- `claude plugin validate plugin` and `claude plugin validate .` check the plugin and the marketplace.
- The segment cache key (hash of text, voice, model and settings in `Project.segment_key`) must stay stable: changing it makes every existing project pay to regenerate its audio.
- Script format changes must keep `check.py`, `Project.lines/outline/script`, the template `AGENTS.md` and the `script` skill consistent.

## Releasing

1. `node scripts/bump-version.mjs X.Y.Z` (app, Rust, Tauri config and the Python CLI get one version; the plugin keeps its own).
2. Add `## X.Y.Z – YYYY-MM-DD` with the release notes to `CHANGELOG.md` (the app shows it; it becomes the GitHub Release body).
3. Commit, tag `vX.Y.Z`, push the tag. `.github/workflows/release.yml` checks the versions, creates a draft release, builds Windows (`.msi` and `-setup.exe`, per-machine, `app/src-tauri/windows/main.wxs`), Linux and macOS with the frozen CLI bundled (`core/packaging/`, `app/src-tauri/tauri.release.conf.json`), and publishes the release only when every build succeeded.
- Installers are not code-signed; updater artifacts are signed with the minisign key from the repository secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` (public key in `tauri.conf.json`). The private key and its password never go into the repository.

## Data boundary (binding)

- The repository holds only the framework. No podcast data of any kind: no sources, scripts, audio, cache, voice IDs from a private account, API keys, or names of real podcast projects in code, tests or docs. Tests use synthetic fixtures.
- Every podcast is one self-contained project folder outside this repository; the tool works on it by path and never copies its content elsewhere.
- Keys only in the OS credential store or environment variables, never in files, logs, command lines or test output (tests use the in-memory fake vault from `core/tests/conftest.py`).

## Conventions

- Repository content and documentation in English; files and projects in lowercase kebab-case; episodes `NN-slug.md` / `NN-slug.mp3` / `NN-slug.json`.
- Prices in `core/src/podcastz/data/pricing.json` carry an `as_of` date; verify before relying on them.
- Commits only after the maintainer's explicit OK; no references to AI sessions and no AI co-author trailers in commit messages.
