# podcastz

Learn by listening to podcasts you prepare yourself.

You describe what you want to understand. Your own AI session (Claude Code or another agentic CLI) interviews you, researches the topic, writes a two-voice dialogue script and checks every claim against the sources. podcastz turns the script into audio with text-to-speech, tells you the price before it spends anything, and publishes the episodes to a folder you sync to your phone.

> Status: early development. The `core` CLI and the Claude Code plugin work; the desktop app runs from source, installers will follow on the Releases page. See [docs/design.md](docs/design.md) and [CHANGELOG.md](CHANGELOG.md).

## Quick start

```sh
uv tool install --editable ./core                  # the `podcastz` command, from a clone of this repo
```

In Claude Code:

```
/plugin marketplace add drzdez/podcastz            # or the path of your clone
/plugin install podcastz@podcastz
/podcastz:prepare                                  # in an empty folder or an existing project
```

The skills (`setup`, `prepare`, `research`, `script`, `review`, `audio`) are described in [plugin/README.md](plugin/README.md). Installation step by step: [docs/getting-started.md](docs/getting-started.md); how the AI session, your approvals and the audio machinery exchange data: [docs/how-it-works.md](docs/how-it-works.md). Other AI tools can follow the `AGENTS.md` that `podcastz new` puts into every project.

## Desktop app (early)

`app/` is a Tauri 2 app (Rust + Svelte 5 + TypeScript) for a **workspace**: a folder with your podcasts, where your AI session runs with the podcastz plugin. It shows the projects and their stage, lets you approve or reject sources, leave requests for the AI session, start or show that session, check scripts, see the price and generate, sample and publish audio, and store your TTS keys (Settings).

```sh
podcastz workspace init <folder>      # once: marker, runtime folder, plugin enabled for sessions started there
cd app && npm install && npm run tauri dev
```

**Why a Python sidecar.** The app's foundations (settings, API keys in the OS credential store, dialogs, launching the AI session, later the updater) are Rust. The podcast pipeline stays in Python and runs as a sidecar, the `podcastz` CLI itself, started per task with JSON-lines output: it already exists and is tested, it talks to the TTS providers and drives ffmpeg for loudness normalisation and mixing, and the same code serves the console, the AI session's skills and the app. Rewriting it in Rust would duplicate that for no gain.

## How it works

1. **New podcast**: a project folder with `AGENTS.md` (instructions for any AI assistant), `BRIEF.md`, `podcast.json` and `state.json`.
2. **Preparation in your AI session**: interview, research into `sources/`, scripts into `text/`, review, then `podcastz check`. Progress goes to `state.json`.
3. **Audio**: `podcastz estimate`, `sample`, `build` (asks before spending), `publish`. Segments are cached by content, so editing one line regenerates only that line.

## CLI (core)

```sh
cd core
uv run podcastz languages                         # languages and cost per audio hour
uv run podcastz quote --language en --hours 1     # price for a planned length
uv run podcastz new how-dns-works                 # project under ~/Podcasts (or $PODCASTZ_HOME)
uv run podcastz check how-dns-works               # validate scripts
uv run podcastz build how-dns-works               # generate audio
```

Script format: a title line `# Episode 01 – Title`, an optional meta line, then only `SPEAKER: text` lines (speakers from `podcast.json`, default `MODERATOR` and `GUEST`), optionally split by `## Chapter title` lines. Next to every MP3 the build writes `NN-slug.json` with the start and end time of each replica and chapter.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- `ffmpeg` and `ffprobe` on PATH
- A TTS key: `OPENAI_API_KEY` (default model `gpt-4o-mini-tts`, about $0.90 per audio hour) or `ELEVENLABS_API_KEY` (higher quality, about $4.60 to $5 per audio hour). Prices are estimates; check the providers' pages.

No AI model is called by podcastz itself; preparation runs in your own AI session.
