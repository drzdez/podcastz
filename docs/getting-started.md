# Getting started

podcastz has three parts. You need the first two; the app is optional.

| Part | What it does | Install |
|---|---|---|
| `podcastz` CLI | project folders, checks, prices, text-to-speech, mixing, publishing | Python package (step 1) |
| Claude Code plugin | skills that interview you, research, write and review the podcast in your own AI session | Claude Code plugin (step 3) |
| Desktop app | shows your podcasts, lets you approve sources, leave requests for the session, and make the audio | installer (coming); today from source (step 6) |

## 1. The CLI

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install "git+https://github.com/drzdez/podcastz#subdirectory=core"
podcastz --version
```

From a clone of the repository: `uv tool install --editable ./core`.

## 2. ffmpeg

Audio is normalised and mixed with ffmpeg; `ffmpeg` and `ffprobe` must be on PATH.

- Windows: `winget install Gyan.FFmpeg`
- macOS: `brew install ffmpeg`
- Debian/Ubuntu: `sudo apt install ffmpeg`

## 3. The Claude Code plugin

In Claude Code:

```
/plugin marketplace add drzdez/podcastz
/plugin install podcastz@podcastz
```

Other AI tools can follow the `AGENTS.md` that every project contains; they get the same steps, without the slash commands.

## 4. A workspace for your podcasts

A workspace is one folder that holds all your podcasts (one subfolder each). Your AI session runs there, and the app opens it.

```sh
podcastz workspace init ~/Podcasts
```

This adds `podcastz.workspace.json`, a `.podcastz/` folder for runtime files (ignored by git), and `.claude/settings.json`, which enables the plugin for every Claude Code session started in the folder. The workspace can be a git repository: commit sources, scripts and `podcast.json`; audio and cache are large and can be regenerated or backed up separately.

## 5. Text-to-speech keys

You need a key from at least one provider:

- OpenAI (`gpt-4o-mini-tts`, cheap, accepts pronunciation instructions)
- ElevenLabs (`eleven_multilingual_v2`, higher quality)

Store it in your operating system's credential store:

```sh
podcastz key set openai        # prompts for the key; nothing is printed
podcastz key test openai       # checks it without spending money
podcastz key status            # shows where each key comes from, never the key
```

The app's Settings page writes the same entry and checks the key when you save it. Lookup order: `PODCASTZ_OPENAI_API_KEY` (an explicit override), then the stored key, then `OPENAI_API_KEY` (the same for `ELEVENLABS`), so an old generic variable never hides a key you saved. Never paste a key into a conversation with an AI assistant.

## 6. The app (optional, from source for now)

Requirements: Node.js, Rust, and on Linux the Tauri system packages.

```sh
cd app
npm install
npm run tauri dev
```

Choose your workspace folder on the first page. Installers with automatic updates will be published on the GitHub Releases page.

## 7. Your first podcast

In the workspace, start Claude Code (`claude`, or *Start* in the app) and run:

```
/podcastz:prepare
```

The session interviews you, collects and registers sources, writes and reviews the scripts, and tells you when they are ready. Then make the audio in the app (*Generate audio*) or in the session (`/podcastz:audio`). Either way you see the price first and confirm it.

[How the data flows](how-it-works.md) explains what happens in the folder at each step.

## 8. Podcasts that belong to another project

A podcast can also live in another project's repository (for example an app that wants learning audio). That project's AI session creates the folder (`podcastz new podcast/<slug>`), writes and keeps the scripts, and opens the podcast in the app with `podcastz open podcast/<slug>` to make the audio. podcastz keeps nothing about such a podcast. Give the session the instructions from `podcastz handoff` (or Help → *Podcasts in another project* in the app). See [the spec](spec-projects-and-orders.md).
