import io
import json
import os

import pytest

from podcastz import PodcastzError, secrets_store, sources
from podcastz import workspace as wsmod
from podcastz.cli import main
from podcastz.project import Project, create


@pytest.fixture
def ws(tmp_path):
    return wsmod.init(str(tmp_path / 'my-podcasts'), marketplace='drzdez/podcastz')


def test_init_workspace(ws):
    assert os.path.exists(ws.path(wsmod.MARKER))
    settings = json.load(open(ws.path('.claude', 'settings.json'), encoding='utf-8'))
    assert settings['enabledPlugins']['podcastz@podcastz'] is True
    assert settings['extraKnownMarketplaces']['podcastz']['source'] == {'source': 'github', 'repo': 'drzdez/podcastz'}
    assert open(ws.rt('.gitignore'), encoding='utf-8').read().strip().endswith('*')
    # init again keeps foreign settings
    json.dump({'permissions': {'allow': ['Bash(ls)']}}, open(ws.path('.claude', 'settings.json'), 'w'))
    wsmod.init(ws.dir, marketplace=ws.dir)
    settings = json.load(open(ws.path('.claude', 'settings.json'), encoding='utf-8'))
    assert settings['permissions'] == {'allow': ['Bash(ls)']}
    assert settings['extraKnownMarketplaces']['podcastz']['source']['source'] == 'directory'


def test_projects_and_slug_resolution(ws, monkeypatch):
    create(ws.path('how-dns-works'), language_code='en')
    assert ws.projects() == ['how-dns-works']
    monkeypatch.chdir(ws.dir)
    assert Project('how-dns-works').dir == ws.path('how-dns-works')
    assert ws.project_of(ws.path('how-dns-works', 'sources')) == 'how-dns-works'
    assert ws.project_of(ws.dir) is None


def test_hooks_report_session_and_requests(ws, monkeypatch, capsys):
    r = ws.add_request('Find a source on DNSSEC', project='how-dns-works')
    for event, state in (('session-start', 'idle'), ('prompt', 'busy'), ('stop', 'idle')):
        monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'session_id': 'abc', 'cwd': ws.dir})))
        assert main(['hook', event]) == 0
        assert ws.session()['state'] == state
    printed = capsys.readouterr().out
    assert r['id'] in printed and 'DNSSEC' in printed
    ws.finish_request(r['id'], 'added s001')
    assert ws.requests() == []
    events = [json.loads(l) for l in open(ws.rt('events.jsonl'), encoding='utf-8')]
    assert events[-1]['kind'] == 'session'


def test_hook_outside_workspace_is_silent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'cwd': str(tmp_path)})))
    assert main(['hook', 'prompt']) == 0
    assert capsys.readouterr().out == ''


def test_sources_index(ws):
    p = create(ws.path('how-dns-works'), language_code='en')
    with open(p.path('sources', 'rfc1034.md'), 'w', encoding='utf-8') as f:
        f.write('# RFC 1034\n')
    s = sources.add(p, 'RFC 1034', 'https://www.rfc-editor.org/rfc/rfc1034', file='rfc1034.md', kind='standard')
    assert s['id'] == 's001' and s['status'] == 'proposed'
    with pytest.raises(PodcastzError):
        sources.add(p, 'again', 'https://www.rfc-editor.org/rfc/rfc1034', file='rfc1034.md')
    with pytest.raises(PodcastzError):
        sources.add(p, 'missing file', 'x', file='nope.md')
    sources.set_status(p, 's001', 'approved', 'primary source')
    assert [x['id'] for x in sources.items(p, 'approved')] == ['s001']


def test_key_lookup_order(monkeypatch, fake_vault):
    # (1) PODCASTZ_<P>_API_KEY override, (2) stored key, (3) generic provider variable
    assert secrets_store.lookup('openai') == (None, None)
    monkeypatch.setenv('OPENAI_API_KEY', 'env-key')
    assert secrets_store.lookup('openai') == ('env-key', 'OPENAI_API_KEY')
    secrets_store.set_key('openai', '  stored-key \n')
    assert secrets_store.lookup('openai') == ('stored-key', 'store')  # a stale generic variable never wins
    monkeypatch.setenv('PODCASTZ_OPENAI_API_KEY', 'pz-key')
    assert secrets_store.lookup('openai') == ('pz-key', 'PODCASTZ_OPENAI_API_KEY')
    monkeypatch.delenv('PODCASTZ_OPENAI_API_KEY')
    assert secrets_store.delete_key('openai')
    assert secrets_store.source('openai') == 'OPENAI_API_KEY'
    with pytest.raises(PodcastzError):
        secrets_store.lookup('nope')


def test_key_values_never_printed(monkeypatch, capsys, fake_vault):
    key = 'sk-proj-' + 'A1b2C3d4' * 6  # looks like a real key
    secrets_store.set_key('openai', key)
    monkeypatch.setattr(secrets_store, 'verify', lambda p: (False, 'HTTP 401 (key from store)'))
    for args in (['key', 'status'], ['key', 'test', 'openai'], ['key', 'delete', 'openai']):
        main(['--json', *args])
        main(args)
    out = capsys.readouterr()
    assert key not in out.out + out.err
    assert 'sk-proj-' not in out.out + out.err


def test_key_set_reads_stdin_and_status_hides_value(monkeypatch, capsys, fake_vault):
    monkeypatch.setattr('sys.stdin', io.StringIO('secret-123\n'))
    assert main(['--json', 'key', 'set', 'elevenlabs']) == 0
    assert fake_vault.data[('podcastz', 'elevenlabs')] == 'secret-123'
    capsys.readouterr()
    assert main(['--json', 'key', 'status']) == 0
    printed = capsys.readouterr().out
    assert 'secret-123' not in printed
    status = json.loads(printed)
    assert {k['provider']: k['source'] for k in status['keys']}['elevenlabs'] == 'store'


def test_episodes_view_with_and_without_timings(ws, capsys):
    p = create(ws.path('how-dns-works'), language_code='en')
    with open(p.path('text', '01-dns.md'), 'w', encoding='utf-8') as f:
        f.write('# Episode 01 – DNS\n\n## Names\nMODERATOR: Hello there.\n<!-- note -->\nGUEST: Hi.\n'
                '## Records\nMODERATOR: A record maps a name.\n')
    assert main(['--json', 'episodes', p.dir]) == 0
    ep = json.loads(capsys.readouterr().out)['episodes'][0]
    assert ep['title'] == 'Episode 01 – DNS' and ep['audio'] is None
    assert [c['first_line'] for c in ep['chapters']] == [1, 3]
    assert [l['speaker'] for l in ep['lines']] == ['MODERATOR', 'GUEST', 'MODERATOR']

    os.makedirs(p.path('audio'), exist_ok=True)
    open(p.path('audio', '01-dns.mp3'), 'wb').close()
    manifest = {'duration': 6.0, 'lines': [{'speaker': 'MODERATOR', 'start': 0.0, 'end': 2.0},
                                           {'speaker': 'GUEST', 'start': 2.0, 'end': 3.0},
                                           {'speaker': 'MODERATOR', 'start': 3.0, 'end': 6.0}]}
    with open(p.path('audio', '01-dns.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f)
    main(['--json', 'episodes', p.dir, '-e', '01'])
    ep = json.loads(capsys.readouterr().out)['episodes'][0]
    assert ep['audio']['timed'] and ep['audio']['duration'] == 6.0
    assert [c['start'] for c in ep['chapters']] == [0.0, 3.0]
    assert ep['lines'][1]['start'] == 2.0

    manifest['lines'].pop()  # the script changed after the build: no timings, audio still playable
    with open(p.path('audio', '01-dns.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f)
    main(['--json', 'episodes', p.dir])
    ep = json.loads(capsys.readouterr().out)['episodes'][0]
    assert ep['audio'] and not ep['audio']['timed'] and 'start' not in ep['lines'][0]


def test_new_with_speakers_info_and_workspace_gitignore(ws, monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(ws.dir)
    assert main(['--json', 'new', 'quiet-hour', '--title', 'Quiet hour', '--language', 'en',
                 '--speakers', 'host, expert']) == 0
    capsys.readouterr()
    gi = open(os.path.join(ws.dir, '.gitignore'), encoding='utf-8').read()
    assert '*/audio/**/*.mp3' in gi and '*/cache/' in gi
    main(['--json', 'info', 'quiet-hour'])
    info = json.loads(capsys.readouterr().out)
    assert info['title'] == 'Quiet hour' and info['owner'] == 'own' and info['dir'].endswith('quiet-hour')
    outside = create(str(tmp_path / 'elsewhere' / 'side-project'))
    main(['--json', 'info', outside.dir])
    assert json.loads(capsys.readouterr().out)['slug'] == 'side-project'
    main(['--json', 'workspace', 'status'])
    st = json.loads(capsys.readouterr().out)
    assert st['projects_dir'] == ws.projects_dir and st['projects'][0]['dir'].endswith('quiet-hour')
    assert json.load(open(os.path.join(ws.dir, 'quiet-hour', 'podcast.json'), encoding='utf-8'))['speakers'] == ['HOST', 'EXPERT']


def test_handoff_and_open(tmp_path, monkeypatch, capsys):
    assert main(['handoff']) == 0
    text = capsys.readouterr().out
    assert 'podcastz new' in text and 'podcastz open' in text and 'SPEAKER: text' in text
    p = create(str(tmp_path / 'client-repo' / 'podcast' / 'dns-basics'))
    started = {}

    class FakePopen:
        def __init__(self, cmd, env=None, **kw):
            started['cmd'], started['env'] = cmd, env

    monkeypatch.setattr('subprocess.Popen', FakePopen)
    monkeypatch.setenv('PODCASTZ_APP', str(tmp_path / 'podcastz-app.exe'))
    monkeypatch.setenv('PODCASTZ_SPAWNED_BY_APP', '1')
    monkeypatch.chdir(p.dir)
    assert main(['--json', 'open']) == 0
    assert started['cmd'][-1] == p.dir and 'PODCASTZ_SPAWNED_BY_APP' not in started['env']
    monkeypatch.delenv('PODCASTZ_APP')
    monkeypatch.setattr('podcastz.cli.find_app', lambda: None)
    capsys.readouterr()
    assert main(['--json', 'open', p.dir]) == 2


def test_json_build_dry_run(ws, monkeypatch, capsys):
    p = create(ws.path('how-dns-works'), language_code='en')
    with open(p.path('text', '01-dns.md'), 'w', encoding='utf-8') as f:
        f.write('# Episode 01 – DNS\n\nMODERATOR: Hello there.\nGUEST: Hi.\n')
    assert main(['--json', 'build', p.dir, '--dry-run']) == 0
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan['event'] == 'plan' and plan['to_generate'] == len('Hello there.') + len('Hi.')
    monkeypatch.chdir(ws.dir)
    assert main(['--json', 'workspace', 'status']) == 0
    st = json.loads(capsys.readouterr().out)
    assert st['projects'][0]['slug'] == 'how-dns-works'
