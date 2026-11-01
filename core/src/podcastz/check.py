"""Validate a project before audio: script format, speakers, TTS-hostile text."""
import re
from dataclasses import dataclass

from .project import Project

URL_RE = re.compile(r'https?://|www\.', re.I)
MARKUP_RE = re.compile(r'[`#\[\]{}<>|_]|\*\*')
SYMBOL_RE = re.compile(r'[→←↔⇒§©®™•…/\\]')
LONG_NUMBER_RE = re.compile(r'\d{3,}')
MAX_LINE = 1500


@dataclass
class Issue:
    file: str
    line: int
    level: str  # error | warning
    message: str

    def __str__(self):
        return f'{self.file}:{self.line}: {self.level}: {self.message}'


def check_episode(p, md):
    issues = []
    add = lambda n, lvl, msg: issues.append(Issue(f'text/{md}', n, lvl, msg))
    rows = [l.rstrip('\n') for l in p.script(md)]  # HTML comments blanked, line numbers kept
    content = [(i + 1, l) for i, l in enumerate(rows) if l.strip()]
    if not content or not content[0][1].startswith('# '):
        add(1, 'error', 'first line must be the title: "# Episode NN – Title"')
    body = content[1:]
    if body and not p.line_re.match(body[0][1]):
        body = body[1:]  # optional meta line ("Part N of M | ~10 min")
    replicas, last = 0, None
    for n, line in body:
        if line.startswith('## '):
            if not line[3:].strip():
                add(n, 'error', 'empty chapter title')
            continue  # chapter marker: not spoken, used for the timing manifest
        m = p.line_re.match(line)
        if not m:
            label = line.split(':', 1)[0].strip('* ') if ':' in line else ''
            if label.isupper() and label:
                add(n, 'error', f'unknown speaker "{label}" (podcast.json speakers: {", ".join(p.cfg["speakers"])})')
            else:
                add(n, 'error', 'not a replica line "SPEAKER: text" (only "## Chapter" markers may sit between replicas)')
            continue
        who, text = m.group(1), m.group(2).strip()
        if not text:
            add(n, 'error', 'empty replica')
            continue
        replicas += 1
        if URL_RE.search(text):
            add(n, 'error', 'URL in a replica (TTS reads it literally)')
        if MARKUP_RE.search(text):
            add(n, 'warning', 'markup or special characters (` # [ ] { } < > | _ **)')
        if SYMBOL_RE.search(text):
            add(n, 'warning', 'symbol TTS may read badly (arrows, slash, §, …): write it as words')
        if LONG_NUMBER_RE.search(text):
            add(n, 'warning', 'number with 3+ digits: consider writing it as words for correct reading')
        if len(text) > MAX_LINE:
            add(n, 'warning', f'very long replica ({len(text)} chars): split it for a natural dialogue')
        if who == last:
            add(n, 'warning', f'{who} speaks twice in a row')
        last = who
    if replicas == 0:
        add(1, 'error', 'no replicas found')
    return issues


def check_project(ref):
    p = Project(ref) if not isinstance(ref, Project) else ref
    issues = []
    if not p.cfg.get('speakers'):
        issues.append(Issue('podcast.json', 1, 'error', 'no "speakers"'))
        return issues
    for key in ('language', 'tts'):
        if not p.cfg.get(key):
            issues.append(Issue('podcast.json', 1, 'error', f'missing "{key}"'))
    eps = p.episodes()
    if not eps:
        issues.append(Issue('text/', 0, 'error', 'no episode scripts (text/NN-slug.md)'))
    for md in eps:
        issues.extend(check_episode(p, md))
        for s in p.cfg['speakers']:
            if not (p.cfg.get('episodes', {}).get(md[:2], {}).get(s) or p.cfg.get('voices', {}).get(s)):
                issues.append(Issue('podcast.json', 1, 'error', f'no voice for {s} in episode {md[:2]}'))
    return issues
