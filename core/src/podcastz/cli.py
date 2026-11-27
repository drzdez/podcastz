"""podcastz command line.

Projects
  podcastz new <folder|slug> [--language cs] [--model M] [--title T]
  podcastz state <project> [stage] [-m message]
  podcastz check <project>                 validate scripts before audio (exit 1 on errors)
  podcastz source list|add|set <project> ...   curated sources (sources/index.json)
Audio
  podcastz languages | quote --language cs --hours 1
  podcastz estimate <project> [-e 01 02]   characters, minutes, cost (total / still to generate)
  podcastz voices [--provider openai|elevenlabs] [--language cs]
  podcastz sample <project> [-e 01] [--chars 1500] [--yes]
  podcastz build <project> [-e 01] [--dry-run] [--yes]
  podcastz mix <project> [-e 01] [--out DIR] | publish <project> | prune <project> [--yes]
  podcastz key status | set <provider> | delete <provider> | test <provider>
Workspace, app and AI session
  podcastz workspace init <dir> [--marketplace drzdez/podcastz|<path>] | workspace status
  podcastz request list | add --text T [--project P] | done <id> [-m result]
  podcastz app status | notify <message> [--project P]
  podcastz hook <session-start|prompt|stop|session-end>   (called by the plugin hooks, JSON on stdin)

A project is a folder path, a slug in the current workspace, or a slug under $PODCASTZ_HOME (~/Podcasts).
`podcastz --json <command>` prints machine-readable output (JSON lines for build) for the app.
"""
import argparse
import getpass
import json
import os
import shutil
import sys

from . import PodcastzError, __version__, secrets_store, sources
from . import workspace as wsmod
from .audio import duration, mix, mix_episode
from .check import check_project
from .pricing import LANGS, PRICING, chars_per_hour, cost, cost_per_hour, fmt_hours, quote, rate_label
from .project import STAGES, Project, create, data_home, done, load_json
from .tts import generate, list_voices

JSON = False


def out(obj):
    """One JSON object per line in --json mode."""
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def say(text, obj=None):
    if JSON:
        if obj is not None:
            out(obj)
    else:
        print(text, flush=True)


def confirm(question, yes):
    if yes:
        return True
    if JSON or not sys.stdin.isatty():
        raise PodcastzError(question + ' - non-interactive, rerun with --yes')
    return input(question + ' [y/N] ').strip().lower() in ('y', 'yes', 'a', 'ano')


def emit(kind, project=None, message=None, **extra):
    """Tell the app about a change, if we are inside a workspace."""
    ws = wsmod.find(project.dir if isinstance(project, Project) else None)
    if ws:
        ws.emit(kind, message=message, project=project.slug if isinstance(project, Project) else project, **extra)


# ---------- prices ----------

def cmd_languages(a):
    if JSON:
        out({'languages': LANGS, 'models': PRICING['models'], 'as_of': PRICING['as_of'],
             'usd_per_hour': {m: {c: round(cost_per_hour(m, c), 2) for c in LANGS} for m in PRICING['models']}})
        return
    print('Audio languages (characters per audio hour):')
    for code, L in LANGS.items():
        basis = 'measured' if L['basis'].startswith('measured') else 'estimated'
        print(f'  {code:4}{L["name"]:24}{L["chars_per_hour"]:>8,}  {basis}')
    print(f'\nCost per audio hour, USD (prices as of {PRICING["as_of"]}):')
    print(f'  {"model":24}{"provider":12}' + ''.join(f'{c:>8}' for c in LANGS) + '  rate')
    for m, info in PRICING['models'].items():
        row = ''.join(f'{cost_per_hour(m, c):>8.2f}' for c in LANGS)
        print(f'  {m:24}{info["provider"]:12}{row}  {rate_label(m)}')


def cmd_quote(a):
    q = quote(a.language, a.model or PRICING['default_model'], a.hours)
    say(f'{q["hours"]:g} h in {LANGS[q["language"]]["name"]} with {q["model"]}: '
        f'~{q["chars"]:,} chars ~ ${q["usd"]:.2f} (${q["usd_per_hour"]:.2f}/h)', q)


# ---------- projects ----------

def cmd_new(a):
    if os.sep in a.folder or '/' in a.folder:
        path = a.folder
    else:
        ws = wsmod.find()
        path = os.path.join(ws.projects_dir if ws else data_home(), a.folder)
    speakers = [s.strip().upper() for s in a.speakers.split(',') if s.strip()] if a.speakers else None
    p = create(path, title=a.title, language_code=a.language, model=a.model, **({'speakers': speakers} if speakers else {}))
    emit('project', p, 'created')
    say(f'Created {p.dir}\nNext: open your AI session in the workspace or project folder and run /podcastz:prepare '
        f'(or ask it to follow AGENTS.md).', {'project': p.slug, 'dir': p.dir})


def cmd_state(a):
    p = Project(a.project)
    if a.stage or a.message is not None:
        s = p.set_state(a.stage, a.message)
        emit('state', p, s.get('message'), stage=s.get('stage'))
    else:
        s = p.state()
    say(f'{s.get("stage")}: {s.get("message", "")}  ({s.get("updated", "-")})', s)


def cmd_check(a):
    issues = check_project(a.project)
    errors = sum(1 for i in issues if i.level == 'error')
    if JSON:
        out({'errors': errors, 'warnings': len(issues) - errors,
             'issues': [i.__dict__ for i in issues]})
    else:
        for i in issues:
            print(i)
        print(f'{errors} errors, {len(issues) - errors} warnings')
    return 1 if errors else 0


def episode_view(p, md):
    """One episode for reading and listening: chapters, replicas, and the MP3 with replica and chapter
    times when the timing manifest written by build/mix still matches the script."""
    text_file = p.path('text', md)
    lines = [{'index': i + 1, 'speaker': who, 'text': text} for i, (who, text) in enumerate(p.lines(md))]
    chapters = [{'title': it['title'], 'first_line': it['next_line']}
                for it in p.outline(md) if it['type'] == 'chapter']
    view = {'episode': md[:-3], 'file': text_file, 'title': p.title(md), 'chapters': chapters,
            'lines': lines, 'audio': None}
    mp3 = p.path('audio', md[:-3] + '.mp3')
    if not os.path.isfile(mp3):
        return view
    audio = {'file': mp3, 'duration': None, 'timed': False,
             'changed_since': os.path.getmtime(text_file) > os.path.getmtime(mp3)}
    man_file = mp3[:-4] + '.json'
    man = load_json(man_file) if os.path.isfile(man_file) else None
    if man:
        audio['duration'] = man.get('duration')
        timed = man.get('lines') or []
        if len(timed) == len(lines) and all(t.get('speaker') == l['speaker'] for t, l in zip(timed, lines)):
            audio['timed'] = True
            for t, l in zip(timed, lines):
                l['start'], l['end'] = t['start'], t['end']
            for c in chapters:
                c['start'] = lines[c['first_line'] - 1]['start'] if c['first_line'] <= len(lines) else man.get('duration')
    view['audio'] = audio
    return view


def cmd_episodes(a):
    p = Project(a.project)
    eps = [episode_view(p, md) for md in p.episodes(a.episode)]
    if JSON:
        out({'project': p.slug, 'title': p.cfg.get('title'), 'episodes': eps})
        return
    for e in eps:
        au = e['audio']
        state = 'no audio' if not au else ('audio with timings' if au['timed'] else 'audio without matching timings')
        print(f'{e["episode"]}: {e["title"]} - {len(e["lines"])} lines, {len(e["chapters"])} chapters, {state}')


def cmd_source(a):
    p = Project(a.project)
    if a.action == 'list':
        items = sources.items(p, a.status)
        if JSON:
            out({'project': p.slug, 'sources': items})
            return
        for s in items:
            print(f'{s["id"]}  {s["status"]:9} {s["title"][:50]:50} {s.get("origin", "")}')
        print(f'{len(items)} sources')
    elif a.action == 'add':
        if not (a.title and a.origin):
            raise PodcastzError('source add needs --title and --origin')
        s = sources.add(p, a.title, a.origin, file=a.file, kind=a.kind, status=a.status or 'proposed',
                        by=a.by, note=a.note)
        emit('sources', p, f'{s["id"]} added: {s["title"]}')
        say(f'{s["id"]} {s["status"]}: {s["title"]}', s)
    else:
        if not a.id:
            raise PodcastzError('source set needs the source id')
        s = sources.set_status(p, a.id, a.status, a.note)
        emit('sources', p, f'{s["id"]} {s["status"]}')
        say(f'{s["id"]} {s["status"]}: {s["title"]}', s)


# ---------- audio ----------

def cmd_estimate(a):
    p = Project(a.project)
    p.require_audio_config()
    model, cph = p.tts['model'], chars_per_hour(p.lang, p.tts['model'])
    rows = []
    for md in p.episodes(a.episode):
        plan = p.plan(md)
        chars = sum(len(t) for _, t, _, _ in plan)
        new = sum(len(t) for _, t, _, s in plan if not done(s))
        rows.append({'episode': md[:-3], 'lines': len(plan), 'chars': chars, 'to_generate': new,
                     'est_min': round(chars / cph * 60, 1),
                     'audio_min': round(duration(p.path('audio', md[:-3] + '.mp3')) / 60, 1)})
    tc, tn = sum(r['chars'] for r in rows), sum(r['to_generate'] for r in rows)
    ta = sum(r['audio_min'] for r in rows)
    total = {'project': p.slug, 'title': p.cfg['title'], 'language': p.lang, 'model': model,
             'rate': rate_label(model), 'chars_per_hour': cph, 'episodes': rows, 'chars': tc, 'to_generate': tn,
             'est_hours': round(tc / cph, 3), 'usd_total': round(cost(tc, model, p.lang), 2),
             'usd_to_generate': round(cost(tn, model, p.lang), 2),
             'usd_per_hour': round(cost_per_hour(model, p.lang), 2), 'audio_min': round(ta, 1)}
    if JSON:
        out(total)
        return
    print(f'{p.slug} - {p.cfg["title"]}  [{p.lang}, {model}, {rate_label(model)}, {cph:,} chars/h]')
    print(f'{"episode":42}{"lines":>6}{"chars":>8}{"to gen":>8}{"est min":>9}{"audio min":>10}')
    for r in rows:
        print(f'{r["episode"][:42]:42}{r["lines"]:>6}{r["chars"]:>8,}{r["to_generate"]:>8,}{r["est_min"]:>9.1f}'
              f'{(str(r["audio_min"]) if r["audio_min"] else "-"):>10}')
    print(f'{"TOTAL":42}{sum(r["lines"] for r in rows):>6}{tc:>8,}{tn:>8,}{tc / cph * 60:>9.1f}'
          f'{(f"{ta:.1f}" if ta else "-"):>10}')
    print(f'Estimated audio {fmt_hours(tc / cph)}; full cost ${total["usd_total"]:.2f}; '
          f'to generate now {tn:,} chars = ${total["usd_to_generate"]:.2f}; '
          f'rate ${total["usd_per_hour"]:.2f} per audio hour')
    if ta:
        print(f'Measured on existing audio: {tc / (ta / 60):,.0f} chars/hour')


def cmd_voices(a):
    voices = list_voices(a.provider, a.language)
    if JSON:
        out({'provider': a.provider, 'voices': voices})
        return
    for v in voices:
        print(f'{v["id"]:24}  {v["name"][:40]:40}  {",".join(v["languages"]) or "-":12}  {v.get("gender", "")}')


def cmd_sample(a):
    p = Project(a.project)
    p.require_audio_config()
    eps = p.episodes(a.episode)
    if not eps:
        raise PodcastzError('No episode scripts in text/')
    md = eps[0]
    plan, total = [], 0
    for row in p.plan(md):
        if plan and total + len(row[1]) > a.chars:
            break
        plan.append(row)
        total += len(row[1])
    new = sum(len(t) for _, t, _, s in plan if not done(s))
    if new and not confirm(f'Sample {md[:-3]}: {len(plan)} lines, {new:,} new chars '
                           f'~ ${cost(new, p.tts["model"], p.lang):.2f}. Generate?', a.yes):
        return
    generate(p, plan)
    res = mix(p, [s for *_, s in plan], p.path('audio', 'samples', f'sample-{md[:2]}.mp3'))
    d = duration(res)
    measured = round(total / (d / 3600)) if d else None
    emit('audio', p, f'sample {md[:2]} ready')
    say(f'OK   {res}: {d / 60:.1f} min; measured {measured:,} chars/hour '
        f'(languages.json {p.lang}: {chars_per_hour(p.lang, p.tts["model"]):,})',
        {'event': 'sample', 'file': res, 'seconds': round(d, 2), 'chars_per_hour': measured})


def cmd_build(a):
    p = Project(a.project)
    p.require_audio_config()
    plans = {md: p.plan(md) for md in p.episodes(a.episode)}
    new = sum(len(t) for pl in plans.values() for _, t, _, s in pl if not done(s))
    model = p.tts['model']
    usd = round(cost(new, model, p.lang), 2)
    say(f'{len(plans)} episodes; {new:,} chars to generate ~ ${usd:.2f} ({model})',
        {'event': 'plan', 'episodes': len(plans), 'to_generate': new, 'usd': usd, 'model': model})
    if a.dry_run or (new and not confirm('Generate?', a.yes)):
        return
    sent, failed = 0, 0
    for md, plan in plans.items():
        ep = md[:-3]

        def progress(i, n, s, ep=ep):
            if JSON:
                out({'event': 'progress', 'episode': ep, 'line': i, 'lines': n, 'chars_sent': s})
            else:
                print(f'\r  {ep}: {i}/{n}', end='', flush=True)
        try:
            sent += generate(p, plan, on_progress=progress)
            if not JSON:
                print()
        except PodcastzError as e:
            failed += 1
            say(f'\nFAIL {ep}: {e}', {'event': 'error', 'episode': ep, 'message': str(e)})
            continue
        res = mix_episode(p, md)
        d = duration(res)
        say(f'OK   {ep}: {d / 60:.1f} min -> {res}',
            {'event': 'episode', 'episode': ep, 'file': res, 'seconds': round(d, 2)})
    spent = round(cost(sent, model, p.lang), 2)
    emit('audio', p, f'build finished: {len(plans) - failed} episodes, ~${spent:.2f}')
    say(f'Characters sent: {sent:,} (~ ${spent:.2f})',
        {'event': 'done', 'chars_sent': sent, 'usd': spent, 'failed': failed})
    return 1 if failed else 0


def cmd_mix(a):
    p = Project(a.project)
    for md in p.episodes(a.episode):
        res = mix_episode(p, md, a.out)
        say(f'OK   {md[:-3]} -> {res}' if res else f'SKIP {md[:-3]}: segments missing (run build)',
            {'event': 'episode', 'episode': md[:-3], 'file': res})


def cmd_publish(a):
    p = Project(a.project)
    target = p.cfg.get('publish_dir')
    if not target:
        raise PodcastzError('Set "publish_dir" in podcast.json')
    os.makedirs(target, exist_ok=True)
    copied = []
    for f in sorted(os.listdir(p.path('audio'))):
        src, dst = p.path('audio', f), os.path.join(target, f)
        if not f.endswith('.mp3'):
            continue
        if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src) \
                and os.path.getmtime(dst) >= os.path.getmtime(src):
            continue
        shutil.copy2(src, dst)
        copied.append(f)
    readme = p.path('text', 'README.md')
    if os.path.exists(readme):
        shutil.copy2(readme, os.path.join(target, 'README.md'))
    emit('audio', p, f'published {len(copied)} files')
    say('\n'.join([f'copied {f}' for f in copied] + [f'Published to {target}']),
        {'event': 'published', 'target': target, 'copied': copied})


def cmd_prune(a):
    p = Project(a.project)
    used = {os.path.normcase(s) for md in p.episodes() for *_, s in p.plan(md)}
    stale = []
    for sub in ('tts', 'norm'):
        for dp, _, files in os.walk(p.path('cache', sub)):
            for f in files:
                if f == 'concat.txt':
                    continue
                key = f.rsplit('-', 1)[0] if sub == 'norm' else f[:-4]
                seg = os.path.join(p.path('cache', 'tts', os.path.basename(dp)), key + '.mp3')
                if os.path.normcase(seg) not in used:
                    stale.append(os.path.join(dp, f))
    say(f'{len(stale)} unused cache files', {'unused': len(stale)})
    if stale and confirm('Delete them? (TTS segments were paid for)', a.yes):
        for f in stale:
            os.remove(f)
        say('deleted', {'deleted': len(stale)})


# ---------- keys ----------

def cmd_key(a):
    if a.action == 'status':
        st = secrets_store.status()
        if JSON:
            out({'store': secrets_store.store_available(), 'keys': st})
            return
        print(f'OS credential store: {"available" if secrets_store.store_available() else "not available"}')
        for s in st:
            print(f'  {s["provider"]:12} {s["source"] or "missing":28} (env: {", ".join(s["env"])})')
        return
    if not a.provider:
        raise PodcastzError(f'key {a.action} needs a provider: {", ".join(secrets_store.providers())}')
    if a.action == 'set':
        # The value is read from stdin, never from the command line (it would show in process lists).
        value = getpass.getpass(f'{a.provider} API key: ') if sys.stdin.isatty() else sys.stdin.readline()
        secrets_store.set_key(a.provider, value)
        say(f'{a.provider}: stored in the OS credential store', {'provider': a.provider, 'source': 'store'})
    elif a.action == 'delete':
        ok = secrets_store.delete_key(a.provider)
        say(f'{a.provider}: {"deleted" if ok else "nothing stored"}', {'provider': a.provider, 'deleted': ok})
    elif a.action == 'test':
        ok, msg = secrets_store.verify(a.provider)
        say(f'{a.provider}: {msg}', {'provider': a.provider, 'ok': ok, 'message': msg})
        return 0 if ok else 1


# ---------- workspace, requests, app, hooks ----------

def need_ws():
    ws = wsmod.find()
    if not ws:
        raise PodcastzError(f'Not inside a podcastz workspace (no {wsmod.MARKER} here or above); '
                            f'create one with `podcastz workspace init <dir>`')
    return ws


def project_summary(p):
    """What the app lists for a project: title, language, stage, episodes, sources, folder."""
    return {'slug': p.slug, 'dir': p.dir, 'title': p.cfg.get('title'), 'language': p.lang, 'state': p.state(),
            'episodes': len(p.episodes()), 'owner': p.cfg.get('owner', {}).get('kind', 'own'),
            'sources': {st: len(sources.items(p, st)) for st in sources.STATUSES}}


def cmd_info(a):
    """Summary of one project by path or slug (also for project folders outside any workspace)."""
    s = project_summary(Project(a.project))
    say(f'{s["slug"]}: {s["title"]} ({s["language"] or "language not set"}), stage {s["state"].get("stage")}, '
        f'{s["episodes"]} episodes - {s["dir"]}', s)


def handoff_text():
    from importlib import resources
    return resources.files('podcastz.templates').joinpath('handoff.md').read_text(encoding='utf-8')


def cmd_handoff(a):
    """Instructions for another AI session that wants podcasts made in its own repository."""
    text = handoff_text()
    if JSON:
        out({'text': text})
    else:
        print(text)


def find_app():
    """The installed desktop app, or None."""
    if os.environ.get('PODCASTZ_APP'):
        return os.environ['PODCASTZ_APP']
    if sys.platform == 'win32':
        for base in (os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA') and
                     os.path.join(os.environ['LOCALAPPDATA'], 'Programs')):
            if base:
                exe = os.path.join(base, 'podcastz', 'podcastz-app.exe')
                if os.path.isfile(exe):
                    return exe
        return None
    if sys.platform == 'darwin':
        return '/Applications/podcastz.app' if os.path.isdir('/Applications/podcastz.app') else None
    return shutil.which('podcastz-app')


def cmd_open(a):
    """Open a podcast folder in the desktop app (starts it, or brings the running app to that podcast)."""
    import subprocess
    p = Project(a.project or os.getcwd())
    app = find_app()
    if not app:
        raise PodcastzError('The podcastz app is not installed (https://github.com/drzdez/podcastz/releases); '
                            'set PODCASTZ_APP to its executable if it lives elsewhere')
    env = {k: v for k, v in os.environ.items() if k != 'PODCASTZ_SPAWNED_BY_APP'}  # the app refuses that marker
    if sys.platform == 'darwin':
        cmd = ['open', '-a', app, '--args', p.dir]
    else:
        cmd = [app, p.dir]
    kwargs = {'creationflags': 0x00000008 | 0x00000200} if sys.platform == 'win32' else {'start_new_session': True}
    subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     **kwargs)
    say(f'Opened {p.dir} in the podcastz app', {'opened': p.dir, 'app': app})


def cmd_workspace(a):
    if a.action == 'init':
        ws = wsmod.init(a.dir or os.getcwd(), a.marketplace)
        say(f'Workspace ready: {ws.dir}\n'
            f'- {wsmod.MARKER}, .podcastz/ (gitignored runtime files), .claude/settings.json enables the podcastz plugin\n'
            f'- start your AI session here (e.g. `claude`), trust the folder and accept the plugin, then /podcastz:prepare',
            {'workspace': ws.dir})
        return
    ws = need_ws()
    projects = [project_summary(Project(os.path.join(ws.projects_dir, slug))) for slug in ws.projects()]
    st = {'workspace': ws.dir, 'projects_dir': ws.projects_dir, 'projects': projects, 'session': ws.session(), 'app': ws.app(),
          'requests': ws.requests()}
    if JSON:
        out(st)
        return
    print(f'Workspace {ws.dir}')
    s = st['session']
    print(f'AI session: {s["state"] + " (" + s.get("updated", "") + ")" if s else "none reported"}')
    for pr in projects:
        print(f'  {pr["slug"]:30} {pr["state"].get("stage", "-"):10} {pr["episodes"]} ep, '
              f'sources {pr["sources"]["approved"]} approved / {pr["sources"]["proposed"]} proposed')
    if st['requests']:
        print(f'{len(st["requests"])} pending requests for the session')


def cmd_request(a):
    ws = need_ws()
    if a.action == 'list':
        items = ws.requests(include_done=a.all)
        if JSON:
            out({'requests': items})
            return
        for r in items:
            print(f'{r["id"]}  {r["status"]:8} {r.get("project") or "-":20} {r["text"]}')
        return
    if a.action == 'add':
        if not a.text:
            raise PodcastzError('request add needs --text')
        r = ws.add_request(a.text, project=a.project, kind=a.kind)
        ws.emit('request', r['text'], r.get('project'), id=r['id'])
        say(f'{r["id"]} pending', r)
    else:
        if not a.id:
            raise PodcastzError('request done needs the request id')
        r = ws.finish_request(a.id, a.message)
        ws.emit('request', a.message, r.get('project'), id=r['id'], status='done')
        say(f'{r["id"]} done', r)


def cmd_app(a):
    ws = need_ws()
    if a.action == 'status':
        app = ws.app()
        say(f'app: {"running (pid " + str(app.get("pid")) + ")" if app else "not running"}', {'app': app})
    else:
        ws.emit('notify', a.message, a.project)
        say('sent', {'sent': True})


def cmd_hook(a):
    """Plugin hooks: report the session to the workspace; give it pending requests. Never fails."""
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ''
        data = json.loads(raw) if raw.strip() else {}
        ws = wsmod.find(data.get('cwd'))
        if not ws:
            return 0
        state = {'session-start': 'idle', 'prompt': 'busy', 'stop': 'idle', 'session-end': 'ended'}[a.event]
        ws.set_session(session_id=data.get('session_id'), client='claude-code', state=state,
                       cwd=data.get('cwd'), transcript=data.get('transcript_path'),
                       project=ws.project_of(data.get('cwd') or ws.dir))
        ws.emit('session', state)
        if a.event in ('session-start', 'prompt'):
            text = wsmod.pending_requests_text(ws)
            if text:
                print(text)
    except Exception as e:  # a hook must never break the user's session
        print(f'podcastz hook: {e}', file=sys.stderr)
    return 0


# ---------- main ----------

def main(argv=None):
    global JSON
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='podcastz', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', action='version', version=__version__)
    ap.add_argument('--json', action='store_true', help='machine-readable output (JSON lines)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def cmd(name, fn, project=True, episodes=False):
        s = sub.add_parser(name)
        s.set_defaults(fn=fn)
        if project:
            s.add_argument('project', help='project folder or slug')
        if episodes:
            s.add_argument('-e', '--episode', nargs='+', metavar='NN', help='only these episodes (01 02 ...)')
        return s

    cmd('languages', cmd_languages, project=False)
    s = cmd('quote', cmd_quote, project=False)
    s.add_argument('--language', required=True)
    s.add_argument('--hours', type=float, required=True)
    s.add_argument('--model')
    s = cmd('new', cmd_new, project=False)
    s.add_argument('folder', help='new project folder, or a slug in the workspace / $PODCASTZ_HOME')
    s.add_argument('--title')
    s.add_argument('--language', help='audio language (may be left for the AI interview)')
    s.add_argument('--model', help=f'TTS model (default {PRICING["default_model"]})')
    s.add_argument('--speakers', help='comma-separated speaker names (default MODERATOR,GUEST)')
    cmd('info', cmd_info)
    cmd('handoff', cmd_handoff, project=False)
    s = cmd('open', cmd_open, project=False)
    s.add_argument('project', nargs='?', help='podcast folder (default: the current folder)')
    s = cmd('state', cmd_state)
    s.add_argument('stage', nargs='?', choices=STAGES)
    s.add_argument('-m', '--message')
    cmd('check', cmd_check)
    cmd('episodes', cmd_episodes, episodes=True)
    s = cmd('source', cmd_source, project=False)
    s.add_argument('action', choices=['list', 'add', 'set'])
    s.add_argument('project')
    s.add_argument('id', nargs='?')
    s.add_argument('--title')
    s.add_argument('--origin', help='URL, document reference or path of the original')
    s.add_argument('--file', help='file in sources/ holding the extracted text')
    s.add_argument('--kind', help='e.g. web, standard, paper, book, user-file')
    s.add_argument('--status', choices=sources.STATUSES)
    s.add_argument('--by', default='session', choices=['session', 'user'])
    s.add_argument('--note')
    cmd('estimate', cmd_estimate, episodes=True)
    s = cmd('voices', cmd_voices, project=False)
    s.add_argument('--provider', default='openai', choices=list(PRICING['providers']))
    s.add_argument('--language')
    s = cmd('sample', cmd_sample, episodes=True)
    s.add_argument('--chars', type=int, default=1500)
    s.add_argument('--yes', action='store_true')
    s = cmd('build', cmd_build, episodes=True)
    s.add_argument('--dry-run', action='store_true')
    s.add_argument('--yes', action='store_true', help='do not ask before spending credits')
    s = cmd('mix', cmd_mix, episodes=True)
    s.add_argument('--out', help='output directory instead of audio/')
    cmd('publish', cmd_publish)
    s = cmd('prune', cmd_prune)
    s.add_argument('--yes', action='store_true')
    s = cmd('key', cmd_key, project=False)
    s.add_argument('action', choices=['status', 'set', 'delete', 'test'])
    s.add_argument('provider', nargs='?')
    s = cmd('workspace', cmd_workspace, project=False)
    s.add_argument('action', choices=['init', 'status'])
    s.add_argument('dir', nargs='?')
    s.add_argument('--marketplace', default=wsmod.DEFAULT_MARKETPLACE,
                   help='plugin marketplace: GitHub owner/repo or a local path')
    s = cmd('request', cmd_request, project=False)
    s.add_argument('action', choices=['list', 'add', 'done'])
    s.add_argument('id', nargs='?')
    s.add_argument('--text')
    s.add_argument('--project')
    s.add_argument('--kind', default='task')
    s.add_argument('-m', '--message')
    s.add_argument('--all', action='store_true')
    s = cmd('app', cmd_app, project=False)
    s.add_argument('action', choices=['status', 'notify'])
    s.add_argument('message', nargs='?')
    s.add_argument('--project')
    s = cmd('hook', cmd_hook, project=False)
    s.add_argument('event', choices=['session-start', 'prompt', 'stop', 'session-end'])

    a = ap.parse_args(argv)
    JSON = a.json
    try:
        return a.fn(a) or 0
    except PodcastzError as e:
        if JSON:
            out({'event': 'error', 'message': str(e)})
        else:
            print(f'error: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
