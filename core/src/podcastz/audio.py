"""Loudness normalization, concatenation and probing via ffmpeg / ffprobe."""
import hashlib
import io
import os
import shutil
import subprocess
import wave

from . import PodcastzError
from .project import done, save_json


def _tool(name):
    exe = shutil.which(name)
    if not exe:
        raise PodcastzError(f'{name} not found on PATH (install ffmpeg)')
    return exe


def ffmpeg(*args):
    subprocess.run([_tool('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y', *args], check=True)


def duration(path):
    if not os.path.exists(path):
        return 0.0
    r = subprocess.run([_tool('ffprobe'), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def wav_seconds(path):
    with wave.open(path, 'rb') as w:
        return w.getnframes() / w.getframerate()


def normalized(p, segments):
    """Loudness-normalized WAV for each segment (cached under cache/norm)."""
    a = p.cfg['audio']
    tag = hashlib.sha1(f'{a["loudnorm"]}|{a["sample_rate"]}|{a["channels"]}'.encode()).hexdigest()[:6]
    wavs = []
    for seg in segments:
        norm_dir = p.path('cache', 'norm', os.path.basename(os.path.dirname(seg)))
        os.makedirs(norm_dir, exist_ok=True)
        wav = os.path.join(norm_dir, f'{os.path.basename(seg)[:-4]}-{tag}.wav')
        if not done(wav):
            ffmpeg('-i', seg, '-af', 'loudnorm=' + a['loudnorm'],
                   '-ar', str(a['sample_rate']), '-ac', str(a['channels']), wav)
        wavs.append(wav)
    return wavs


def mix(p, segments, out):
    """Loudness-normalize each segment (cached WAV), concat, encode MP3."""
    a = p.cfg['audio']
    wavs = normalized(p, segments)
    lst = p.path('cache', 'norm', 'concat.txt')
    with io.open(lst, 'w', encoding='utf-8', newline='\n') as f:
        for w in wavs:
            f.write("file '" + w.replace('\\', '/').replace("'", "'\\''") + "'\n")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ffmpeg('-f', 'concat', '-safe', '0', '-i', lst,
           '-codec:a', 'libmp3lame', '-q:a', str(a['mp3_quality']), '-ac', str(a['channels']), out)
    return out


def manifest(p, md, wavs):
    """Timing of every replica and chapter in the mixed episode (seconds from the start)."""
    lines, t = [], 0.0
    for (who, text, _, _), wav in zip(p.plan(md), wavs):
        d = wav_seconds(wav)
        lines.append({'index': len(lines) + 1, 'speaker': who, 'start': round(t, 2), 'end': round(t + d, 2),
                      'text': text})
        t += d
    chapters = []
    for item in p.outline(md):
        if item['type'] == 'chapter':
            start = lines[item['next_line'] - 1]['start'] if item['next_line'] <= len(lines) else round(t, 2)
            chapters.append({'title': item['title'], 'start': start, 'first_line': item['next_line']})
    return {'episode': md[:-3], 'title': p.title(md), 'duration': round(t, 2), 'chapters': chapters, 'lines': lines}


def mix_episode(p, md, out_dir=None):
    """Mix one episode from cached segments and write its timing manifest next to the MP3.

    Returns the MP3 path, or None if segments are missing.
    """
    plan = p.plan(md)
    if any(not done(seg) for *_, seg in plan):
        return None
    out = os.path.join(out_dir or p.path('audio'), md[:-3] + '.mp3')
    segments = [seg for *_, seg in plan]
    mix(p, segments, out)
    save_json(out[:-4] + '.json', manifest(p, md, normalized(p, segments)))
    return out
