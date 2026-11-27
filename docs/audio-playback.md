# Audio playback in the desktop app (and a proposed devstack standard)

Status: proposal for the devstack standard (2026-11-27), from an analysis and an opponent review. podcastz is the reference implementation (`app/src/lib/Episodes.svelte`, `allow_audio` in `app/src-tauri/src/lib.rs`).

## Context

Apps are Tauri 2 (Rust core, Svelte 5 webview), Windows first, then macOS and Linux, installers built on GitHub. Two implementations exist:

- **podcastz** plays whole episodes (10–60 min, 10–60 MB MP3) with HTML5 `<audio>` over the Tauri asset protocol. The static scope is empty; a Rust command checks each file (canonical path, allowed extension, inside the open workspace) and grants only that file at runtime (`asset_protocol_scope().allow_file`). The script is synchronised through the timing manifest the audio build writes next to each MP3 (start and end of every replica, chapter starts): the current replica is highlighted on `timeupdate`, a click on a chapter or replica seeks. Verified on Windows (WebView2), including seeking.
- **recordingz** plays only clips of up to 8 s (WAV cut from a 16 kHz mix) from its Python review backend over localhost HTTP, without Range and without text sync.

## Facts (checked 2026-11-27)

- The asset protocol answers HTTP Range requests (206, at most about 1 MB per range); a request without Range reads the whole file into memory, so never `fetch()` a large asset URL.
- The asset scope is app-wide and only grows while the app runs; `forbid_file` overrides an allow but cannot be undone.
- **Linux:** `<audio>`/`<video>` from `asset://` fail on WebKitGTK (tauri issue #3725, open, last failure report 2026-09-22), because GStreamer fetches media itself and does not know the custom scheme. The fix moved from PR #14402 (closed unmerged 2026-10-06) to `tauri-apps/tauri-gstreamer-plugin`; the bundler change (#15965) was merged 2026-09-02. Newer WebKitGTK may also need `WEBKIT_GST_ALLOWED_URI_PROTOCOLS=asset`. Custom URI schemes other than `asset` are not covered by that plugin. A blob URL only changed the error to a decode error in one report (video).
- **macOS:** Apple's decoder seeks VBR MP3 inaccurately (Xing TOC has only 100 points). podcastz currently encodes `libmp3lame -q:a 4`, which is VBR.
- Ogg Opus is still unreliable in WKWebView.
- CVE-2026-42184 (fixed in Tauri 2.11.1) bypassed the origin check of custom schemes on Windows.

## Options

| | Transport | Verdict |
|---|---|---|
| A | `<audio>` + asset protocol, per-file runtime grant | **Default** |
| B | `<audio>` + localhost HTTP server | Only for short generated clips from a backend that already exists |
| C | `<audio>` + own Rust URI scheme | Only when bytes are not a plain file (decrypt, transcode); stays broken on Linux even after the plugin fix |
| D | Native Rust playback (rodio/cpal, or community plugins such as tauri-plugin-native-audio) | Only for playback without a window, a chosen output device or unusual codecs; no pitch-preserving speed, no media keys without extra work |
| E | Web Audio API with decoded buffers | Only for clips under ~30 s that need sample-accurate or gapless playback |
| F | Open the file in the system player (opener plugin) | Fallback where A does not work |

## Proposed decision

1. **Default A:** `assetProtocol.enable: true`, static scope `[]`, one Rust command that grants single files after checking the canonical path, the allowed extensions (a parameter, e.g. mp3, m4a, wav) and the app's current root. Preconditions: a CSP with `media-src 'self' asset: http://asset.localhost` (no `csp: null`), Tauri ≥ 2.11.1, and on switching the root (workspace) either `forbid_file` for earlier grants or the documented behaviour that they stay readable until exit.
2. **Formats:** for audio with text sync **CBR MP3 or AAC/M4A** (accurate seeking on every platform); VBR only without sync; WAV for short clips; no Ogg Opus until WKWebView is proven.
3. **Linux:** playback counts as unsupported until a Linux bundle built with the Tauri GStreamer plugin (#15965) is tested; until then the app offers "Open in system player" (F). A loopback server is built only if that test fails, and then bound to 127.0.0.1 with a random port, a per-run token, Host-header validation (DNS rebinding), Range, no directory listing, and the same file check.
4. **B** is allowed for generated clips of about 30 s or less from a backend that already exists for a strong reason (recordingz); bound to 127.0.0.1 with a token and a Host check. Full recordings with seeking use A.
5. **C, D, E** only in the cases listed in the table.
6. **Text sync:** the podcastz timing manifest is the reference format (`audio/NN-slug.json`: duration, `lines[]` with index, speaker, start, end, text; `chapters[]` with title, start, first_line); the player marks it stale when the script is newer than the audio. A shared schema and a template player component are extracted when a second app needs them, not before.
7. **Media keys / Now Playing:** not part of the standard until tested on WebView2 and WKWebView.

## Consequences for podcastz (follow-ups)

- Encode episodes as CBR (or M4A) so chapter and replica jumps stay accurate on macOS; this changes only mixing (`cache/norm` and the MP3), not the paid TTS segment cache.
- Add a CSP; revoke or document grants on workspace switch; make the extension list a parameter of `allow_audio`.
- Linux: "Open in system player" until the GStreamer plugin build is tested.
- Resume positions live in localStorage keyed by file path; move them to the app settings store if the origin ever changes.
