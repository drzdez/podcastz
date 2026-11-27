# Spec: own podcasts and podcasts of other projects

Status: accepted direction (maintainer, 2026-11-27); replaces an earlier draft with order import, script locks and deliveries. Written after an analysis and an opponent review, then simplified by the maintainer's model below.

## The model

podcastz is a craftsman: it has **its own podcasts**, and it **visits other projects** and makes their podcasts there.

- **Own podcasts** live in the podcast projects folder (the workspace): one subfolder per podcast with brief, sources, scripts, work, audio and metadata. They are prepared in the workspace's AI session with the podcastz plugin and changed only there. If the workspace is a git repository, everything except generated audio and caches can be committed.
- **Podcasts of another project** (an app that wants learning audio, for example) live in **that project's repository**. Its AI session creates the podcast folder, writes and keeps the brief, sources and scripts, and commits them. podcastz keeps **nothing** about such a podcast: it works on the folder in place when asked, checks the scripts, tells the price, generates the audio and writes metadata about how the audio was made, all inside that folder.
- So nobody needs to copy scripts, lock them or sync them: there is one copy, in its owner's repository. A change to the script is made by its owner; podcastz regenerates only the changed lines.

## Pieces

| Piece | What it does |
|---|---|
| `podcastz new <path> --title … --language … --speakers …` | Creates a podcast folder anywhere (structure, `podcast.json`, `BRIEF.md`, `AGENTS.md`, and a `.gitignore` that excludes generated audio and caches). No AI needed. |
| App: **Add podcast** | The same for own podcasts, in the podcast projects folder. |
| `podcastz open [path]` | Opens a podcast folder in the desktop app (starts it, or switches the running app to that podcast). |
| App: **Podcast folders elsewhere** | Lists podcast folders outside the workspace that were opened; the app works on them but does not manage their storage, git or backups. |
| `podcastz handoff` / Help → *Podcasts in another project* | The instruction text for another project's AI session: requirements, creating the folder, the script format, checking, pricing, generating (app or CLI), what comes back. Paste it into the session or save it in its repository. |
| `audio/NN-slug.json` | Timing of every replica and chapter, plus `production`: when, podcastz version, TTS provider, model, voices, characters, price at the time, fingerprints of the script and of the speech segments. Committed by the owner; the MP3 is not. |
| `podcastz info <path>` | Summary of any podcast folder (used by the app). |

## Rules

- Generated audio (`audio/**/*.mp3|wav|m4a|ogg`), `cache/` and `delivery/` are always in `.gitignore` (written by `podcastz new` into the project and by `podcastz workspace init` into the workspace).
- **Paid audio is always made in the app** (maintainer, 2026-11-28): any session may create a podcast and open it in the app (`podcastz open`), which is a proposal; the person decides the price, voices, model and other settings in the app and starts the generation there. AI sessions never run paid `build`/`sample` themselves.
- **Exception: free text-to-speech.** If a free model is configured, a session may generate audio without the app, silently with its defaults, for quick prototyping; such audio is marked as a free draft without production quality (also in the manifest's `production` block).
- API keys stay in the operating system's credential store of the person's account (entered in the app's Settings); no session ever sees them.
- podcastz never copies a podcast's content out of its folder; company-sourced material never goes into any repository.
- The podcast's owner decides what is committed; podcastz only guarantees that audio and caches are ignored.

## Not needed any more

The earlier draft's `owner` block, `import`, script hashes per import, the build guard against changed scripts, `deliver` and change-request flows are dropped: with the podcast in its owner's repository there is nothing to sync. The manifest's script fingerprint still tells whether audio matches the current script.

## Open points

- Decided 2026-11-28: any session on the person's account may open the app on its podcast; paid generation happens only in the app after the person's decisions. Still to do: a free draft model (none is configured today), and making the CLI refuse paid `build`/`sample` outside the app (a behaviour change announced in advance to the production session).
- Pronunciation map (word → spoken form applied before text-to-speech) so that one pronunciation fix regenerates only the affected lines; optional, later.
- Linux playback (see `docs/audio-playback.md`).
