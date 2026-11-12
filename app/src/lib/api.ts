// Thin layer over the Rust commands: everything goes through the podcastz CLI (`--json`).
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

export type Stage = 'interview' | 'research' | 'script' | 'review' | 'ready';

export interface ProjectState { stage?: Stage; message?: string; updated?: string }
export interface ProjectSummary {
  slug: string; title?: string; language?: string | null; state: ProjectState; episodes: number;
  sources: { proposed: number; approved: number; rejected: number };
}
export interface SessionInfo { state: 'idle' | 'busy' | 'ended'; updated?: string; project?: string | null; session_id?: string }
export interface Request { id: string; project?: string | null; text: string; status: string; created: string; result?: string }
export interface WorkspaceStatus {
  workspace: string; projects: ProjectSummary[]; session: SessionInfo | null; app: unknown; requests: Request[];
}
export interface Source {
  id: string; title: string; origin: string; file?: string; kind?: string;
  status: 'proposed' | 'approved' | 'rejected'; added_by: string; note?: string;
}
export interface Issue { file: string; line: number; level: 'error' | 'warning'; message: string }
export interface Estimate {
  project: string; language: string; model: string; rate: string; chars: number; to_generate: number;
  est_hours: number; usd_total: number; usd_to_generate: number; usd_per_hour: number; audio_min: number;
  episodes: { episode: string; lines: number; chars: number; to_generate: number; est_min: number; audio_min: number }[];
}
export interface KeyStatus { store: boolean; keys: { provider: string; source: string | null; env: string[] }[] }

/** Run a CLI command; the last JSON line is the result. Errors come back as {event:'error'}. */
export async function cli<T>(args: string[], cwd?: string, stdin?: string): Promise<T> {
  let raw: string;
  try {
    raw = await invoke<string>('cli', { args, cwd: cwd ?? null, stdin: stdin ?? null });
  } catch (e) {
    raw = String(e);
  }
  const lines = raw.trim().split(/\r?\n/).filter(Boolean);
  const last = lines.length ? safeParse(lines[lines.length - 1]) : null;
  if (!last) throw new Error(raw.trim() || 'no output from podcastz');
  if (last.event === 'error') throw new Error(last.message);
  return last as T;
}

function safeParse(line: string): any {
  try { return JSON.parse(line); } catch { return null; }
}

export interface JobLine { event?: string; [k: string]: unknown }

/** Start a long CLI task; onLine gets each JSON line, the promise resolves with the exit code. */
export async function job(args: string[], cwd: string, onLine: (l: JobLine) => void, onStart?: (id: number) => void): Promise<number | null> {
  let unlisten: UnlistenFn | undefined;
  let id = -1;
  const buffered: any[] = [];
  return new Promise(async (resolve, reject) => {
    const handle = (p: any) => {
      if (p.done) { unlisten?.(); resolve(p.code ?? null); return; }
      if (p.line) { const l = safeParse(p.line); if (l) onLine(l); }
      if (p.stderr) onLine({ event: 'log', message: p.stderr });
    };
    unlisten = await listen<any>('job', (e) => {
      if (id < 0) { buffered.push(e.payload); return; }
      if (e.payload.id === id) handle(e.payload);
    });
    try {
      id = await invoke<number>('start_job', { args, cwd });
      onStart?.(id);
      buffered.filter((p) => p.id === id).forEach(handle);
    } catch (e) { unlisten?.(); reject(e); }
  });
}

export const cancelJob = (id: number) => invoke('cancel_job', { id });

// API keys live in the OS credential store, handled in Rust (one entry shared with the CLI).
export const keyStatus = () => invoke<KeyStatus>('key_status');
export const keySet = (provider: string, value: string) => invoke<void>('key_set', { provider, value });
export const keyDelete = (provider: string) => invoke<boolean>('key_delete', { provider });

// App settings (workspace, AI client command, update policy, last key checks) in the Tauri store,
// not in the webview. Never key values.
import { load, type Store } from '@tauri-apps/plugin-store';
let settingsStore: Promise<Store> | null = null;
const settings = () => (settingsStore ??= load('settings.json', { autoSave: true, defaults: {} }));
export async function getSetting<T = string>(key: string): Promise<T | null> {
  return ((await (await settings()).get<T>(key)) ?? null);
}
export async function setSetting<T = string>(key: string, value: T) {
  await (await settings()).set(key, value);
}

export interface KeyCheck { ok: boolean; message: string; at: number }

export interface Diagnostics {
  app_version: string; os: string; arch: string;
  cli: string | null; cli_error: string | null; cli_version: string | null;
  ffmpeg: string | null; ffprobe: string | null;
}
export const diagnostics = () => invoke<Diagnostics>('diagnostics');

export const REPO_URL = 'https://github.com/drzdez/podcastz';
export const DOCS = {
  gettingStarted: `${REPO_URL}/blob/main/docs/getting-started.md`,
  howItWorks: `${REPO_URL}/blob/main/docs/how-it-works.md`,
  skills: `${REPO_URL}/blob/main/plugin/README.md`,
  issues: `${REPO_URL}/issues`,
  releases: `${REPO_URL}/releases`,
};
export const setWorkspace = (workspace: string | null) => invoke('set_workspace', { workspace });
export const openSession = (workspace: string, focusOnly: boolean, continuePrevious: boolean, client?: string) =>
  invoke<string>('open_session', { workspace, focusOnly, continuePrevious, client: client ?? null });
