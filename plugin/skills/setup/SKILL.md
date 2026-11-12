---
name: setup
description: Set up podcastz for the user - check that the podcastz CLI, ffmpeg and a text-to-speech key are available, create a workspace for their podcasts, and explain how preparation in this session and audio production fit together. Use when the user installs podcastz, asks how to start, runs /podcastz:setup, or when /podcastz:prepare finds something missing.
---

# Set up podcastz

Go through the checks in order, fix what you can with the user's agreement, and explain what the user has to do themselves. Talk in the user's language.

## 1. CLI

Run `podcastz --version`.
- Missing: the user needs Python 3.11+ and uv, then `uv tool install "git+https://github.com/drzdez/podcastz#subdirectory=core"` (from a clone: `uv tool install --editable <clone>/core`). Offer to run it.

## 2. ffmpeg

Run `ffmpeg -version` and `ffprobe -version`.
- Missing: Windows `winget install Gyan.FFmpeg`, macOS `brew install ffmpeg`, Debian/Ubuntu `sudo apt install ffmpeg`. A new terminal (and a new AI session) is needed afterwards for the PATH change.

## 3. Workspace

Run `podcastz workspace status`.
- Not in a workspace: agree on a folder for all podcasts (for example `~/Podcasts`, or the current folder if it is meant for that) and run `podcastz workspace init <dir>`. Explain: one subfolder per podcast; `.podcastz/` holds runtime files and is ignored by git; `.claude/settings.json` enables this plugin for sessions started there, so the user should start Claude Code in that folder from now on.
- If the workspace is a git repository, suggest committing `podcastz.workspace.json` and `.claude/settings.json`, and ignoring `*/audio/` and `*/cache/` unless the user wants audio in git.

## 4. Text-to-speech key

Run `podcastz key status`.
- No key: the user chooses a provider (OpenAI `gpt-4o-mini-tts`, cheap; ElevenLabs `eleven_multilingual_v2`, higher quality) and stores the key **themselves**, either in the app's Settings or in their own terminal with `podcastz key set <provider>` (it prompts without echo). Never ask for the key, never let it be pasted into the conversation, never put it into a command line or a file.
- Then `podcastz key test <provider>` (no cost).
- A key is only needed for audio; preparing scripts works without one.

## 5. The app (optional)

The desktop app opens the same workspace: it shows the podcasts and their stage, lets the user approve sources, leave requests for this session, and generate and publish audio. Installers come from the GitHub Releases page of drzdez/podcastz; from source: `cd app; npm install; npm run tauri dev`.

## 6. Explain the flow, then start

In a few sentences: this session prepares the content (interview, sources, scripts, review) into files in the podcast's folder; the user approves sources (app or here); `podcastz check` is the gate to `ready`; audio is made only after the user approves the price, in the app or with `/podcastz:audio`. Details: docs/how-it-works.md in the repository.

Then offer `/podcastz:prepare` for the first podcast.
