---
name: script
description: Write two-voice dialogue podcast scripts in the podcastz format (NN-slug.md, one "SPEAKER: text" line per replica) from a project's plan and sources, ready for text-to-speech. Use when writing or rewriting podcast episodes, or as step 3 of /podcastz:prepare.
---

# Write the scripts

Input: `BRIEF.md`, `work/plan.md`, `sources/`, speakers from `podcast.json`. Drafts go to `work/` (for example `work/round-1-drafting/draft-01.md`), finals to `text/NN-slug.md`.

## Format (parsed by the TTS pipeline, enforced by `podcastz check`)

```
# Episode 01 – Title
Part 1 of 3 | Estimated length: ~10 min

## Optional chapter title
MODERATOR: One replica per line.
GUEST: Another replica.
```

- After the two header lines only `SPEAKER: text` lines, optionally split by `## Chapter title` lines (not spoken; their start times go to `audio/NN-slug.json`).
- No lists, tables, notes, markdown emphasis, URLs or brackets. HTML comments `<!-- ... -->` are ignored by the pipeline; use them only if the project asks for them.
- Speaker labels exactly as in `podcast.json` `speakers`.

## Writing for the ear

- Cast: one moderator who asks on behalf of the listener and summarises; a guest per episode introduced by role, never by an invented name. Use the right grammatical gender for each speaker in languages that need it.
- A conversation, not a lecture: replicas mostly one to five sentences, explanations may be longer; no monologue over about 150 words.
- Concrete examples before abstractions. Explain every term the listener may not know the first time it appears.
- Each episode opens with what it covers and how it connects to the previous one, and ends with a short summary.
- Text-to-speech reads what is written: expand abbreviations on first use; write numbers, versions, codes and standard numbers the way they are spoken; avoid symbols (arrows, slashes, section signs). If an abbreviation is read as a word or letter by letter, add it to `tts.instructions` in `podcast.json` (OpenAI) instead of misspelling it.
- Length: plan about 700 to 800 characters of replicas per minute; check with `podcastz estimate <project>` once files exist.

## Facts

Every factual claim comes from the **approved** sources (`podcastz source list <project> --status approved`). Keep a map `work/sources-map.md`: claim → source file and section. Hedge uncertain claims, drop unsupported ones, and list anything taken from outside the sources separately.

Update the state: `podcastz state . script -m "drafts of <n> episodes"`.
