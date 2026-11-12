"""Workspace: a folder with podcast projects that the app opens and where the AI session runs.

Runtime files in <workspace>/.podcastz/ connect the app and the session:
  session.json        the AI session as reported by the plugin hooks
  app.json            present while the app runs (pid, version), written by the app
  events.jsonl        events from the session and the CLI for the app (one JSON object per line)
  requests/<id>.json  requests from the app to the session
"""
import json
import os
import secrets

from . import PodcastzError
from .project import load_json, now, save_json

MARKER = 'podcastz.workspace.json'
RUNTIME = '.podcastz'
DEFAULT_MARKETPLACE = 'drzdez/podcastz'


def find(start=None):
    """The workspace containing start (default: current directory), or None."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(d, MARKER)):
            return Workspace(d)
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def init(path, marketplace=DEFAULT_MARKETPLACE):
    """Create (or complete) a workspace: marker, runtime folder, project-scoped plugin settings."""
    path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.join(path, RUNTIME, 'requests'), exist_ok=True)
    marker = os.path.join(path, MARKER)
    if not os.path.exists(marker):
        save_json(marker, {'projects_dir': '.', 'created': now()})
    with open(os.path.join(path, RUNTIME, '.gitignore'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('# runtime files of podcastz (session, app, requests)\n*\n')
    settings_path = os.path.join(path, '.claude', 'settings.json')
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    settings = load_json(settings_path) if os.path.exists(settings_path) else {}
    if os.path.isdir(marketplace):
        source = {'source': 'directory', 'path': os.path.abspath(marketplace)}
    else:
        source = {'source': 'github', 'repo': marketplace}
    settings.setdefault('extraKnownMarketplaces', {})['podcastz'] = {'source': source}
    settings.setdefault('enabledPlugins', {})['podcastz@podcastz'] = True
    save_json(settings_path, settings)
    return Workspace(path)


class Workspace:
    def __init__(self, path):
        self.dir = os.path.abspath(path)
        self.cfg = load_json(os.path.join(self.dir, MARKER))

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def rt(self, *parts):
        return os.path.join(self.dir, RUNTIME, *parts)

    @property
    def projects_dir(self):
        return os.path.normpath(os.path.join(self.dir, self.cfg.get('projects_dir', '.')))

    def projects(self):
        d = self.projects_dir
        if not os.path.isdir(d):
            return []
        return sorted(n for n in os.listdir(d) if os.path.exists(os.path.join(d, n, 'podcast.json')))

    def project_of(self, path):
        """Slug of the project containing path, or None."""
        p = os.path.abspath(path)
        base = self.projects_dir
        rel = os.path.relpath(p, base)
        if rel.startswith('..'):
            return None
        slug = rel.split(os.sep)[0]
        return slug if slug in self.projects() else None

    # ----- session (written by plugin hooks) -----

    def session(self):
        p = self.rt('session.json')
        return load_json(p) if os.path.exists(p) else None

    def set_session(self, **fields):
        os.makedirs(self.rt(), exist_ok=True)
        s = self.session() or {}
        if fields.get('state') == 'started' or s.get('session_id') != fields.get('session_id', s.get('session_id')):
            s = {'started': now()}
        s.update({k: v for k, v in fields.items() if v is not None})
        s['updated'] = now()
        save_json(self.rt('session.json'), s)
        return s

    # ----- requests from the app to the session -----

    def requests(self, include_done=False):
        d = self.rt('requests')
        if not os.path.isdir(d):
            return []
        items = [load_json(os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith('.json')]
        return items if include_done else [r for r in items if r.get('status') == 'pending']

    def add_request(self, text, project=None, kind='task'):
        os.makedirs(self.rt('requests'), exist_ok=True)
        rid = now().replace(':', '').replace('-', '').replace('+0000', 'Z')[:15] + '-' + secrets.token_hex(2)
        r = {'id': rid, 'project': project, 'kind': kind, 'text': text, 'status': 'pending', 'created': now()}
        save_json(self.rt('requests', rid + '.json'), r)
        return r

    def finish_request(self, rid, result=None):
        p = self.rt('requests', rid + '.json')
        if not os.path.exists(p):
            raise PodcastzError(f'No request {rid}')
        r = load_json(p)
        r.update({'status': 'done', 'done': now(), 'result': result})
        save_json(p, r)
        return r

    # ----- the app: app.json while it runs; it watches events.jsonl -----

    def app(self):
        p = self.rt('app.json')
        return load_json(p) if os.path.exists(p) else None

    def emit(self, kind, message=None, project=None, **extra):
        """Append an event for the app (it watches the file; harmless when the app isn't running)."""
        os.makedirs(self.rt(), exist_ok=True)
        ev = {'time': now(), 'kind': kind, 'project': project, 'message': message, **extra}
        with open(self.rt('events.jsonl'), 'a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps({k: v for k, v in ev.items() if v is not None}, ensure_ascii=False) + '\n')
        return ev


def pending_requests_text(ws):
    """Context text for the session about requests waiting from the app."""
    reqs = ws.requests()
    if not reqs:
        return ''
    lines = ['podcastz: the user left requests in the podcastz app for this session. '
             'Handle them (ask the user if unclear) and mark each done with `podcastz request done <id> -m "<result>"`:']
    for r in reqs:
        where = f' [project {r["project"]}]' if r.get('project') else ''
        lines.append(f'- {r["id"]}{where}: {r["text"]}')
    return '\n'.join(lines)
