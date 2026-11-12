<script lang="ts">
  import { onMount } from 'svelte';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { diagnostics, DOCS, type Diagnostics, type KeyStatus, type WorkspaceStatus } from './api';
  import { RELEASES, itemHtml } from './releaseNotes';

  interface Props {
    status: WorkspaceStatus | null;
    workspace: string;
    keys: KeyStatus | null;
    checking: boolean;
    updateMsg: string;
    autoCheck: boolean;
    lastCheck: number | null;
    onCheckUpdates: () => void;
    onOpenSettings: () => void;
  }
  let { status, workspace, keys, checking, updateMsg, autoCheck, lastCheck, onCheckUpdates, onOpenSettings }: Props = $props();

  let diag = $state<Diagnostics | null>(null);
  let copied = $state(false);

  async function loadDiag() { diag = await diagnostics(); }
  onMount(loadDiag);

  type Check = { name: string; ok: boolean | null; detail: string; fix?: string };
  const checks = $derived<Check[]>([
    {
      name: 'podcastz CLI',
      ok: diag ? !!diag.cli_version : null,
      detail: diag ? (diag.cli_version ? `${diag.cli_version} (${diag.cli})` : diag.cli_error ?? `${diag.cli} does not run`) : 'checking…',
      fix: 'Install Python 3.11+ and uv, then: uv tool install "git+https://github.com/drzdez/podcastz#subdirectory=core"',
    },
    {
      name: 'ffmpeg and ffprobe',
      ok: diag ? !!(diag.ffmpeg && diag.ffprobe) : null,
      detail: diag ? (diag.ffmpeg && diag.ffprobe ? diag.ffmpeg : `missing: ${[!diag.ffmpeg && 'ffmpeg', !diag.ffprobe && 'ffprobe'].filter(Boolean).join(', ')}`) : 'checking…',
      fix: 'Windows: winget install Gyan.FFmpeg · macOS: brew install ffmpeg · Debian/Ubuntu: sudo apt install ffmpeg; then restart the app',
    },
    {
      name: 'Text-to-speech key',
      ok: keys ? keys.keys.some((k) => k.source) : null,
      detail: keys ? (keys.keys.filter((k) => k.source).map((k) => `${k.provider} (${k.source})`).join(', ') || 'none') : 'checking…',
      fix: 'Settings → API keys (only needed for audio; preparing scripts works without one)',
    },
    {
      name: 'Workspace',
      ok: !!status,
      detail: status ? status.workspace : workspace ? `${workspace} is not a workspace yet` : 'no folder chosen',
      fix: 'Workspace tab: choose a folder and "Make it a workspace" (or run podcastz workspace init <folder>)',
    },
    {
      name: 'AI session with the podcastz plugin',
      ok: status ? !!status.session : null,
      detail: status?.session ? `last seen ${status.session.state}${status.session.updated ? ', ' + status.session.updated : ''}` : 'no session has reported yet',
      fix: 'In Claude Code: /plugin marketplace add drzdez/podcastz, /plugin install podcastz@podcastz, then Start in the header (the plugin reports the session here)',
    },
  ]);

  async function copyDiagnostics() {
    const text = [
      `podcastz app ${diag?.app_version} on ${diag?.os}/${diag?.arch}`,
      ...checks.map((c) => `${c.ok ? 'OK ' : c.ok === false ? 'NO ' : '?  '} ${c.name}: ${c.detail}`),
    ].join('\n');
    await navigator.clipboard.writeText(text);
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }
</script>

<section class="help">
  <h2>Setup check</h2>
  <ul class="checks">
    {#each checks as c}
      <li class:ok={c.ok === true} class:bad={c.ok === false}>
        <span class="mark">{c.ok === true ? '✓' : c.ok === false ? '✗' : '…'}</span>
        <div>
          <strong>{c.name}</strong> <small>{c.detail}</small>
          {#if c.ok === false && c.fix}<div class="fix">{c.fix}</div>{/if}
        </div>
      </li>
    {/each}
  </ul>
  <div class="row">
    <button onclick={loadDiag}>Check again</button>
    <button onclick={copyDiagnostics}>{copied ? 'Copied' : 'Copy for a bug report'}</button>
    <button onclick={() => openUrl(DOCS.issues)}>Report a problem</button>
  </div>

  <h2>How it works</h2>
  <p>podcastz never talks to an AI model. Your own AI session (Claude Code with the podcastz plugin, or another tool
    following <code>AGENTS.md</code>) prepares the content; this app shows it, takes your approvals and makes the audio.
    Both work on the same files in the workspace.</p>
  <ol>
    <li><strong>Interview</strong> – <em>Start</em> the AI session (header). It asks what you want to understand, for whom,
      how long and in which language, and writes <code>BRIEF.md</code>.</li>
    <li><strong>Research</strong> – the session collects sources and lists them as <em>proposed</em>. Approve or reject them in the
      podcast's tab; only approved sources are used.</li>
    <li><strong>Script</strong> and <strong>review</strong> – the session writes two-voice scripts and has every claim checked against the sources.</li>
    <li><strong>Ready</strong> – the scripts pass the check (shown in the podcast's tab).</li>
    <li><strong>Audio</strong> – see the price, confirm, <em>Generate audio</em>; only lines not generated before cost money. Then <em>Publish</em>
      copies the episodes to your sync folder.</li>
  </ol>
  <p>Anything else for the session (a new podcast, a better source, a shorter episode): type it under
    <em>Ask the AI session</em>. The session picks it up with your next message there and marks it done.</p>
  <div class="row">
    <button onclick={() => openUrl(DOCS.gettingStarted)}>Installation guide</button>
    <button onclick={() => openUrl(DOCS.howItWorks)}>How the data flows</button>
    <button onclick={() => openUrl(DOCS.skills)}>The AI skills</button>
  </div>

  <h2>About</h2>
  <p>podcastz {diag?.app_version ?? ''} · MIT licence · <a href={DOCS.releases} onclick={(e) => { e.preventDefault(); openUrl(DOCS.releases); }}>releases</a></p>
  <div class="row">
    <button disabled={checking} onclick={onCheckUpdates}>{checking ? 'Checking…' : 'Check for updates'}</button>
    <small>{updateMsg}</small>
  </div>
  <p><small>Automatic check {autoCheck ? 'once a day' : 'off'}{lastCheck ? `, last ${new Date(lastCheck).toLocaleString()}` : ''} ·
    <a href="#settings" onclick={(e) => { e.preventDefault(); onOpenSettings(); }}>change in Settings</a></small></p>

  <h3>Release notes</h3>
  {#each RELEASES as r}
    <h4>{r.version} <small>{r.date}</small></h4>
    <ul>{#each r.items as i}<li>{@html itemHtml(i)}</li>{/each}</ul>
  {/each}
</section>

<style>
  .help { max-width: 900px; }
  .checks { list-style: none; padding: 0; }
  .checks li { display: flex; gap: 10px; padding: 6px 0; border-bottom: 1px solid #eceef2; }
  .mark { width: 18px; font-weight: 700; color: #8a90a0; }
  .ok .mark { color: #0a7a3d; }
  .bad .mark { color: #b42318; }
  .fix { font-size: 13px; color: #8a6100; margin-top: 2px; }
  .row { display: flex; gap: 8px; margin: 12px 0; align-items: center; flex-wrap: wrap; }
  h4 { margin: 12px 0 4px; }
  li { margin: 3px 0; }
</style>
