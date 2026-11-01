"""TTS providers (OpenAI, ElevenLabs) and segment generation with progress callbacks."""
import json
import os
import time
import urllib.error
import urllib.request

from . import PodcastzError
from .pricing import PRICING, model_info, provider
from .project import done

ELEVENLABS_API = 'https://api.elevenlabs.io/v1'
OPENAI_SPEECH = 'https://api.openai.com/v1/audio/speech'


def api_key(prov):
    env = PRICING['providers'][prov]['api_key_env']
    key = os.environ.get(env)
    if not key:
        raise PodcastzError(f'{env} is not set')
    return key


def http(url, data=None, headers=None, timeout=180, retries=3):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode('utf-8', 'replace')[:300]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and a < retries - 1:
                time.sleep(5 * (a + 1))
                continue
            raise PodcastzError(f'TTS API HTTP {e.code}: {body}') from None
        except (urllib.error.URLError, TimeoutError) as e:
            if a < retries - 1:
                time.sleep(5)
                continue
            raise PodcastzError(f'TTS API unreachable: {e}') from None


def _elevenlabs(p, speaker, voice, text, prev, nxt):
    t, info = p.tts, model_info(p.tts['model'])
    payload = {'text': text, 'model_id': t['model'], 'voice_settings': t['voice_settings']}
    ctx = t.get('context_chars', 300)
    if ctx and info.get('supports_context', True):
        if prev:
            payload['previous_text'] = prev[-ctx:]
        if nxt:
            payload['next_text'] = nxt[:ctx]
    if info.get('supports_language_code'):
        payload['language_code'] = p.lang
    return http(f'{ELEVENLABS_API}/text-to-speech/{voice}?output_format={t["output_format"]}',
                data=json.dumps(payload).encode('utf-8'),
                headers={'xi-api-key': api_key('elevenlabs'), 'Content-Type': 'application/json'})


def _openai(p, speaker, voice, text, prev, nxt):
    t = p.tts
    payload = {'model': t['model'], 'voice': voice, 'input': text, 'response_format': t['output_format']}
    instr = p.instructions(speaker)
    if instr and model_info(t['model']).get('supports_instructions'):
        payload['instructions'] = instr
    return http(OPENAI_SPEECH, data=json.dumps(payload).encode('utf-8'),
                headers={'Authorization': 'Bearer ' + api_key('openai'), 'Content-Type': 'application/json'})


SYNTH = {'elevenlabs': _elevenlabs, 'openai': _openai}


def synthesize(p, speaker, voice, text, prev, nxt, out):
    audio = SYNTH[provider(p.tts['model'])](p, speaker, voice, text, prev, nxt)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + '.part', 'wb') as f:
        f.write(audio)
    os.replace(out + '.part', out)


def generate(p, plan, on_progress=None, should_stop=None):
    """Generate missing segments of one episode plan; returns characters sent.

    on_progress(index, total, chars_sent) is called after each line;
    should_stop() lets a caller (the app) cancel between lines.
    """
    sent = 0
    for i, (who, txt, voice, seg) in enumerate(plan):
        if should_stop and should_stop():
            break
        if not done(seg):
            prev = plan[i - 1][1] if i > 0 else ''
            nxt = plan[i + 1][1] if i < len(plan) - 1 else ''
            synthesize(p, who, voice, txt, prev, nxt, seg)
            sent += len(txt)
        if on_progress:
            on_progress(i + 1, len(plan), sent)
    return sent


def list_voices(prov, lang=None):
    if prov == 'openai':
        return [{'id': v, 'name': v, 'languages': ['any']} for v in PRICING['providers']['openai']['voices']]
    data = json.loads(http(f'{ELEVENLABS_API}/voices', headers={'xi-api-key': api_key('elevenlabs')}))
    res = []
    for v in data['voices']:
        labels = v.get('labels') or {}
        langs = {labels.get('language', '')} | {x.get('language', '') for x in v.get('verified_languages') or []}
        langs.discard('')
        if lang and lang not in langs:
            continue
        res.append({'id': v['voice_id'], 'name': v['name'], 'languages': sorted(langs),
                    'gender': labels.get('gender', '')})
    return res
