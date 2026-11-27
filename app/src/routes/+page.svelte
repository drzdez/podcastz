<script lang="ts">
  import { onMount } from 'svelte';
  import { open as pickFolder } from '@tauri-apps/plugin-dialog';
  import { openPath } from '@tauri-apps/plugin-opener';
  import { getVersion } from '@tauri-apps/api/app';
  import { check, type Update } from '@tauri-apps/plugin-updater';
  import { relaunch } from '@tauri-apps/plugin-process';
  import {
    cli, job, cancelJob, setWorkspace, openSession, keyStatus, keySet, keyDelete, getSetting, setSetting,
    type WorkspaceStatus, type Source, type Issue, type Estimate, type KeyStatus, type JobLine, type KeyCheck,
  } from '$lib/api';
  import Help from '$lib/Help.svelte';
  import Episodes from '$lib/Episodes.svelte';
  import { shouldCheck, shouldOffer } from '$lib/update';
  import { RELEASES, releasesSince, itemHtml, type Release } from '$lib/releaseNotes';

  const STAGES = ['interview', 'research', 'script', 'review', 'ready'];

  let tab = $state<'workspace' | 'project' | 'settings' | 'help'>('workspace');
  let projectView = $state<'overview' | 'listen'>('overview');

  // updates and release notes (devstackz ADR 0002 and the release-notes requirement)
  let appVersion = $state('');
  let autoCheck = $state(true);
  let lastCheck = $state<number | null>(null);
  let skippedVersion = $state<string | null>(null);
  let checking = $state(false);
  let updateMsg = $state('');
  let available = $state<Update | null>(null);
  let installing = $state<string | null>(null);
  let whatsNew = $state<Release[]>([]);
  let keyChecks = $state<Record<string, KeyCheck>>({});
  let workspace = $state('');
  let client = $state('claude');
  let status = $state<WorkspaceStatus | null>(null);
  let error = $state('');
  let notice = $state('');

  let slug = $state<string | null>(null);
  let sources = $state<Source[]>([]);
  let issues = $state<Issue[]>([]);
  let estimate = $state<Estimate | null>(null);
  let estimateError = $state('');
  let requestText = $state('');

  let keys = $state<KeyStatus | null>(null);
  let keyInput = $state<Record<string, string>>({});
  let keyMsg = $state<Record<string, string>>({});

  let jobId = $state<number | null>(null);
  let jobLog = $state<string[]>([]);
  let progress = $state<{ episode: string; line: number; lines: number } | null>(null);

  const project = $derived(status?.projects.find((p) => p.slug === slug) ?? null);
  const projectDir = $derived(status && slug ? `${status.workspace}\\${slug}` : '');
  const sessionAlive = $derived(!!status?.session && status.session.state !== 'ended');

  let refreshing = false;
  async function refresh() {
    if (!workspace) { status = null; return; }
    if (refreshing) return; // never stack CLI calls when one is slow
    refreshing = true;
    try {
      status = await cli<WorkspaceStatus>(['workspace', 'status'], workspace);
      error = '';
    } catch (e) {
      status = null;
      const msg = String((e as Error).message ?? e);
      // "not a workspace" is shown as a notice with the button to fix it, not as an error
      error = msg.startsWith('Not inside a podcastz workspace') ? '' : msg;
    } finally {
      refreshing = false;
    }
  }

  async function loadProject() {
    if (!slug || !status) return;
    const cwd = status.workspace;
    try { sources = (await cli<{ sources: Source[] }>(['source', 'list', slug], cwd)).sources; } catch { sources = []; }
    try { issues = (await cli<{ issues: Issue[] }>(['check', slug], cwd)).issues; } catch { issues = []; }
    try { estimate = await cli<Estimate>(['estimate', slug], cwd); estimateError = ''; }
    catch (e) { estimate = null; estimateError = String((e as Error).message ?? e); }
  }

  async function chooseWorkspace() {
    const dir = await pickFolder({ directory: true, title: 'podcastz workspace' });
    if (typeof dir === 'string') await useWorkspace(dir);
  }

  async function useWorkspace(dir: string) {
    workspace = dir;
    await setSetting('workspace', dir);
    await refresh();
    if (!status) {
      error = '';
      notice = 'This folder is not a podcastz workspace yet. "Make it a workspace" prepares it for your podcasts and the AI session.';
    } else {
      notice = '';
      await setWorkspace(status.workspace);
    }
  }

  async function initWorkspace() {
    try {
      await cli(['workspace', 'init', workspace], workspace);
      await useWorkspace(workspace);
    } catch (e) { error = String((e as Error).message ?? e); }
  }

  async function session(focusOnly: boolean) {
    if (!status) return;
    try {
      const r = await openSession(status.workspace, focusOnly, !!status.session, client);
      notice = r === 'focused' ? 'Switched to the AI session window.' : 'AI session started in a terminal window.';
    } catch (e) { notice = String(e); }
  }

  async function setSource(s: Source, st: 'approved' | 'rejected' | 'proposed') {
    await cli(['source', 'set', slug!, s.id, '--status', st], status!.workspace);
    await loadProject();
    await refresh();
  }

  async function ask(text: string) {
    if (!text.trim() || !status) return;
    await cli(['request', 'add', '--text', text.trim(), ...(slug ? ['--project', slug] : [])], status.workspace);
    requestText = '';
    await refresh();
    notice = 'Request left for the AI session. It sees it with your next message there.';
  }

  async function runJob(args: string[], confirmText?: string) {
    if (!status || jobId !== null) return;
    if (confirmText && !confirm(confirmText)) return;
    jobLog = []; progress = null;
    const code = await job(args, status.workspace, (l: JobLine) => {
      if (l.event === 'progress') progress = l as any;
      else if (l.event === 'episode') jobLog = [...jobLog, `${l.episode}: ${l.file ? 'done' : 'segments missing'}`];
      else if (l.event === 'done') jobLog = [...jobLog, `Finished: ${l.chars_sent} characters, ~$${l.usd}`];
      else if (l.event === 'published') jobLog = [...jobLog, `Published to ${l.target} (${(l.copied as string[]).length} files)`];
      else if (l.event === 'error') jobLog = [...jobLog, `Error ${l.episode ?? ''}: ${l.message}`];
      else if (l.event === 'sample') jobLog = [...jobLog, `Sample ready (${l.chars_per_hour} chars/hour)`];
      else if (l.event === 'log' && l.message) jobLog = [...jobLog, String(l.message)];
    }, (id) => (jobId = id));
    jobId = null; progress = null;
    jobLog = [...jobLog, `exit code ${code}`];
    await loadProject();
    await refresh();
  }

  async function loadKeys() {
    try { keys = await keyStatus(); } catch (e) { error = String((e as Error).message ?? e); }
  }

  async function saveKey(provider: string) {
    const value = keyInput[provider]?.trim();
    if (!value) return;
    try {
      await keySet(provider, value);
      keyInput[provider] = '';
      keyMsg[provider] = 'saved';
      await loadKeys();
      await testKey(provider); // verify on save (no cost)
    } catch (e) { keyMsg[provider] = String((e as Error).message ?? e); }
  }

  async function testKey(provider: string) {
    keyMsg[provider] = 'checking…';
    let result: KeyCheck;
    try {
      const r = await cli<{ ok: boolean; message: string }>(['key', 'test', provider]);
      result = { ok: r.ok, message: r.message, at: Date.now() };
    } catch (e) {
      result = { ok: false, message: String((e as Error).message ?? e), at: Date.now() };
    }
    keyMsg[provider] = '';
    keyChecks = { ...keyChecks, [provider]: result };
    await setSetting('keyChecks', keyChecks);
  }

  async function deleteKey(provider: string) {
    await keyDelete(provider);
    keyMsg[provider] = 'deleted from the credential store';
    const { [provider]: _, ...rest } = keyChecks;
    keyChecks = rest;
    await setSetting('keyChecks', keyChecks);
    await loadKeys();
  }

  async function checkForUpdates(manual: boolean) {
    if (checking) return;
    checking = true;
    updateMsg = manual ? 'Checking…' : '';
    lastCheck = Date.now();
    await setSetting('lastUpdateCheck', lastCheck);
    try {
      const u = await check();
      if (u && shouldOffer(appVersion, u.version, manual ? null : skippedVersion)) {
        available = u;
        updateMsg = `podcastz ${u.version} is available.`;
      } else if (manual) {
        updateMsg = `podcastz ${appVersion} is up to date.`;
      }
    } catch (e) {
      // automatic checks stay quiet (offline, or no release published yet)
      const msg = String(e);
      if (manual) updateMsg = /404|Not Found|valid release JSON/i.test(msg)
        ? 'No release with automatic updates has been published yet.'
        : `Cannot check for updates: ${msg}`;
    } finally {
      checking = false;
    }
  }

  async function installUpdate() {
    if (!available || jobId !== null) return;
    installing = 'Downloading…';
    try {
      let total = 0, done = 0;
      await available.downloadAndInstall((ev) => {
        if (ev.event === 'Started') total = ev.data.contentLength ?? 0;
        else if (ev.event === 'Progress') {
          done += ev.data.chunkLength;
          installing = total ? `Downloading… ${Math.round((done / total) * 100)} %` : 'Downloading…';
        } else if (ev.event === 'Finished') installing = 'Installing…';
      });
      await relaunch();
    } catch (e) {
      installing = null;
      updateMsg = `Update failed: ${e}`;
    }
  }

  async function skipUpdate() {
    if (!available) return;
    skippedVersion = available.version;
    await setSetting('skippedVersion', skippedVersion);
    available = null;
  }

  async function setAutoCheck(on: boolean) {
    autoCheck = on;
    await setSetting('checkUpdates', on);
  }

  async function closeWhatsNew() {
    whatsNew = [];
    await setSetting('lastSeenVersion', appVersion);
  }

  onMount(() => {
    (async () => {
      appVersion = await getVersion();
      autoCheck = (await getSetting<boolean>('checkUpdates')) ?? true;
      lastCheck = await getSetting<number>('lastUpdateCheck');
      skippedVersion = await getSetting('skippedVersion');
      keyChecks = (await getSetting<Record<string, KeyCheck>>('keyChecks')) ?? {};
      // release notes once per version, after an install or an update
      whatsNew = releasesSince(RELEASES, await getSetting('lastSeenVersion'), appVersion);
      if (autoCheck && shouldCheck(lastCheck, Date.now())) checkForUpdates(false);
    })();
    (async () => {
      client = (await getSetting('client')) ?? 'claude';
      const ws = await getSetting('workspace');
      if (ws) await useWorkspace(ws);
    })();
    loadKeys();
    const timer = setInterval(() => { if (jobId === null) refresh(); }, 3000);
    return () => clearInterval(timer);
  });

  $effect(() => { if (tab === 'project' && slug) loadProject(); });
</script>

<main>
  <header>
    <h1>podcastz</h1>
    <nav>
      <button class:active={tab === 'workspace'} onclick={() => (tab = 'workspace')}>Workspace</button>
      <button class:active={tab === 'project'} disabled={!slug} onclick={() => (tab = 'project')}>
        {slug ?? 'Project'}
      </button>
      <button class:active={tab === 'settings'} onclick={() => { tab = 'settings'; loadKeys(); }}>Settings</button>
      <button class:active={tab === 'help'} onclick={() => { tab = 'help'; loadKeys(); }}>Help</button>
    </nav>
    {#if status}
      <div class="session" class:alive={sessionAlive}>
        AI session: {status.session ? status.session.state : 'not started'}
        {#if sessionAlive}<button onclick={() => session(true)}>Show</button>{/if}
        <button onclick={() => session(false)}>{status.session ? 'Continue' : 'Start'}</button>
      </div>
    {/if}
  </header>

  {#if available}
    <div class="banner">
      <div>
        <strong>podcastz {available.version} is available</strong> <small>(you have {appVersion})</small>
        {#if available.body}<details><summary>What's new</summary><pre class="notes">{available.body}</pre></details>{/if}
      </div>
      {#if installing}
        <span>{installing}</span>
      {:else}
        <button disabled={jobId !== null} title={jobId !== null ? 'Wait until the audio task finishes' : ''}
          onclick={installUpdate}>Install and restart</button>
        <button onclick={skipUpdate}>Skip this version</button>
        <button onclick={() => (available = null)}>Later</button>
      {/if}
    </div>
  {/if}

  {#if whatsNew.length}
    <div class="overlay" role="presentation">
      <div class="dialog" role="dialog" aria-modal="true" aria-label="What's new">
        <h2>{whatsNew.length === 1 && whatsNew[0].version === appVersion ? `What's new in podcastz ${appVersion}` : `podcastz updated to ${appVersion}`}</h2>
        {#each whatsNew as r}
          {#if whatsNew.length > 1}<h4>{r.version} <small>{r.date}</small></h4>{/if}
          <ul>{#each r.items as i}<li>{@html itemHtml(i)}</li>{/each}</ul>
        {/each}
        <p><small>Release notes stay available in Help.</small></p>
        <button onclick={closeWhatsNew}>OK</button>
      </div>
    </div>
  {/if}

  {#if error}<p class="error">{error}</p>{/if}
  {#if notice}<p class="notice">{notice}</p>{/if}

  {#if tab === 'workspace'}
    <section>
      <div class="row">
        <input bind:value={workspace} placeholder="Workspace folder" onchange={() => useWorkspace(workspace)} />
        <button onclick={chooseWorkspace}>Choose…</button>
        {#if workspace && !status}<button onclick={initWorkspace}>Make it a workspace</button>{/if}
      </div>
      {#if status}
        <table>
          <thead><tr><th>Podcast</th><th>Stage</th><th>Episodes</th><th>Sources</th><th></th></tr></thead>
          <tbody>
            {#each status.projects as p (p.slug)}
              <tr>
                <td><strong>{p.title ?? p.slug}</strong><br /><small>{p.slug} · {p.language ?? 'language not set'}</small></td>
                <td>
                  <div class="stages">
                    {#each STAGES as st}<span class:done={STAGES.indexOf(st) <= STAGES.indexOf(p.state.stage ?? 'interview')}>{st}</span>{/each}
                  </div>
                  <small>{p.state.message ?? ''}</small>
                </td>
                <td>{p.episodes}</td>
                <td>{p.sources.approved} approved<br /><small>{p.sources.proposed} to review</small></td>
                <td><button onclick={() => { slug = p.slug; tab = 'project'; }}>Open</button></td>
              </tr>
            {:else}
              <tr><td colspan="5">No podcasts yet. Start the AI session and ask for a new podcast.</td></tr>
            {/each}
          </tbody>
        </table>
        <h3>Ask the AI session</h3>
        <div class="row">
          <input bind:value={requestText} placeholder="e.g. New podcast: how DNS works, 20 minutes, beginners" />
          <button onclick={() => ask(requestText)}>Leave request</button>
        </div>
        {#if status.requests.length}
          <ul>{#each status.requests as r}<li>{r.text} <small>({r.project ?? 'workspace'}, pending)</small></li>{/each}</ul>
        {/if}
      {/if}
    </section>
  {:else if tab === 'project' && project}
    <section>
      <h2>{project.title ?? project.slug}</h2>
      <p><small>{project.state.stage}: {project.state.message ?? ''}</small>
        <button onclick={() => openPath(projectDir)}>Open folder</button></p>
      <div class="subnav">
        <button class:active={projectView === 'overview'} onclick={() => (projectView = 'overview')}>Sources, check and audio</button>
        <button class:active={projectView === 'listen'} onclick={() => (projectView = 'listen')}>Script and player</button>
      </div>
    {#if projectView === 'listen'}
      <Episodes workspace={status!.workspace} slug={project.slug} />
    {:else}

      <h3>Sources</h3>
      <table>
        <thead><tr><th>Source</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {#each sources as s (s.id)}
            <tr class={s.status}>
              <td><strong>{s.title}</strong><br /><small>{s.origin}{s.note ? ' – ' + s.note : ''}</small></td>
              <td>{s.status}<br /><small>by {s.added_by}</small></td>
              <td class="actions">
                {#if s.status !== 'approved'}<button onclick={() => setSource(s, 'approved')}>Approve</button>{/if}
                {#if s.status !== 'rejected'}<button onclick={() => setSource(s, 'rejected')}>Reject</button>{/if}
                <button onclick={() => ask(`Re-check source ${s.id} (${s.title}) in project ${slug} and summarise what it adds.`)}>Re-check</button>
              </td>
            </tr>
          {:else}
            <tr><td colspan="3">No sources listed yet.</td></tr>
          {/each}
        </tbody>
      </table>
      <div class="row">
        <input bind:value={requestText} placeholder="Ask about this podcast, e.g. Find a primary source on DNSSEC" />
        <button onclick={() => ask(requestText)}>Leave request</button>
      </div>

      <h3>Scripts</h3>
      {#if issues.length}
        <ul class="issues">{#each issues.slice(0, 30) as i}<li class={i.level}>{i.file}:{i.line} {i.message}</li>{/each}</ul>
        {#if issues.length > 30}<small>… {issues.length - 30} more</small>{/if}
      {:else}
        <p><small>{project.episodes ? 'Check passed.' : 'No episodes yet.'}</small></p>
      {/if}

      <h3>Audio</h3>
      {#if estimate}
        <table>
          <thead><tr><th>Episode</th><th>Characters</th><th>Not generated</th><th>Est. min</th><th>Audio min</th></tr></thead>
          <tbody>
            {#each estimate.episodes as e}<tr><td>{e.episode}</td><td>{e.chars}</td><td>{e.to_generate}</td><td>{e.est_min}</td><td>{e.audio_min || '-'}</td></tr>{/each}
          </tbody>
        </table>
        <p>{estimate.model}, {estimate.rate}: full ${estimate.usd_total.toFixed(2)}, still to generate
          <strong>${estimate.usd_to_generate.toFixed(2)}</strong> (${estimate.usd_per_hour.toFixed(2)} per audio hour)</p>
        <div class="row">
          <button disabled={jobId !== null || issues.some((i) => i.level === 'error')}
            onclick={() => runJob(['sample', slug!, '--yes'], 'Generate a short voice sample (a few cents)?')}>Sample</button>
          <button disabled={jobId !== null || issues.some((i) => i.level === 'error')}
            onclick={() => runJob(['build', slug!, '--yes'], `Generate audio for about $${estimate!.usd_to_generate.toFixed(2)}?`)}>Generate audio</button>
          <button disabled={jobId !== null} onclick={() => runJob(['publish', slug!])}>Publish</button>
          <button onclick={() => openPath(projectDir + '\\audio')}>Audio folder</button>
          {#if jobId !== null}<button onclick={() => cancelJob(jobId!)}>Cancel</button>{/if}
        </div>
        {#if progress}<progress max={progress.lines} value={progress.line}></progress> {progress.episode} {progress.line}/{progress.lines}{/if}
        {#if jobLog.length}<pre>{jobLog.join('\n')}</pre>{/if}
      {:else}
        <p><small>{estimateError || 'No estimate yet.'}</small></p>
      {/if}
    {/if}
    </section>
  {:else if tab === 'settings'}
    <section>
      <h2>API keys for text-to-speech</h2>
      <p><small>Keys are stored in the operating system credential store ({keys?.store === false ? 'not available' : 'Windows Credential Manager, macOS Keychain or Linux Secret Service'}),
        shared with the podcastz CLI. The app never shows a key; saving checks it with a free request to the provider.
        Order: <code>PODCASTZ_&lt;PROVIDER&gt;_API_KEY</code> (explicit override), then the stored key, then the provider's own variable.
        One key is enough; it is only needed for audio.</small></p>
      {#if keys}
        {#each keys.keys as k}
          {@const kc = keyChecks[k.provider]}
          <div class="key">
            <strong>{k.provider}</strong>
            <span>{k.source ? (k.source === 'store' ? 'stored' : `from ${k.source}`) : 'missing'}</span>
            <input type="password" autocomplete="off" placeholder={k.source === 'store' ? 'paste a new key to replace' : 'paste key'}
              bind:value={keyInput[k.provider]} onkeydown={(e) => e.key === 'Enter' && saveKey(k.provider)} />
            <button disabled={!keyInput[k.provider]?.trim()} onclick={() => saveKey(k.provider)}>Save</button>
            <button disabled={!k.source} onclick={() => testKey(k.provider)}>Test</button>
            <button disabled={k.source !== 'store'} onclick={() => deleteKey(k.provider)}>Remove</button>
            <small class:bad={kc && !kc.ok} class:good={kc?.ok}>
              {keyMsg[k.provider] || (kc ? `${kc.ok ? '✓' : '✗'} ${kc.message} · checked ${new Date(kc.at).toLocaleString()}` : '')}
              {#if k.source && k.source !== 'store' && k.source.startsWith('PODCASTZ_')} · the override variable wins over a stored key{/if}
            </small>
          </div>
        {/each}
      {/if}
      <h2>Updates</h2>
      <label class="check"><input type="checkbox" checked={autoCheck} onchange={(e) => setAutoCheck(e.currentTarget.checked)} />
        Check for updates automatically (at start, at most once a day)</label>
      <div class="row">
        <button disabled={checking} onclick={() => checkForUpdates(true)}>{checking ? 'Checking…' : 'Check now'}</button>
        <small>{updateMsg || (lastCheck ? `Last check ${new Date(lastCheck).toLocaleString()}` : 'Not checked yet')}</small>
        {#if skippedVersion}<small>· skipped {skippedVersion}
          <button class="link" onclick={async () => { skippedVersion = null; await setSetting('skippedVersion', null); }}>undo</button></small>{/if}
      </div>
      <p><small>Updates are downloaded from the GitHub Releases of drzdez/podcastz and verified with the release signing key before they are installed. Nothing is sent except the request for the latest version.</small></p>
      <h2>AI session</h2>
      <div class="row">
        <label for="client">Command</label>
        <input id="client" bind:value={client} onchange={() => setSetting('client', client)} />
      </div>
      <p><small>Started in the workspace in a Windows Terminal window named "podcastz": a new session gets
        <code>/podcastz:prepare</code>, otherwise <code>--continue</code>. The app never talks to the model itself.</small></p>
    </section>
  {:else if tab === 'help'}
    <Help {status} {workspace} {keys} {checking} {updateMsg} {autoCheck} {lastCheck}
      onCheckUpdates={() => checkForUpdates(true)} onOpenSettings={() => (tab = 'settings')} />
  {/if}
</main>

<style>
  :global(body) { margin: 0; font-family: system-ui, sans-serif; background: #f6f7f9; color: #1d2330; }
  main { padding: 0 20px 40px; }
  header { display: flex; align-items: center; gap: 20px; border-bottom: 1px solid #d9dde5; padding: 10px 0; }
  h1 { font-size: 20px; margin: 0; }
  nav button { background: none; border: none; padding: 6px 10px; cursor: pointer; border-radius: 6px; }
  nav button.active { background: #e3e8f2; font-weight: 600; }
  .session { margin-left: auto; display: flex; gap: 8px; align-items: center; font-size: 14px; color: #6b7280; }
  .session.alive { color: #0a7a3d; }
  section { max-width: 1100px; }
  .row { display: flex; gap: 8px; margin: 12px 0; align-items: center; }
  .row input { flex: 1; }
  input { padding: 6px 8px; border: 1px solid #c7ccd6; border-radius: 6px; }
  button { padding: 6px 12px; border: 1px solid #c7ccd6; border-radius: 6px; background: white; cursor: pointer; }
  button:disabled { opacity: 0.5; cursor: default; }
  table { width: 100%; border-collapse: collapse; background: white; margin: 8px 0; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid #eceef2; vertical-align: top; }
  tr.rejected td { opacity: 0.5; }
  tr.approved td:first-child { border-left: 3px solid #0a7a3d; }
  .actions { white-space: nowrap; }
  .stages { display: flex; gap: 4px; }
  .stages span { font-size: 11px; padding: 1px 5px; border-radius: 4px; background: #eceef2; color: #8a90a0; }
  .stages span.done { background: #d7efe0; color: #0a7a3d; }
  .issues li.error { color: #b42318; }
  .issues li.warning { color: #8a6100; }
  .error { color: #b42318; }
  .notice { color: #1e4fa8; }
  .key { display: grid; grid-template-columns: 110px 220px 1fr auto auto auto; gap: 8px; align-items: center; margin: 8px 0; }
  .key small { grid-column: 2 / -1; color: #6b7280; }
  .key small.good { color: #0a7a3d; }
  .key small.bad { color: #b42318; }
  .check { display: flex; gap: 8px; align-items: center; }
  .subnav { display: flex; gap: 6px; margin: 8px 0 14px; border-bottom: 1px solid #d9dde5; }
  .subnav button { border: none; border-bottom: 2px solid transparent; border-radius: 0; background: none; }
  .subnav button.active { border-bottom-color: #1e4fa8; font-weight: 600; }
  button.link { border: none; background: none; padding: 0 4px; color: #1e4fa8; text-decoration: underline; }
  .banner { display: flex; gap: 10px; align-items: center; background: #e8f0fe; border: 1px solid #b6cdf5; border-radius: 8px; padding: 10px 14px; margin: 12px 0; }
  .banner > div { flex: 1; }
  pre.notes { background: white; color: #1d2330; white-space: pre-wrap; }
  .overlay { position: fixed; inset: 0; background: rgba(20, 24, 33, 0.35); display: flex; align-items: center; justify-content: center; z-index: 10; }
  .dialog { background: white; border-radius: 10px; padding: 20px 24px; max-width: 620px; max-height: 80vh; overflow: auto; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25); }
  pre { background: #1d2330; color: #e6e9ef; padding: 10px; border-radius: 6px; max-height: 240px; overflow: auto; }
  progress { width: 300px; }
  small { color: #6b7280; }
</style>
