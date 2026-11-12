"""TTS API keys in the OS credential store.

Store: Python `keyring` (Windows Credential Manager, macOS Keychain, Linux Secret Service),
service "podcastz", user name = provider ("openai", "elevenlabs"); the desktop app writes the same entry.
Lookup order: (1) PODCASTZ_<PROVIDER>_API_KEY as an explicit override, (2) the stored key,
(3) the provider's generic variable (OPENAI_API_KEY, ...) as the last fallback, so a stale generic
variable never hides a key saved in Settings.
Key values only go in; callers outside this module see the source, never the value.
"""
import json
import os
import urllib.error
import urllib.request

from . import PodcastzError
from .pricing import PRICING

SERVICE = 'podcastz'
CHECK_URLS = {'openai': ('https://api.openai.com/v1/models', 'Authorization', 'Bearer {}'),
              'elevenlabs': ('https://api.elevenlabs.io/v1/models', 'xi-api-key', '{}')}


def providers():
    return list(PRICING['providers'])


def _keyring():
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:
        return None


def env_names(provider):
    return [f'PODCASTZ_{provider.upper()}_API_KEY', PRICING['providers'][provider]['api_key_env']]


def _check(provider):
    if provider not in PRICING['providers']:
        raise PodcastzError(f'Unknown provider "{provider}". Providers: {", ".join(providers())}')


def lookup(provider):
    """(key, source) where source is 'store', an environment variable name, or None."""
    _check(provider)
    override, generic = env_names(provider)
    if os.environ.get(override):
        return os.environ[override], override
    kr = _keyring()
    if kr:
        try:
            v = kr.get_password(SERVICE, provider)
        except Exception:
            v = None
        if v:
            return v, 'store'
    if os.environ.get(generic):
        return os.environ[generic], generic
    return None, None


def get(provider):
    key, _ = lookup(provider)
    if not key:
        raise PodcastzError(f'No API key for {provider}: run `podcastz key set {provider}` (or the app Settings), '
                            f'or set {" or ".join(env_names(provider))}')
    return key


def source(provider):
    return lookup(provider)[1]


def store_available():
    return _keyring() is not None


def set_key(provider, value):
    _check(provider)
    value = (value or '').strip()
    if not value:
        raise PodcastzError('Empty key')
    kr = _keyring()
    if not kr:
        raise PodcastzError('No OS credential store available; use the environment variables instead')
    kr.set_password(SERVICE, provider, value)


def delete_key(provider):
    _check(provider)
    kr = _keyring()
    if not kr:
        return False
    try:
        kr.delete_password(SERVICE, provider)
        return True
    except Exception:
        return False


def verify(provider):
    """Call a cheap read-only endpoint; returns (ok, message). Never includes the key."""
    key, src = lookup(provider)
    if not key:
        return False, 'no key'
    url, header, fmt = CHECK_URLS[provider]
    req = urllib.request.Request(url, headers={header: fmt.format(key)})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            json.loads(r.read() or b'{}')
            return True, f'valid (from {src})'
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code} (key from {src})'
    except (urllib.error.URLError, TimeoutError) as e:
        return False, f'unreachable: {e}'


def status():
    """Per provider: where the key comes from (no values)."""
    return [{'provider': p, 'source': source(p), 'env': env_names(p)} for p in providers()]
