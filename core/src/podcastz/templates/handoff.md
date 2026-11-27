# Making podcasts with podcastz (instructions for an AI session)

podcastz turns two-voice dialogue scripts into audio. It is a service: it keeps nothing about your podcast. **You own the podcast**: its folder lives in your repository, you write and keep the brief, the sources and the scripts, and you commit them. podcastz only checks the scripts, tells the price, generates the audio and writes metadata about how the audio was made.

## Requirements

- The `podcastz` command (`podcastz --version`). If it is missing, ask the user to install it: `uv tool install "git+https://github.com/drzdez/podcastz#subdirectory=core"` and ffmpeg.
- The podcastz desktop app for listening and for generating audio with a price confirmation (optional, but the usual way).
- Never ask for API keys and never put them in files or commands: the user stores them once in the app's Settings.

## 1. Create the podcast folder

Inside your repository, for example under `podcast/`:

```
podcastz new podcast/<slug> --title "<title>" --language <code> --speakers MODERATOR,GUEST
```

`<slug>` is lowercase kebab-case. This creates `podcast.json` (title, language, speakers, voices, TTS model), `BRIEF.md`, `AGENTS.md` (the method), `sources/`, `text/`, `work/`, `audio/` and a `.gitignore` that keeps generated audio and caches out of git. `podcastz languages` lists the languages and the price per audio hour; `podcastz quote --language <code> --hours <h>` prices a planned length.

## 2. Write the scripts

One file per episode: `text/NN-slug.md` (`01-introduction.md`, `02-…`).

```
# Episode 01 – How DNS works

## Names and addresses
MODERATOR: Welcome. Today we look at how a name becomes an address.
GUEST: Every device on the internet is reached by a number, the IP address.

## The lookup
MODERATOR: So what happens when I type a name into the browser?
```

- The first line is `# Episode NN – Title`; `## Chapter` lines are chapter marks (not spoken; the app and the timing manifest show them).
- Every other non-empty line is `SPEAKER: text`, one line per replica, speakers as in `podcast.json`.
- Write for the ear: no URLs, no markup, abbreviations and numbers written the way they should be spoken, short sentences. About 700–800 characters make one audio minute.
- HTML comments (`<!-- … -->`) are ignored; use them for your own notes.
- Facts come from your sources; keep them in `sources/` or wherever your project keeps them.

Then run `podcastz check podcast/<slug>` and fix every error.

## 3. Make the audio

- You may show an estimate: `podcastz estimate podcast/<slug>`.
- **Paid audio is always made in the podcastz app, never by you:** open the podcast with `podcastz open podcast/<slug>` and tell the user it is ready. The user decides the price, voices, model and other settings there, generates the audio (*Generate audio*), listens in *Script and player*, and can publish. Do not run `podcastz build` or `podcastz sample` for a paid text-to-speech model.
- Only a free text-to-speech model, if one is configured, may be run without the app, with its defaults, for quick prototypes; say clearly that such audio is a free draft, not production quality.
- Only changed lines are generated again; the paid speech segments are cached in `cache/` (not in git; keep the folder).

## 4. What you get

- `audio/NN-slug.mp3` – the episode (not in git).
- `audio/NN-slug.json` – commit it: the start and end time of every replica and chapter (for chapter jumps in your app), and `production`: when and with which podcastz version, TTS provider, model, voices, characters, the price at the time, and fingerprints of the script and of the speech segments, so you can tell whether the audio still matches the script.

## 5. Changing a podcast

Edit the script, `podcastz check`, then generate again (in the app or with `build`); commit the scripts and the new `audio/*.json`.
