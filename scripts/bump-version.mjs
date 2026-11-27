#!/usr/bin/env node
// Sets one version in every file that carries it, so a release never ships mixed versions.
//   node scripts/bump-version.mjs 0.2.0
// Files: app/package.json (the source), app/package-lock.json (2 places), app/src-tauri/Cargo.toml,
// app/src-tauri/Cargo.lock, app/src-tauri/tauri.conf.json, core/pyproject.toml, core/src/podcastz/__init__.py.
// The Claude Code plugin keeps its own version (plugin/.claude-plugin/plugin.json).
// Afterwards add a "## <version> – <date>" section to CHANGELOG.md; `cargo test` checks both.
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const version = process.argv[2];
if (!/^\d+\.\d+\.\d+$/.test(version ?? '')) {
  console.error('usage: node scripts/bump-version.mjs MAJOR.MINOR.PATCH (MSI versions allow no pre-release text)');
  process.exit(2);
}

function edit(rel, fn) {
  const path = join(root, rel);
  const before = readFileSync(path, 'utf8');
  const after = fn(before);
  if (after === before) {
    if (!before.includes(version)) throw new Error(`${rel}: version field not found`);
    console.log(`${rel}: already ${version}`);
    return;
  }
  writeFileSync(path, after);
  console.log(`${rel}: ${version}`);
}

function json(rel, fn) {
  edit(rel, (text) => {
    const data = JSON.parse(text);
    fn(data);
    return JSON.stringify(data, null, 2) + (text.endsWith('\n') ? '\n' : '');
  });
}

json('app/package.json', (d) => { d.version = version; });
json('app/package-lock.json', (d) => { d.version = version; d.packages[''].version = version; });
json('app/src-tauri/tauri.conf.json', (d) => { d.version = version; });
edit('app/src-tauri/Cargo.toml', (t) => t.replace(/^(\[package\][\s\S]*?\nversion = ")[^"]+"/, `$1${version}"`));
edit('app/src-tauri/Cargo.lock', (t) => t.replace(/(\[\[package\]\]\nname = "podcastz-app"\nversion = ")[^"]+"/, `$1${version}"`));
edit('core/pyproject.toml', (t) => t.replace(/^(\[project\][\s\S]*?\nversion = ")[^"]+"/m, `$1${version}"`));
edit('core/src/podcastz/__init__.py', (t) => t.replace(/__version__ = '[^']+'/, `__version__ = '${version}'`));

const changelog = readFileSync(join(root, 'CHANGELOG.md'), 'utf8');
if (!changelog.split('\n').some((l) => l.startsWith(`## ${version} `))) {
  console.log(`\nNow add "## ${version} – ${new Date().toISOString().slice(0, 10)}" with the release notes to CHANGELOG.md.`);
}
