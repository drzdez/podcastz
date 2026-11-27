#!/usr/bin/env node
// Prints the CHANGELOG.md section of one version: the GitHub Release body (one source of release
// notes, the same text the app shows).
//   node scripts/release-notes.mjs 0.1.0      (a leading "v" is accepted)
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const version = (process.argv[2] ?? '').replace(/^v/, '');
const lines = readFileSync(join(root, 'CHANGELOG.md'), 'utf8').split(/\r?\n/);
const start = lines.findIndex((l) => l.startsWith(`## ${version} `) || l === `## ${version}`);
if (!version || start < 0) {
  console.error(`CHANGELOG.md has no section "## ${version} – <date>"`);
  process.exit(1);
}
const end = lines.findIndex((l, i) => i > start && l.startsWith('## '));
const body = lines.slice(start + 1, end < 0 ? undefined : end).join('\n').trim();
console.log(`${body}

**Install:** Windows \`.msi\` or \`-setup.exe\` (for all users; not code-signed, so Windows may warn about an unknown publisher: More info, Run anyway), macOS \`.dmg\`, Linux \`.AppImage\`, \`.deb\` or \`.rpm\`. Installed apps update themselves. Your AI session also needs the \`podcastz\` CLI and the Claude Code plugin: see [Getting started](https://github.com/drzdez/podcastz/blob/main/docs/getting-started.md).`);
