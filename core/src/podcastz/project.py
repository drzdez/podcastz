"""Podcast project folder: config, episodes, state, segment plan."""
import datetime
import hashlib
import io
import json
import os
import re
import shutil
from importlib import resources

from . import PodcastzError
from .pricing import PRICING, language, model_info, provider

EPISODE_RE = re.compile(r'^(\d\d)-.+\.md$')
COMMENT_RE = re.compile(r'<!--.*?-->', re.S)
SLUG_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
PROJECT_DIRS = ['sources', 'work', 'text', 'audio/samples', 'cache/tts', 'cache/norm', '.podcastz']
STAGES = ['interview', 'research', 'script', 'review', 'ready']
DEFAULT_AUDIO = {'loudnorm': 'I=-18:TP=-2:LRA=7', 'sample_rate': 44100, 'channels': 1, 'mp3_quality': 4}


def load_json(path):
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def data_home():
    """Folder where projects live by default: $PODCASTZ_HOME or ~/Podcasts."""
    return os.path.abspath(os.path.expanduser(os.environ.get('PODCASTZ_HOME') or '~/Podcasts'))


def resolve(ref):
    """A project path, a slug in the current workspace, or a slug inside data_home()."""
    path = ref
    if not os.path.isdir(ref):
        from .workspace import find  # local import: workspace imports this module
        ws = find()
        cand = os.path.join(ws.projects_dir, ref) if ws else None
        path = cand if cand and os.path.isdir(cand) else os.path.join(data_home(), ref)
    if not os.path.exists(os.path.join(path, 'podcast.json')):
        raise PodcastzError(f'Not a podcastz project (missing podcast.json): {path}')
    return os.path.abspath(path)


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Project:
    def __init__(self, ref):
        self.dir = resolve(ref)
        self.slug = os.path.basename(self.dir)
        self.cfg = load_json(self.path('podcast.json'))
        self.tts = self.cfg.get('tts') or {}
        self.lang = self.cfg.get('language')
        speakers = self.cfg.get('speakers') or []
        alt = '|'.join(re.escape(s) for s in speakers) or r'(?!x)x'
        self.line_re = re.compile(r'^\s*\**(' + alt + r')\**\s*:\s*(.*)$')

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def require_audio_config(self):
        """Language and TTS model must be set before estimating or generating."""
        if not self.lang:
            raise PodcastzError('podcast.json has no "language" yet (the AI session sets it after the interview)')
        if not self.tts.get('model'):
            raise PodcastzError('podcast.json has no "tts.model"')
        language(self.lang)
        model_info(self.tts['model'])

    # ----- episodes -----

    def episodes(self, only=None):
        d = self.path('text')
        eps = sorted(f for f in os.listdir(d) if EPISODE_RE.match(f)) if os.path.isdir(d) else []
        return [f for f in eps if f[:2] in only] if only else eps

    def lines(self, md):
        out = []
        for line in self.script(md):
            m = self.line_re.match(line)
            if m and m.group(2).strip():
                out.append((m.group(1), m.group(2).replace('*', '').strip()))
        return out

    def script(self, md):
        """Lines of a script with HTML comments (also multi-line) blanked out, line numbers kept."""
        with io.open(self.path('text', md), encoding='utf-8') as f:
            text = f.read()
        text = COMMENT_RE.sub(lambda m: '\n' * m.group(0).count('\n'), text)
        return [l + '\n' for l in text.split('\n')]

    def title(self, md):
        for line in self.script(md):
            if line.startswith('# '):
                return line[2:].strip()
        return md[:-3]

    def outline(self, md):
        """Chapters ("## Title" lines, not spoken) and replicas in script order.

        A chapter carries next_line, the 1-based index of the first replica after it.
        """
        items, n = [], 0
        for line in self.script(md):
            if line.startswith('## '):
                items.append({'type': 'chapter', 'title': line[3:].strip(), 'next_line': n + 1})
                continue
            m = self.line_re.match(line)
            if m and m.group(2).strip():
                n += 1
                items.append({'type': 'line', 'index': n, 'speaker': m.group(1)})
        return items

    def voice(self, ep, speaker):
        v = self.cfg.get('episodes', {}).get(ep, {}).get(speaker) or self.cfg.get('voices', {}).get(speaker)
        if not v:
            raise PodcastzError(f'No voice for {speaker} in episode {ep}: set podcast.json "voices" or "episodes"')
        return v

    def instructions(self, speaker):
        """OpenAI style instructions: common text + per-speaker addition."""
        t = self.tts
        return ' '.join(x for x in [t.get('instructions', ''), t.get('speaker_instructions', {}).get(speaker, '')] if x)

    def segment_key(self, voice, text, speaker):
        t = self.tts
        if provider(t['model']) == 'openai':
            parts = [text, voice, t['model'], t['output_format'], self.instructions(speaker)]
        else:
            parts = [text, voice, t['model'], t['output_format'], t['voice_settings']]
        raw = json.dumps(parts, ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]

    def plan(self, md):
        """[(speaker, text, voice, segment_path)] for one episode, in order."""
        base, ep = md[:-3], md[:2]
        res = []
        for who, txt in self.lines(md):
            v = self.voice(ep, who)
            res.append((who, txt, v, self.path('cache', 'tts', base, self.segment_key(v, txt, who) + '.mp3')))
        return res

    # ----- state (written by the AI session, read by the app) -----

    def state(self):
        p = self.path('state.json')
        return load_json(p) if os.path.exists(p) else {'stage': 'interview'}

    def set_state(self, stage=None, message=None, **extra):
        if stage and stage not in STAGES:
            raise PodcastzError(f'Unknown stage "{stage}". Stages: {", ".join(STAGES)}')
        s = self.state()
        if stage:
            s['stage'] = stage
        if message is not None:
            s['message'] = message
        s.update(extra)
        s['updated'] = now()
        save_json(self.path('state.json'), s)
        return s


def done(path):
    return os.path.exists(path) and os.path.getsize(path) > 1000


def default_tts(model, lang=None):
    info = model_info(model)
    if info['provider'] == 'openai':
        tts = {'provider': 'openai', 'model': model, 'output_format': 'mp3',
               'instructions': 'Speak natural, fluent language as a calm, friendly podcast speaker. '
                               'Read abbreviations the way native speakers say them.',
               'speaker_instructions': {}}
    else:
        tts = {'provider': info['provider'], 'model': model, 'output_format': 'mp3_44100_128',
               'voice_settings': {'stability': 0.5, 'similarity_boost': 0.75}, 'context_chars': 300}
    return tts


def default_voices(model, speakers):
    pool = PRICING['providers'][provider(model)].get('default_voices') or []
    return {s: (pool[i % len(pool)] if pool else None) for i, s in enumerate(speakers)}


def create(path, title=None, language_code=None, model=None, speakers=('MODERATOR', 'GUEST')):
    """Create a project folder from the template. Language may be left for the AI interview."""
    path = os.path.abspath(os.path.expanduser(path))
    slug = os.path.basename(path)
    if not SLUG_RE.match(slug):
        raise PodcastzError(f'Folder name must be lowercase kebab-case (e.g. "how-dns-works"), got "{slug}"')
    if os.path.exists(path) and os.listdir(path):
        raise PodcastzError(f'Folder already exists and is not empty: {path}')
    if language_code:
        language(language_code)
    model = model or PRICING['default_model']
    speakers = list(speakers)
    for sub in PROJECT_DIRS:
        os.makedirs(os.path.join(path, sub), exist_ok=True)
    tpl = resources.files('podcastz.templates').joinpath('project')
    for name in ('AGENTS.md', 'BRIEF.md'):
        with tpl.joinpath(name).open('rb') as src, open(os.path.join(path, name), 'wb') as dst:
            shutil.copyfileobj(src, dst)
    cfg = {
        'title': title or slug,
        'language': language_code,
        'speakers': speakers,
        'voices': default_voices(model, speakers),
        'episodes': {},
        'tts': default_tts(model, language_code),
        'audio': dict(DEFAULT_AUDIO),
        'publish_dir': None,
    }
    save_json(os.path.join(path, 'podcast.json'), cfg)
    save_json(os.path.join(path, 'state.json'),
              {'stage': 'interview', 'message': 'Project created; waiting for the interview', 'updated': now()})
    return Project(path)
