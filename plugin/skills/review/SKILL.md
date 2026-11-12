---
name: review
description: Review podcastz podcast scripts against the project's sources - facts, completeness against the brief, clarity for a listener new to the topic, and text-to-speech readiness - and record findings with proposed wording. Use when checking or approving podcast scripts, or as step 4 of /podcastz:prepare.
---

# Review the scripts

Run the review as a **separate agent** that did not write the text, when subagents are available; otherwise do a separate, deliberate pass. The reviewer does not edit the scripts; it writes findings, the writer applies them.

## What to check

1. **Facts**: every factual claim against the approved sources (`podcastz source list <project> --status approved`; use `work/sources-map.md`, but verify yourself). A claim resting on a proposed or rejected source is a finding. Unsupported, distorted or over-generalised claims are findings, with the source and a corrected wording.
2. **Completeness**: does each episode deliver its goal from `work/plan.md` and the brief? Missing essentials get a short addition (no more than about 10 % length).
3. **Clarity**: would a listener without prior knowledge follow it? Terms explained, examples concrete, no dense monologues, episodes connect.
4. **Text-to-speech**: format (`podcastz check`), abbreviations expanded, numbers and codes written to be spoken, no symbols, speaker gender consistent.
5. **Level**: matches the brief (don't ask for detail the user excluded).

## Output

`work/review-NN.md` per episode (or `work/review-final.md` for a recheck):
- verdict: `APPROVED` or `CHANGES NEEDED`;
- numbered findings: severity (blocking / recommended / cosmetic), the replica (start of it), the problem, the source (file and section), and the **full proposed wording** of the replica.

The writer records in `work/done-review.md` what was applied or rejected and why. After substantial changes (new passages, split episodes) run a short recheck of the changed parts only.

Update the state: `podcastz state . review -m "<verdicts>"`.
