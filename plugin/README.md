# podcastz plugin for Claude Code

Skills that prepare a two-voice learning podcast in a podcastz project folder and voice it with the `podcastz` CLI.

| Skill | Use |
|---|---|
| `/podcastz:prepare` | end to end: interview, research, script, review, check |
| `/podcastz:research` | sources with provenance and an episode plan |
| `/podcastz:script` | scripts in the podcastz format, written for the ear |
| `/podcastz:review` | review against sources, clarity and TTS readiness |
| `/podcastz:audio` | estimate, sample, build (only after you approve the price), publish |

## Install

```
/plugin marketplace add drzdez/podcastz        # or a local clone: /plugin marketplace add <path-to-podcastz>
/plugin install podcastz@podcastz
```

The skills call the `podcastz` CLI: `uv tool install --editable <path-to-podcastz>/core`. Audio needs `ffmpeg`/`ffprobe` and an `OPENAI_API_KEY` or `ELEVENLABS_API_KEY` in the environment.
