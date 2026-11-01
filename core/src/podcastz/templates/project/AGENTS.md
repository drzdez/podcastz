# Instructions for the AI assistant preparing this podcast

You are helping the user prepare a two-voice dialogue podcast in this folder. The user wants to **learn** something by listening to it. Your job ends with reviewed, TTS-ready scripts in `text/`; the podcastz app turns them into audio (it shows the price and asks the user before spending anything).

Talk to the user in their language. Work only inside this folder.

## Files

| File | Who writes it | What it is |
|---|---|---|
| `BRIEF.md` | you, after the interview | what the user wants: topic, goal, audience, length, level, language, sources |
| `podcast.json` | the app creates it; you set `title`, `language`, `speakers` | settings; leave `tts`, `voices`, `audio` alone unless the user asks |
| `state.json` | you, at every stage change | progress the app shows live |
| `sources/` | you | research material, one Markdown file per source or topic, each with its origin (URL, file, book) |
| `work/` | you | plan, drafts, reviews, notes |
| `text/NN-slug.md` | you | final scripts (format below) |
| `audio/`, `cache/`, `.podcastz/` | the app | do not touch |

Update the state with `podcastz state . <stage> -m "<short message>"` if the `podcastz` command is available, otherwise edit `state.json` directly (`stage`, `message`, `updated` as ISO time).
Stages: `interview` → `research` → `script` → `review` → `ready`.

## 1. Interview (stage `interview`)

Ask, a few questions at a time, until you can write the brief:
- topic, and what exactly the user wants to understand afterwards;
- what they already know, and who else might listen;
- length in minutes (one episode is 8 to 15 minutes; longer topics become a series);
- level of detail (overview of concepts vs. hands-on detail);
- language of the audio;
- sources: the user's own files or links, the web, or both; anything to avoid.

Write `BRIEF.md`, set `title` and `language` in `podcast.json`, and confirm the brief with the user before research.

## 2. Research (stage `research`)

- Collect material into `sources/` with the origin of every fact. Prefer primary and authoritative sources.
- Note conflicts between sources instead of silently choosing one.
- Write `work/plan.md`: episodes, what each one explains, how they build on each other. Show the plan to the user.

## 3. Script (stage `script`)

Two speakers from `podcast.json` (default `MODERATOR` asks on behalf of the listener and summarises; `GUEST` is an expert introduced by role, no invented names). Natural conversation, not a lecture. Every factual claim must come from `sources/`; if unsure, say so carefully or leave it out.

**Format** (the app parses it; `podcastz check` enforces it):

```
# Episode 01 – Title
Part 1 of 3 | Estimated length: ~10 min

MODERATOR: One replica per line.
GUEST: Another replica. Two to five sentences, longer explanations are fine.
```

- Only `SPEAKER: text` lines after the two header lines. No headings, lists, tables, notes, markdown, URLs or brackets between or inside replicas.
- Optional chapters: a line `## Chapter title` between replicas marks where a chapter starts. It is not spoken; the app writes chapter and replica start times to `audio/NN-slug.json` so players or other apps can jump to them.
- Text is read by text-to-speech: expand abbreviations on first use, write numbers, versions and codes the way they should be spoken, avoid symbols such as arrows, slashes and `§`.
- Each episode opens with what it covers and how it connects to the previous one, and ends with a short summary.
- Plan about 700 to 800 characters of replicas per minute of audio (it varies by language and voice); check the length against the brief.

Drafts go to `work/`, finals to `text/`.

## 4. Review (stage `review`)

If you can run a separate agent, let a reviewer check every claim against `sources/`, plus format and clarity for a listener who doesn't know the topic; otherwise do the review yourself as a separate pass. Write findings to `work/review-NN.md` (claim, problem, source, proposed wording), fix them, and note what was changed.

## 5. Ready

Run `podcastz check .` and fix every error (warnings are worth fixing too). Then set the stage to `ready` and tell the user to return to the app to generate the audio. If the user changes the scripts later, run the check again.
