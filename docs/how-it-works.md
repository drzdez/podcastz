# How the data flows

The AI session and the podcastz machinery never talk to each other directly. They share **files in the workspace**: the session prepares the content, the CLI and the app turn it into audio. Everything a podcast is made of stays in its own project folder, so you can see what it was made from and delete it completely.

```
<workspace>/
  podcastz.workspace.json        marks the workspace
  .claude/settings.json          enables the podcastz plugin for sessions started here
  .podcastz/                     runtime only (not committed)
    session.json                 is the AI session running, busy or idle (plugin hooks)
    app.json                     the app is open
    events.jsonl                 change notices for the app
    requests/<id>.json           your requests from the app to the session
  how-dns-works/                 one podcast
    podcast.json                 title, language, speakers, voices, TTS model
    BRIEF.md                     what you want, written after the interview
    state.json                   stage: interview → research → script → review → ready
    AGENTS.md                    the method, for any AI tool
    sources/                     material, one file per source
    sources/index.json           the source list: proposed / approved / rejected
    work/                        plan, drafts, reviews
    text/NN-slug.md              final scripts
    audio/NN-slug.mp3            episodes
    audio/NN-slug.json           start times of replicas and chapters
    cache/                       generated speech segments (paid for: keep them)
```

## Who writes what

| File | AI session | You (app or session) | CLI / app |
|---|---|---|---|
| `BRIEF.md`, `podcast.json` title and language | writes after the interview | answers, corrects | reads |
| `sources/*`, `sources/index.json` | proposes sources | approves, rejects, adds | lists |
| `work/*`, `text/*` | writes and reviews | reads, asks for changes | checks |
| `state.json` | updates the stage | – | shows it |
| `.podcastz/requests/` | handles, marks done | leaves requests | stores |
| `audio/*`, `cache/*` | – | approves the price | generates |

## The steps

1. **Interview** (`interview`): the session asks what you want to understand, for whom, how long, how detailed, in which language, from which sources. Result: `BRIEF.md`. The app shows a price per hour as soon as language and length are known.
2. **Research** (`research`): sources go to `sources/` with their origin, and each is registered in `sources/index.json` as *proposed*. You approve or reject them in the app (or tell the session). Only approved sources count.
3. **Script** (`script`): the episodes are written in `text/` from approved sources only, one line per replica (`MODERATOR: …`, `GUEST: …`), with optional `## Chapter` lines.
4. **Review** (`review`): a separate reviewer checks every claim against the sources, the clarity and the text-to-speech form; the writer fixes the findings.
5. **Ready** (`ready`): `podcastz check` must pass. The session sets the stage and tells you.
6. **Audio** (after `ready`): the app or the CLI estimates the cost (`podcastz estimate`), you confirm, `podcastz build` generates only what is not cached yet, normalises and mixes each episode, and writes `audio/NN-slug.json` with timings. `podcastz publish` copies the MP3 files to a folder you sync to your phone.

## Talking to the session from the app

- *Start* or *Continue* opens your AI session in the workspace in a terminal window; *Show* brings it to the front.
- *Leave request* (for example "find a primary source on DNSSEC") writes `.podcastz/requests/<id>.json`. With your next message in the session, the plugin puts the request into the session's context; the session handles it and marks it done. Nothing is typed into your terminal for you.
- Approving or rejecting a source in the app changes `sources/index.json`; the session sees it the next time it reads the list.

## Changing a finished podcast

Edit a line in `text/` (or ask the session), run `podcastz check`, then *Generate audio* again: only the changed lines are generated (the cache is keyed by text, voice, model and settings), then *Publish*.

## Where things are not stored

- No podcast data is ever copied outside its project folder by podcastz.
- API keys live only in your operating system's credential store (or environment variables), never in project files, logs or messages.
- The app never talks to an AI model; preparation always runs in your own AI session.
