import io
import json
import os
import shutil
import subprocess

import pytest

from podcastz import PodcastzError
from podcastz.check import check_project
from podcastz.cli import main
from podcastz.pricing import cost, quote
from podcastz.project import Project, create

GOOD = """# Episode 01 – How DNS works
Part 1 of 1 | Estimated length: ~2 min

MODERATOR: Welcome. Today we look at how a name turns into an address.
GUEST: Thanks. It starts with your computer asking a resolver.
MODERATOR: And who answers?
"""


def write(p, name, text):
    with io.open(p.path('text', name), 'w', encoding='utf-8') as f:
        f.write(text)


@pytest.fixture
def project(tmp_path):
    return create(str(tmp_path / 'how-dns-works'), language_code='en')


def test_create_layout(project):
    for name in ('podcast.json', 'state.json', 'AGENTS.md', 'BRIEF.md'):
        assert os.path.exists(project.path(name))
    cfg = json.load(open(project.path('podcast.json'), encoding='utf-8'))
    assert cfg['speakers'] == ['MODERATOR', 'GUEST']
    assert cfg['voices'] == {'MODERATOR': 'marin', 'GUEST': 'cedar'}
    assert project.state()['stage'] == 'interview'


def test_create_rejects_bad_slug(tmp_path):
    with pytest.raises(PodcastzError):
        create(str(tmp_path / 'Bad Name'))


def test_language_can_wait_for_interview(tmp_path):
    p = create(str(tmp_path / 'later'))
    assert p.lang is None
    with pytest.raises(PodcastzError):
        p.require_audio_config()


def test_check_passes_good_script(project):
    write(project, '01-dns.md', GOOD)
    assert [i for i in check_project(project) if i.level == 'error'] == []


def test_check_finds_errors(project):
    write(project, '01-dns.md', GOOD + '- a bullet\nHOST: unknown speaker\nGUEST: see https://example.org\n')
    msgs = [i.message for i in check_project(project) if i.level == 'error']
    assert any('not a replica' in m for m in msgs)
    assert any('unknown speaker' in m for m in msgs)
    assert any('URL' in m for m in msgs)


def test_plan_and_cache_key_stable(project):
    write(project, '01-dns.md', GOOD)
    plan = project.plan('01-dns.md')
    assert len(plan) == 3
    assert plan[0][2] == 'marin' and plan[1][2] == 'cedar'
    again = Project(project.dir).plan('01-dns.md')
    assert [r[3] for r in plan] == [r[3] for r in again]


def test_state_roundtrip(project):
    project.set_state('research', 'collecting sources')
    s = Project(project.dir).state()
    assert s['stage'] == 'research' and s['message'] == 'collecting sources'
    with pytest.raises(PodcastzError):
        project.set_state('nonsense')


def test_pricing():
    assert cost(1000, 'eleven_multilingual_v2', 'cs') == pytest.approx(0.10)
    q = quote('cs', 'gpt-4o-mini-tts', 1)
    assert q['usd'] == pytest.approx(0.90)


CHAPTERS = """# Episode 01 – How DNS works
Part 1 of 1

## Asking
MODERATOR: Where does it start?
GUEST: With a resolver.
## Answering
MODERATOR: And then?
"""


def test_chapters_pass_check_and_outline(project):
    write(project, '01-dns.md', CHAPTERS)
    assert [i for i in check_project(project) if i.level == 'error'] == []
    chapters = [i for i in project.outline('01-dns.md') if i['type'] == 'chapter']
    assert [(c['title'], c['next_line']) for c in chapters] == [('Asking', 1), ('Answering', 3)]
    assert project.title('01-dns.md') == 'Episode 01 – How DNS works'


def test_html_comments_are_ignored(project):
    text = GOOD.replace('Part 1 of 1 | Estimated length: ~2 min\n',
                        'Part 1 of 1 | Estimated length: ~2 min\n<!-- coverage:\n  q1, q2\nGUEST: not spoken -->\n')
    text += 'GUEST: Done. <!-- inline note --> Really.\n'
    write(project, '01-dns.md', text)
    assert [i for i in check_project(project) if i.level == 'error'] == []
    spoken = [t for _, t in project.lines('01-dns.md')]
    assert len(spoken) == 4 and 'not spoken' not in ' '.join(spoken)
    assert spoken[-1] == 'Done.  Really.'


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg not on PATH')
def test_manifest_timings(project):
    from podcastz.audio import mix_episode
    write(project, '01-dns.md', CHAPTERS)
    for seconds, (_, _, _, seg) in zip((1.0, 2.0, 1.5), project.plan('01-dns.md')):
        os.makedirs(os.path.dirname(seg), exist_ok=True)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                        'sine=frequency=440:sample_rate=44100', '-t', str(seconds), seg], check=True)
    out = mix_episode(project, '01-dns.md')
    m = json.load(open(out[:-4] + '.json', encoding='utf-8'))
    assert [l['start'] for l in m['lines']] == pytest.approx([0.0, 1.0, 3.0], abs=0.05)
    assert m['duration'] == pytest.approx(4.5, abs=0.05)
    assert [(c['title'], c['start']) for c in m['chapters']] == [('Asking', 0.0), ('Answering', pytest.approx(3.0, abs=0.05))]


def test_cli_check_exit_codes(project, capsys):
    write(project, '01-dns.md', GOOD)
    assert main(['check', project.dir]) == 0
    write(project, '02-bad.md', 'no title\n')
    assert main(['check', project.dir]) == 1
    assert main(['check', project.dir + '-missing']) == 2
