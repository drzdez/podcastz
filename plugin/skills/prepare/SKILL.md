---
name: prepare
description: Prepare a two-voice learning podcast end to end in a podcastz project folder - interview the user, research with sources, write and review the scripts, check them for text-to-speech. Use when the user wants to make, prepare or continue a podcast, runs /podcastz:prepare, or opens a session in a folder with podcast.json.
---

# Prepare a podcast

You guide the user from an idea to reviewed, TTS-ready scripts. The user wants to **learn** by listening. Talk in the user's language; files you write for the project follow the project's language (scripts in the audio language).

## 0. Find or create the project

- A project folder contains `podcast.json`. Look in the current directory first. If the user names another folder, work there by path.
- No project yet: agree on a folder (lowercase kebab-case name) and run `podcastz new <folder>` (add `--language <code>` if already known). This creates `podcast.json`, `state.json`, `BRIEF.md`, `AGENTS.md` and the folders.
- If `podcastz` is not on PATH, tell the user how to install it: `uv tool install --editable <path-to-podcastz>/core` (or `uv tool install podcastz` once published).
- Read `state.json` and continue from its stage instead of starting over. Read `AGENTS.md` if present; the project may add its own rules (for example HTML comments the project's own pipeline reads - leave them intact).

Record progress at every stage change: `podcastz state . <stage> -m "<short message>"` (stages `interview`, `research`, `script`, `review`, `ready`).

## 1. Interview

Ask a few questions at a time until you can write `BRIEF.md`: topic and what the user wants to understand afterwards, prior knowledge, audience, total length (one episode 8 to 15 minutes; more makes a series), level of detail (concepts and how they fit together vs. hands-on detail), audio language, sources (the user's files or links, the web, both) and what to avoid. Set `title` and `language` in `podcast.json`. Show a price with `podcastz quote --language <code> --hours <h>` and confirm the brief before research.

## 2. Research

Use the `research` skill: sources with provenance in `sources/`, conflicts noted, a plan in `work/plan.md`. Show the plan (episodes and what each explains) and get the user's OK.

## 3. Script

Use the `script` skill. Prefer a separate writer agent if you can run subagents; give it the brief, the plan and the sources folder.

## 4. Review

Use the `review` skill with a separate reviewer agent that did not write the text. Apply the findings, rerun the review for substantial changes. The user may change the brief at any time (length, level of detail); then adjust plan and scripts rather than starting over.

## 5. Ready

Run `podcastz check <project>` and fix all errors; fix warnings where reasonable. Make sure the writer is done editing before you declare the scripts final. Then `podcastz state . ready -m "<n> episodes, ~<minutes> min"` and tell the user the scripts are ready for audio (the `audio` skill, or the podcastz app).

## Rules

- Facts only from `sources/`. Hedge uncertain ones ("according to the materials"), drop unsupported ones.
- Never spend money on audio inside this skill.
- Never copy material from outside the project into other places (other repositories, messages, memory); work on the project folder by path.
