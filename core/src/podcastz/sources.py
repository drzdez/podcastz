"""sources/index.json: the curated list of a project's sources, shared by the AI session and the app."""
import os

from . import PodcastzError
from .project import load_json, now, save_json

STATUSES = ['proposed', 'approved', 'rejected']


def _path(p):
    return p.path('sources', 'index.json')


def load(p):
    path = _path(p)
    return load_json(path) if os.path.exists(path) else {'sources': []}


def items(p, status=None):
    return [s for s in load(p)['sources'] if not status or s.get('status') == status]


def add(p, title, origin, file=None, kind=None, status='proposed', by='session', note=None):
    if status not in STATUSES:
        raise PodcastzError(f'Unknown status "{status}". Statuses: {", ".join(STATUSES)}')
    if file and not os.path.exists(p.path('sources', file)):
        raise PodcastzError(f'sources/{file} does not exist (give the file name relative to sources/)')
    idx = load(p)
    for s in idx['sources']:
        if s.get('origin') == origin and s.get('file') == file:
            raise PodcastzError(f'Source already listed as {s["id"]}')
    n = max((int(s['id'][1:]) for s in idx['sources'] if s.get('id', '').startswith('s')), default=0) + 1
    entry = {'id': f's{n:03d}', 'title': title, 'origin': origin, 'file': file, 'kind': kind,
             'status': status, 'added_by': by, 'added': now(), 'note': note}
    idx['sources'].append({k: v for k, v in entry.items() if v is not None})
    os.makedirs(p.path('sources'), exist_ok=True)
    save_json(_path(p), idx)
    return entry


def set_status(p, sid, status=None, note=None):
    if status and status not in STATUSES:
        raise PodcastzError(f'Unknown status "{status}". Statuses: {", ".join(STATUSES)}')
    idx = load(p)
    for s in idx['sources']:
        if s['id'] == sid:
            if status:
                s['status'] = status
            if note is not None:
                s['note'] = note
            s['updated'] = now()
            save_json(_path(p), idx)
            return s
    raise PodcastzError(f'No source {sid}')
