# podcastz – design

A personal tool for learning through podcasts you prepare yourself. You describe what you want to understand; your own AI session (Claude Code or another agentic CLI) interviews you, researches, writes a two-voice dialogue script and reviews it against the sources; the desktop app turns the script into audio with a cost estimate, lets you listen and publishes the files to a folder you sync to your phone.

Status: draft, 2026-10-07.

## 1. Principles

- **AI preparation happens in the user's own AI session, not inside the app.** It's a conversation the user steers (brief changes, level of detail, length), and it runs on the user's own subscription. The app never calls a language model and never handles AI credentials. Anthropic doesn't allow third-party apps to offer claude.ai login, so the app only *opens a terminal* with the user's interactive client.
- **The project folder is the contract.** The AI session and the app never talk directly; they read and write files with a defined format. Any AI client that can follow `AGENTS.md` can prepare a podcast.
- **Audio is the app's job.** TTS costs money, so the app shows the price and asks before generating. Generation is deterministic, cached by content and repeatable.
- **Generic and open.** No personal data, keys, voices from a private account or employer content in the repository. Podcast projects live outside the repo in a user-chosen data folder.

## 1a. Workspace: what the app sees and where the skills live (2026-11-02)

In practice one AI session works on many podcasts at once (a production repository with one folder per podcast). So the unit the app opens is a **workspace**, not a single project:

```
<workspace>/                       e.g. a private repository with your podcasts
  podcastz.workspace.json          marker + settings (projects folder, defaults)
  .claude/settings.json            enables the podcastz plugin for every session started here
  .podcastz/                       runtime files, gitignored
    session.json                   the AI session as reported by the plugin hooks
    app.json                       the running app (local URL + token), written by the app
    requests/<id>.json             requests from the app to the session
  <slug>/                          one folder per podcast (podcast.json, sources/, text/, work/, audio/, cache/)
```

- `podcastz workspace init <dir>` creates the marker, `.podcastz/` with its `.gitignore`, and project-scoped plugin settings, so the skills are available to any session started in the workspace.
- **The app knows the session**: plugin hooks (`SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd`) call `podcastz hook …`, which writes `.podcastz/session.json` (session id, client, state `busy`/`idle`/`ended`, current project, time). The app shows it and offers *Open AI session* (focus or `claude --continue` in the workspace, §5).
- **The session knows the app**: the app writes `.podcastz/app.json` while it runs. Skills call `podcastz app notify|show`, which reach the app if it runs and do nothing otherwise, so the console workflow keeps working without the app.
- **The app asks the session**: buttons such as *Find more sources on…*, *Re-check this source*, *Shorten episode 2* write `.podcastz/requests/<id>.json`. The plugin's `SessionStart` and `UserPromptSubmit` hooks put pending requests into the session's context, and the app focuses the session window; the session handles them and marks them done with `podcastz request done <id>`. Nothing is typed into the terminal on the user's behalf.
- **Sources are curated together**: `sources/index.json` in each project lists every source (title, origin, file, who added it, status `proposed` / `approved` / `rejected`, note). The `research` skill adds proposals with `podcastz source add`; the user approves, rejects or adds sources in the app (or tells the session); the `script` and `review` skills use approved sources only.

## 2. Components

```
podcastz/                       (this repo, public)
  core/          Python package `podcastz` + CLI: project format and template (AGENTS.md, BRIEF.md),
                 check, state, sources, workspace, keys, estimate/quote, TTS, cache, mix, publish;
                 `--json` output (JSON lines for long tasks) is the app's protocol
  app/           Tauri 2 (Rust, thin) + Svelte 5 / Vite / TypeScript UI
  plugin/        Claude Code plugin: skills (prepare, research, script, review, audio), hooks (session state, requests)
  docs/
```

```
┌─ Tauri app ──────────────────────────────────────────────┐
│ Rust: runs the CLI per task, streams JSON lines as events,│
│       cancels (kill), launches/focuses the AI session     │
│ UI: workspace, project (sources, scripts, audio), settings│
└──────────────┬───────────────────────────────────────────┘
               │ spawn `podcastz --json …` (stdin for secrets)
┌──────────────▼──────────────┐      files       ┌──────────────────────────┐
│ podcastz CLI (sidecar)      │◄────────────────►│ workspace / project      │
│ core: check, estimate, TTS, │                  │ BRIEF, sources/index,    │
│ cache, mix, publish, keys   │                  │ text, state, .podcastz/  │
└─────────────────────────────┘                  └────────────▲─────────────┘
                                                              │ writes, hooks
                                              ┌───────────────┴──────────────┐
                                              │ user's AI session (terminal) │
                                              │ claude + podcastz plugin, or │
                                              │ another client via AGENTS.md │
                                              └──────────────────────────────┘
```

Backend choice (2026-11-02, on the devstack's advice): **the sidecar is the CLI itself**, no server. The app spawns `podcastz --json …` per task; short commands return one JSON object, long ones (build, sample, publish) print JSON lines (`plan`, `progress`, `episode`, `error`, `done`) that Rust forwards to the UI as events; cancelling kills the process. One code path for console and app, no port, no token. In development the app uses `podcastz` from PATH (or `$PODCASTZ_CLI`); for distribution the CLI is frozen with PyInstaller as `podcastz-cli-<target-triple>` and bundled as a Tauri `externalBin`.

**API keys** (same approach as other personal apps): the OS credential store through Python `keyring`, service `podcastz`, user name = provider (`openai`, `elevenlabs`). Lookup order (devstack secrets standard): `PODCASTZ_<PROVIDER>_API_KEY` as an explicit override, then the stored key, then the provider's generic variable (`OPENAI_API_KEY`, `ELEVENLABS_API_KEY`) last, so a stale generic variable never hides a key saved in Settings. Saving in the app verifies the key at once; the last result and its time are shown (stored in the app settings, never the key). The app reads and writes the same entry in Rust (devstack decision: app foundations in Rust): on Windows it calls Credential Manager directly with Python keyring's naming (TargetName `podcastz` for the first provider, `<provider>@podcastz` for others, UTF-16 blob), because the Rust `keyring` crate names Windows targets differently; on macOS and Linux it uses the `keyring` crate. Verified both ways (Rust writes, Python reads, and back). The Settings page only ever sees where a key comes from, never its value; `podcastz key test` checks a key against the provider's read-only models endpoint. Python tests use an in-memory fake vault; the Rust interop tests are `#[ignore]` and use a throwaway service name.


## 3. Project folder (the contract)

```
<data-folder>/<slug>/
  podcast.json    settings: title, language, speakers, voices, TTS provider/model, audio, publish_dir
  BRIEF.md        what the user wants: topic, audience, goal, length, level, language, source policy
  state.json      stage + progress written by the AI session, read by the app
  AGENTS.md       instructions for any AI client: steps, file formats, rules (copied from templates/)
  sources/        research material with provenance (one file per source or topic)
  work/           drafts, reviews, notes of the AI session
  text/           final scripts NN-slug.md + README.md
  audio/          generated MP3; samples/
  cache/          TTS segments (paid, keep) and normalized WAVs
  .podcastz/      app-private: agent.lock, launch info
```

`state.json`:

```json
{
  "stage": "interview | research | script | review | ready",
  "updated": "2026-10-07T10:00:00Z",
  "message": "Research: 7 sources collected",
  "episodes": [{"file": "01-intro.md", "status": "draft | reviewed | final"}]
}
```

Script format (unchanged from the existing tool): line 1 `# Episode NN – Title`, line 2 `Part N of M | Estimated length: ~10 min`, then only lines `SPEAKER: text`. Speakers come from `podcast.json`. No markdown, URLs or symbols inside lines; abbreviations expanded on first use; numbers written so that TTS reads them correctly. `podcastz check <project>` validates this and is the gate to `stage: ready`.

## 4. Flow: new podcast

1. **App → "New podcast".** Asks only for the name and the project folder (default `<data-folder>/<slug>`). The AI client comes from app settings (per-project override possible).
2. **App prepares the folder** from `templates/`: `AGENTS.md`, skeleton `podcast.json`, `state.json` with `stage: interview`, empty folders. For Claude Code it checks that the `podcastz` plugin is installed and offers the install commands if not.
3. **App starts the AI session** in the folder (see §5), with the first instruction: Claude Code `claude -n podcastz-<slug> "/podcastz:prepare"`; other clients their own command plus "Read AGENTS.md and start the interview".
4. **The session interviews the user**: topic, what they want to learn, prior knowledge, audience, length, level of detail, language, own materials vs web. Result: `BRIEF.md`, language and length in `podcast.json`. From here the app can show a cost estimate.
5. **Research → script → review** in the session, writer and reviewer as separate agents (reviewer checks every claim against `sources/`). Each step updates `state.json`; the user can steer at any time.
6. **Gate**: the session runs `podcastz check`; only if it passes it sets `stage: ready` and tells the user to return to the app.
7. **App** (watching the folder all along) shows sources, scripts, review verdict and the estimate by actual character count; at `ready` it enables **Generate audio** (with price confirmation), then the player and **Publish**.

The user never has to signal the app; the app reacts to file changes.

## 5. Launching and finding the AI session (Windows first)

- **Launch**: `wt.exe -w podcastz-<slug> new-tab --title "podcastz · <slug>" -d <project> powershell.exe -NoExit -Command "<client command>"`. One named Windows Terminal window per project, so it can be focused later. Fallback without Windows Terminal: `powershell.exe -NoExit` in a new console window.
- **Continue vs new**: if the folder already has a conversation, `claude --continue -n podcastz-<slug>`; otherwise a new session with the first instruction. Other clients: templates in settings (`new`, `continue`, `first prompt`).
- **No second session**:
  - Claude Code: plugin hooks `SessionStart` / `SessionEnd` write and remove `.podcastz/agent.lock` (`pid`, `started`, `client`). Works even when the user started `claude` manually in the folder.
  - App-launched sessions: the app also stores the wrapper PID in `.podcastz/launch.json`; alive = process exists and has a child process of the client.
  - If a live session exists → focus its window (`wt -w podcastz-<slug> focus-tab -t 0`) instead of launching. Stale lock (process gone) → remove and offer **Continue**.
  - Other clients have no hooks: detection only covers sessions the app launched.
- **Pitfalls** (from the existing launcher scripts): a bare `;` in a `wt` command line separates commands (escape as `\;`); quote paths with spaces and diacritics in `-Command`; PowerShell 5.1 scripts must be UTF-8 with BOM; never `start script.ps1` (opens an editor), always `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`.

## 6. App screens

- **Projects**: list with stage, episodes, length, cost; data-folder setting.
- **New podcast**: name + folder → creates and launches (§4).
- **Project**: stage timeline from `state.json`; buttons *Open AI session* (focus or launch) and *Generate audio*; sources list; estimate.
- **Editor**: per-episode script with line validation (`check`), lines changed since the last build highlighted with their cost to regenerate.
- **Player**: episode audio with the script alongside; regenerate one line.
- **Build**: progress from the CLI's JSON lines (line X of Y, characters, cost so far), cancel; then *Publish* to `publish_dir`.
- **Settings**: data folder, AI client profiles, TTS keys (stored in the OS credential store, never in project files), default TTS model, voices.

## 7. Claude Code plugin (`plugin/`)

- Distributed from this repo as a plugin marketplace (`.claude-plugin/marketplace.json` at the root, plugin in `plugin/`): `/plugin marketplace add drzdez/podcastz` (or a local path), `/plugin install podcastz@podcastz`.
- Skills (implemented): `prepare` (orchestrates interview → research → script → review → check), `research`, `script`, `review` and `audio` (estimate, sample, build only after the user approves the price, publish), each usable on its own. Until the app exists, `audio` is how a console session produces the episodes.
- Hooks (with the app, later): session lock (§5) and `state.json` touch on stop.
- The skills call the `podcastz` CLI, installed with `uv tool install --editable core` (or from PyPI later).
- The same steps are written for any client in `templates/AGENTS.md`, so the plugin is a convenience, not a requirement.

## 8. TTS and cost

Providers and prices in `core` data files (dated; verify before relying on them): ElevenLabs (per character; best quality for Czech), OpenAI `gpt-4o-mini-tts` (per audio minute, accepts pronunciation instructions), `tts-1`. Duration and cost estimates use measured characters per audio hour per language and provider; every sample and build refines them. The cache key is a hash of text, voice, model and settings, so editing one line regenerates only that line.

## 9. Distribution and updates

- **Windows**: `.msi` installer (Tauri bundler) with **auto-update** through `tauri-plugin-updater`: signed update artifacts, update manifest (`latest.json`) published with GitHub Releases, the app checks on start and offers to install.
- **Linux and macOS** builds from the same code: AppImage / `.deb`, `.dmg` / `.app`. Built in GitHub Actions on a windows / ubuntu / macos matrix; each platform freezes its own Python sidecar (PyInstaller) and bundles it as a Tauri `externalBin` with the target-triple suffix.
- MSI version numbers must stay within MSI limits (semver `MAJOR.MINOR.PATCH`, no pre-release text in the MSI version).
- Reference setup (proven in another personal Tauri app, markdownz):
  - `bundle`: `targets: "all"`, identifier `io.github.drzdez.podcastz`, `createUpdaterArtifacts: true`; Windows produces `.msi` (WiX) and NSIS `-setup.exe`. A custom WiX template (`windows/main.wxs`, copy of the Tauri template) keeps per-machine installs from triggering Windows Installer "repair" for other users; re-sync it with upstream when upgrading the Tauri CLI.
  - Updater: `tauri-plugin-updater` + `tauri-plugin-process`; endpoint `https://github.com/drzdez/podcastz/releases/latest/download/latest.json`; `windows.installMode: "passive"`; minisign key from `npx tauri signer generate` (private key and password outside the repo, in GitHub secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, backed up; losing it means existing installs can't update). The UI checks at start at most once a day (Settings: Check now) and offers Install now / Later / Skip this version with download progress. Linux packages from a distro or Flatpak get a "manual" update mode (link only); AppImage, Windows and macOS self-update.
  - CI: `.github/workflows/release.yml` on tag `v*` with `tauri-apps/tauri-action`, matrix macos (aarch64 and x86_64), ubuntu-22.04 (deps `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf`), windows; draft release. A separate CI workflow runs tests and `cargo clippy -D warnings`.
  - No Windows code signing or Apple notarization (unsigned builds; only update artifacts are signed). WebView2 is not bundled (preinstalled runtime).
- **New compared to the reference: the Python sidecar.** Each CI runner builds it with PyInstaller (`podcastz-cli-<target-triple>[.exe]`) before `tauri-action`, and `bundle.externalBin` includes it. ffmpeg stays a system requirement at first (the app checks and explains how to install it); bundling it is a later option.
- The Python CLI (`podcastz`) stays installable on its own (`uv tool install`) for console-only use.
- **State in the app today:** updater and process plugins are wired (Settings: automatic check on/off, Check now, skip version; banner with Install and restart, disabled while an audio task runs), release notes from `CHANGELOG.md` shown once per version and in Help. Still missing for the first release: the minisign public key in `tauri.conf.json` (`plugins.updater.pubkey` is empty, so an install would fail signature verification, never install unverified), `bundle.createUpdaterArtifacts`, the WiX template, the sidecar build, an app icon, and the release workflow, following the devstack release standard.
- **CLI discovery (lesson):** the app never runs a bare `podcastz`, never a program inside its own folder tree (on Windows `cargo run` puts `target/debug/deps` first on PATH, and an old build of the app there once started itself without end), and never a GUI-subsystem executable; a child started by the app exits at once if it is the app.

## 10. Out of scope (for now)

- The app calling an LLM API itself (possible later as an optional plugin with the user's own API key).
- Podcast hosting / RSS feed, ID3 chapters, intro music.
- macOS / Linux AI-session launch specifics in the first version (builds exist, launching uses a generic terminal; the launcher is one module).

## 11. Plan

1. Repo skeleton, `core` (port and generalization of the existing CLI), `podcastz check`, project template, `AGENTS.md`.
2. Claude Code plugin: `prepare` skill and lock hooks; try it end to end on one small podcast from the console.
3. JSON-lines protocol of the CLI (the app's sidecar), workspace, keys in the OS credential store.
4. Tauri app: projects, new podcast + launch/focus session, project view with live state, editor, player, build, publish, settings.
5. Packaging: PyInstaller sidecar per platform, `.msi` with auto-update, Linux and macOS builds in GitHub Actions; README, license, publish the repo.
