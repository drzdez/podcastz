# Changelog

Release notes of podcastz, newest first. The desktop app shows the entry of a new version once after an install or update, and all of them in Help; the same text is the body of the GitHub Release. Every version heading is `## <version> – <YYYY-MM-DD>`.

## 0.1.3 – 2026-11-27

- Add podcast: create a new podcast in your podcast projects folder from the app (name, language, speakers), without the AI session.
- The Workspace page shows where your podcast projects live, with buttons to open that folder and each podcast's folder.
- Podcast folders elsewhere: open a podcast that belongs to another project (for example an app's repository); podcastz works on it in place and keeps nothing about it. `podcastz open <folder>` opens a podcast in the app from a terminal or another AI session.
- Help, *Podcasts in another project*: instructions for another project's AI session (create the folder, script format, price, audio) with a Copy button; the same text with `podcastz handoff`.
- Each episode's `audio/NN-slug.json` now records how the audio was made: date, podcastz version, TTS provider, model, voices, characters, price, and fingerprints of the script and the speech segments.
- New podcasts and workspaces get a `.gitignore` that keeps generated audio and caches out of git.
- CLI: `podcastz new --speakers`, `podcastz info`, `podcastz open`, `podcastz handoff`.

## 0.1.2 – 2026-11-27

First release with installers (0.1.1 was published without them by a release workflow error).

- Script and player: read each episode by chapter and listen to it; jump to a chapter or click a replica to play from there, the spoken replica is highlighted, speed 0.8× to 2×, space to play or pause, the position is remembered. New CLI command `podcastz episodes`.
- Desktop app: open a workspace with your podcasts, see each podcast's stage, approve or reject sources, leave requests for your AI session, start or show that session, check scripts, see the price and generate, sample and publish audio.
- Settings: text-to-speech keys stored in the operating system's credential store (shared with the CLI, never shown), automatic update checks that you can switch off.
- Help: setup check (CLI, ffmpeg, keys, workspace, AI session), how preparation and audio fit together, release notes, check for updates.
- CLI: workspaces, source curation (`podcastz source`), keys (`podcastz key`), requests from the app, JSON output for the app.
- Claude Code plugin 0.3.0: `setup` skill, hooks that tell the app whether the AI session is running and pass on your requests.
- Installers for Windows (`.msi` and `-setup.exe`, for all users), macOS and Linux, with the `podcastz` CLI bundled for the app.

## 0.1.1 – 2026-11-27

- Published without installers by a release workflow error; use 0.1.2.

## 0.1.0 – 2026-11-12

- Not published.
