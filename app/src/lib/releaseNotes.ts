// Release notes shipped with the app: CHANGELOG.md at the repository root, bundled at build time.
// A Rust test (lib.rs) checks that the current version has an entry.

import changelog from '../../../CHANGELOG.md?raw';
import { compareVersions } from './update';

export interface Release {
  version: string;
  /** YYYY-MM-DD, may be empty */
  date: string;
  items: string[];
}

/** Sections `## <version> – <date>` with their bullet points, newest first. */
export function parseChangelog(md: string): Release[] {
  const releases: Release[] = [];
  let current: Release | null = null;
  for (const raw of md.split(/\r?\n/)) {
    const head = raw.match(/^##\s+v?(\d+(?:\.\d+)*\S*)\s*(?:[–-]\s*(\S+))?/);
    if (head) {
      current = { version: head[1], date: head[2] ?? '', items: [] };
      releases.push(current);
      continue;
    }
    if (!current) continue;
    const item = raw.match(/^\s*[-*]\s+(.*)$/);
    if (item) current.items.push(item[1].trim());
    else if (raw.trim() && current.items.length) current.items[current.items.length - 1] += ' ' + raw.trim();
  }
  return releases.sort((a, b) => compareVersions(b.version, a.version));
}

/** Releases newer than the last one the user saw, up to the running one; only the running one after a fresh install. */
export function releasesSince(releases: Release[], seen: string | null | undefined, current: string): Release[] {
  return releases.filter((r) => compareVersions(r.version, current) <= 0 && (seen ? compareVersions(r.version, seen) > 0 : r.version === current));
}

export const RELEASES = parseChangelog(changelog);

/** Inline `code` in release notes, as safe HTML. */
export function itemHtml(text: string): string {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return esc.replace(/`([^`]+)`/g, '<code>$1</code>');
}
