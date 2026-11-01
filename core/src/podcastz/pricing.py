"""Languages, TTS models and cost estimates (data in podcastz/data/*.json)."""
import json
from importlib import resources

from . import PodcastzError


def _load(name):
    with resources.files('podcastz.data').joinpath(name).open(encoding='utf-8') as f:
        return json.load(f)


LANGS = {k: v for k, v in _load('languages.json').items() if not k.startswith('_')}
PRICING = _load('pricing.json')


def model_info(model):
    m = PRICING['models'].get(model)
    if not m:
        raise PodcastzError(f'Unknown TTS model "{model}". Known: {", ".join(PRICING["models"])}')
    return m


def provider(model):
    return model_info(model)['provider']


def language(lang):
    if lang not in LANGS:
        raise PodcastzError(f'Unknown language "{lang}". Known: {", ".join(LANGS)}')
    return LANGS[lang]


def chars_per_hour(lang, model=None):
    L = language(lang)
    if model:
        return L.get('by_provider', {}).get(provider(model), L['chars_per_hour'])
    return L['chars_per_hour']


def cost(chars, model, lang):
    m = model_info(model)
    if 'usd_per_audio_minute' in m:
        return chars / chars_per_hour(lang, model) * 60 * m['usd_per_audio_minute']
    return chars / 1000 * m['usd_per_1k_chars']


def cost_per_hour(model, lang):
    return cost(chars_per_hour(lang, model), model, lang)


def rate_label(model):
    m = model_info(model)
    if 'usd_per_audio_minute' in m:
        return f'${m["usd_per_audio_minute"]:.3f}/audio min'
    return f'${m["usd_per_1k_chars"]:.3f}/1k chars'


def quote(lang, model, hours):
    """Estimate for a planned length: chars, cost, rate per hour."""
    cph = chars_per_hour(lang, model)
    chars = hours * cph
    return {'language': lang, 'model': model, 'hours': hours, 'chars': round(chars),
            'usd': round(cost(chars, model, lang), 2), 'usd_per_hour': round(cost(cph, model, lang), 2)}


def fmt_hours(hours):
    h, m = divmod(round(hours * 60), 60)
    return f'{h} h {m:02d} min'
