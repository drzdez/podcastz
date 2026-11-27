<script lang="ts">
  // Read an episode's script by chapter and listen to it: the player jumps to chapters and replicas
  // and highlights the replica being spoken, using the timing manifest the build writes next to the MP3.
  import { cli, audioUrl, type EpisodeView, type EpisodeLine } from './api';

  interface Props { workspace: string; slug: string }
  let { workspace, slug }: Props = $props();

  let episodes = $state<EpisodeView[]>([]);
  let selected = $state<string | null>(null);
  let error = $state('');
  let src = $state('');
  let audio = $state<HTMLAudioElement | null>(null);
  let time = $state(0);
  let duration = $state(0);
  let paused = $state(true);
  let rate = $state(1);
  let follow = $state(true);

  const ep = $derived(episodes.find((e) => e.episode === selected) ?? null);
  const timed = $derived(!!ep?.audio?.timed);
  const current = $derived(timed && ep ? ep.lines.find((l) => l.start !== undefined && time >= l.start && time < (l.end ?? Infinity)) ?? null : null);
  const currentChapter = $derived(ep && timed ? [...ep.chapters].reverse().find((c) => c.start !== undefined && time >= c.start) ?? null : null);
  /** Lines grouped under their chapter (a group without a title for lines before the first chapter). */
  const groups = $derived.by(() => {
    if (!ep) return [];
    const out: { title: string | null; start?: number; lines: EpisodeLine[] }[] = [];
    const starts = new Map(ep.chapters.map((c) => [c.first_line, c]));
    for (const l of ep.lines) {
      const c = starts.get(l.index);
      if (c || !out.length) out.push({ title: c?.title ?? null, start: c?.start, lines: [] });
      out[out.length - 1].lines.push(l);
    }
    return out;
  });

  const POS_KEY = 'podcastz.positions';
  function savedPositions(): Record<string, number> {
    try { return JSON.parse(localStorage.getItem(POS_KEY) ?? '{}'); } catch { return {}; }
  }
  function savePosition() {
    if (!ep?.audio || !audio) return;
    try {
      const all = savedPositions();
      all[ep.audio.file] = audio.currentTime;
      localStorage.setItem(POS_KEY, JSON.stringify(all));
    } catch { /* storage unavailable: no resume */ }
  }

  async function load() {
    try {
      episodes = (await cli<{ episodes: EpisodeView[] }>(['episodes', slug], workspace)).episodes;
      error = '';
      if (!episodes.some((e) => e.episode === selected)) await select(episodes[0]?.episode ?? null);
    } catch (e) { error = String((e as Error).message ?? e); }
  }

  async function select(name: string | null) {
    savePosition();
    selected = name;
    time = 0; duration = 0; src = '';
    const a = episodes.find((e) => e.episode === name)?.audio;
    if (a) {
      try { src = await audioUrl(a.file); } catch (e) { error = String(e); }
    }
  }

  function onLoaded() {
    if (!audio || !ep?.audio) return;
    duration = audio.duration;
    audio.playbackRate = rate;
    const pos = savedPositions()[ep.audio.file];
    if (pos && pos < audio.duration - 5) audio.currentTime = pos;
  }

  function seek(t: number | undefined, play = true) {
    if (!audio || t === undefined) return;
    audio.currentTime = Math.max(0, Math.min(t, audio.duration || t));
    if (play) audio.play();
  }
  const toggle = () => { if (audio) audio.paused ? audio.play() : audio.pause(); };
  const skip = (s: number) => audio && seek(audio.currentTime + s, !audio.paused);
  function setRate(r: number) { rate = r; if (audio) audio.playbackRate = r; }

  function fmt(s: number | undefined) {
    if (s === undefined || !isFinite(s)) return '–:––';
    const m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  function onKey(e: KeyboardEvent) {
    const t = e.target as HTMLElement;
    if (!src || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(t.tagName)) return;
    if (e.key === ' ') { e.preventDefault(); toggle(); }
    else if (e.key === 'ArrowLeft') skip(-10);
    else if (e.key === 'ArrowRight') skip(10);
  }

  // keep the spoken replica in view while playing
  $effect(() => {
    if (!follow || paused || !current) return;
    document.getElementById(`line-${current.index}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });

  $effect(() => { slug; workspace; load(); });
</script>

<svelte:window onkeydown={onKey} onbeforeunload={savePosition} />

{#if error}<p class="error">{error}</p>{/if}

<div class="layout">
  <aside>
    {#each episodes as e (e.episode)}
      <button class:active={e.episode === selected} onclick={() => select(e.episode)}>
        <strong>{e.title}</strong>
        <small>{e.lines.length} lines · {e.chapters.length} chapters · {e.audio ? (e.audio.duration ? fmt(e.audio.duration) : 'audio') : 'no audio'}</small>
      </button>
    {:else}
      <p><small>No episodes yet.</small></p>
    {/each}
  </aside>

  {#if ep}
    <div class="main">
      <div class="player">
        {#if src}
          <audio bind:this={audio} {src} preload="metadata" onloadedmetadata={onLoaded}
            ontimeupdate={() => (time = audio?.currentTime ?? 0)} onplay={() => (paused = false)}
            onpause={() => { paused = true; savePosition(); }}></audio>
          <div class="controls">
            <button onclick={() => skip(-15)} title="Back 15 s (←: 10 s)">−15</button>
            <button class="play" onclick={toggle} title="Play / pause (space)">{paused ? '▶' : '❚❚'}</button>
            <button onclick={() => skip(15)} title="Forward 15 s (→: 10 s)">+15</button>
            <input class="bar" type="range" min="0" max={duration || 0} step="0.5" value={time}
              oninput={(e) => seek(Number(e.currentTarget.value), !paused)} aria-label="Position" />
            <span class="time">{fmt(time)} / {fmt(duration)}</span>
            <select value={rate} onchange={(e) => setRate(Number(e.currentTarget.value))} aria-label="Speed">
              {#each [0.8, 1, 1.15, 1.25, 1.5, 1.75, 2] as r}<option value={r}>{r}×</option>{/each}
            </select>
          </div>
          {#if timed && ep.chapters.length}
            <div class="chapters">
              {#each ep.chapters as c}
                <button class:active={currentChapter === c} onclick={() => seek(c.start)}>{fmt(c.start)} {c.title}</button>
              {/each}
            </div>
          {/if}
          <div class="hints">
            {#if !timed}<small>No timings for this script (the script changed after the audio was made, or the audio is older): plays, but cannot jump to lines.</small>
            {:else if ep.audio?.changed_since}<small>The script file changed after the audio was made; text and audio may differ.</small>
            {:else}<small>Click a line to play from there. Space: play/pause, ←/→: 10 s.</small>{/if}
            {#if timed}<label><input type="checkbox" bind:checked={follow} /> follow the text</label>{/if}
          </div>
        {:else}
          <p><small>No audio for this episode yet. Generate it in the Audio section.</small></p>
        {/if}
      </div>

      <article>
        <h2>{ep.title}</h2>
        {#each groups as g}
          {#if g.title}
            <h3>{#if timed}<button class="link" onclick={() => seek(g.start)}>{g.title}</button> <small>{fmt(g.start)}</small>{:else}{g.title}{/if}</h3>
          {/if}
          {#each g.lines as l (l.index)}
            <p id={`line-${l.index}`} class="line" class:current={current?.index === l.index} class:clickable={timed}>
              {#if timed}
                <button class="replica" onclick={() => seek(l.start)} title={fmt(l.start)}>
                  <span class="who">{l.speaker}</span> {l.text}
                </button>
              {:else}
                <span class="who">{l.speaker}</span> {l.text}
              {/if}
            </p>
          {/each}
        {/each}
      </article>
    </div>
  {/if}
</div>

<style>
  .layout { display: grid; grid-template-columns: 240px 1fr; gap: 16px; align-items: start; }
  aside { display: flex; flex-direction: column; gap: 6px; position: sticky; top: 8px; }
  aside button { text-align: left; display: flex; flex-direction: column; gap: 2px; }
  aside button.active { border-color: #1e4fa8; background: #eef3fc; }
  .player { position: sticky; top: 0; background: #f6f7f9; padding: 8px 0; z-index: 2; border-bottom: 1px solid #d9dde5; }
  .controls { display: flex; gap: 8px; align-items: center; }
  .controls .play { width: 44px; font-weight: 700; }
  .bar { flex: 1; }
  .time { font-variant-numeric: tabular-nums; color: #6b7280; min-width: 92px; text-align: right; }
  .chapters { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .chapters button { font-size: 12px; padding: 3px 8px; }
  .chapters button.active { background: #d7efe0; border-color: #0a7a3d; }
  .hints { display: flex; gap: 16px; justify-content: space-between; margin-top: 6px; }
  .hints label { font-size: 13px; color: #6b7280; display: flex; gap: 4px; align-items: center; }
  article { max-width: 760px; }
  h3 { margin: 18px 0 6px; font-size: 16px; }
  .line { margin: 4px 0; padding: 4px 8px; border-radius: 6px; line-height: 1.5; }
  .line.current { background: #fff4d6; }
  .replica { all: unset; cursor: pointer; display: block; }
  .line.clickable:hover { background: #eef3fc; }
  .line.current:hover { background: #ffecb3; }
  .who { font-size: 11px; font-weight: 700; color: #1e4fa8; margin-right: 6px; letter-spacing: 0.03em; }
  button.link { border: none; background: none; padding: 0; font: inherit; color: inherit; cursor: pointer; text-decoration: underline dotted; }
  .error { color: #b42318; }
</style>
