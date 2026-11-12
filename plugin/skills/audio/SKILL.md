---
name: audio
description: Turn finished podcastz scripts into audio with the podcastz CLI - check, estimate the cost, generate a voice sample, build all episodes after the user approves the price, and publish the MP3s. Use when the user wants to voice, generate, rebuild or publish podcast audio, or after /podcastz:prepare reports ready.
---

# Audio

Audio costs money. **Never run `podcastz build` or `podcastz sample` without the user's explicit OK to the price shown.**

## Steps

1. `podcastz check <project>`: errors must be fixed first (state should be `ready`). Make sure nobody is still editing the scripts.
2. Voices and model in `podcast.json` (`tts.model`, `voices`, per-episode `episodes.NN.<SPEAKER>`):
   - OpenAI `gpt-4o-mini-tts`: cheap (about $0.90 per audio hour), voices are language-independent (`podcastz voices --provider openai`), accepts `tts.instructions` and `tts.speaker_instructions` for style and pronunciation (which abbreviations are read as words and which letter by letter).
   - ElevenLabs `eleven_multilingual_v2`: higher quality, strongest for Czech (about $4.60 per audio hour); `podcastz voices --provider elevenlabs --language <code>`; library voices must be added to the account first.
   - Keys: `podcastz key status` shows where each key comes from (never the value). They live in the OS credential store, entered in the app's Settings or by the user running `podcastz key set <provider>` in their own terminal (it prompts; never ask the user to paste a key into the conversation). Order: `PODCASTZ_<PROVIDER>_API_KEY` (explicit override), then the stored key, then the provider's own variable (`OPENAI_API_KEY`, ...). `podcastz key test <provider>` verifies a key without spending money.
3. `podcastz estimate <project>`: characters, estimated minutes, full cost and the cost of what is not cached yet. Show it to the user.
4. Optional, recommended for a new voice or language: `podcastz sample <project> -e 01 --yes` after OK (about 1 500 characters, a few cents). Let the user listen; it also prints the measured characters per hour.
5. `podcastz build <project> --yes` after OK. Lines already generated come from the cache (`cache/tts`, keyed by text, voice, model and settings), so only new or changed lines cost money. Long runs: run it in the background and report when done.
6. Next to each `audio/NN-slug.mp3` the build writes `audio/NN-slug.json` with replica and chapter start times.
7. `podcastz publish <project>` copies the MP3s and `text/README.md` to `publish_dir` from `podcast.json` (for example a folder synced to the phone).

## Changes later

Edit the line in `text/`, run `podcastz check`, then `podcastz build <project> -e NN` (only the changed lines are regenerated) and `podcastz publish`. `podcastz prune <project>` lists cache files no longer used; deleting them throws away paid audio, so ask first.

## Troubleshooting

HTTP 401: key rotated or missing permissions; 402: plan doesn't allow the voice (ElevenLabs free tier); 429: rate limit or exhausted credit. `ffmpeg` and `ffprobe` must be on PATH.
