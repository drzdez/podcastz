---
name: research
description: Collect and organise research material for a podcastz podcast into sources/ with the origin of every fact, note conflicts, and write an episode plan. Use when preparing a podcast's sources, when the user adds material to a podcast, or as step 2 of /podcastz:prepare.
---

# Research for a podcast

Input: `BRIEF.md` (topic, goal, level, sources policy). Output: `sources/` and `work/plan.md`.

## Sources

- Start with what the user provided (files, folders, links). Read it fully before searching elsewhere. Use the web only where the brief allows it or where the provided material leaves a necessary gap; say so in the plan.
- Prefer primary and authoritative sources (standards, official documentation, original papers) over summaries.
- One Markdown file per source or per topic in `sources/`, kebab-case names. Each file starts with its origin: URL, document title and version or date, or the path of the user's file, and the date you accessed it.
- Keep the substance, not everything: definitions, how things relate, numbers with their context, examples that make a concept concrete.
- Copy text only as far as needed and attributed; summarise in your own words otherwise.
- Write down conflicts between sources explicitly (`sources/conflicts.md`), with both claims and their origins. Don't silently pick one.
- Material extracted from documents (for example .docx or PDF converted to text) goes into `sources/` as text, with the original file named as the origin.

## The source list (`sources/index.json`)

Register every source so the user can curate it (in the app or by telling you):

```
podcastz source add <project> --title "RFC 1034 – Domain names" --origin https://www.rfc-editor.org/rfc/rfc1034 --file rfc1034.md --kind standard --note "primary definition of resolvers"
podcastz source list <project> [--status approved]
podcastz source set <project> s003 --status approved|rejected [--note "..."]
```

- New sources start as `proposed`. Sources the user provided can be added with `--status approved --by user`.
- Ask the user to review proposals (or let them do it in the app) before writing scripts; say briefly why each source is worth using.
- Later steps use **approved** sources only; never rely on `rejected` ones. If the user rejects a source a plan depends on, find a replacement or adjust the plan.

## Plan

`work/plan.md`:
- the episodes, each with a one-line goal ("after this the listener understands …");
- what each episode explains, in order, and how it builds on the previous one;
- the guest role for each episode (for example "data specialist", "software architect");
- target length per episode from the brief, and the characters it implies (`podcastz quote` gives characters per hour for the language and model);
- open questions and gaps in the sources.

Update the state: `podcastz state . research -m "<n> sources, plan for <m> episodes"`.
