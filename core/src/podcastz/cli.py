"""podcastz command line.

  podcastz languages                       languages, speech rate and cost per audio hour
  podcastz quote --language cs --hours 1   price for a planned length
  podcastz new <folder|slug> [--language cs] [--model M] [--title T]
  podcastz state <project> [stage] [-m message]
  podcastz check <project>                 validate scripts before audio (exit 1 on errors)
  podcastz estimate <project> [-e 01 02]   characters, minutes, cost (total / still to generate)
  podcastz voices [--provider openai|elevenlabs] [--language cs]
  podcastz sample <project> [-e 01] [--chars 1500] [--yes]
  podcastz build <project> [-e 01] [--dry-run] [--yes]
  podcastz mix <project> [-e 01] [--out DIR]
  podcastz publish <project>
  podcastz prune <project> [--yes]

A project is a folder path or a slug under $PODCASTZ_HOME (default ~/Podcasts).
"""
import argparse
import os
import shutil
import sys

from . import PodcastzError, __version__
from .audio import duration, mix, mix_episode
from .check import check_project
from .pricing import LANGS, PRICING, chars_per_hour, cost, cost_per_hour, fmt_hours, quote, rate_label
from .project import STAGES, Project, create, data_home, done
from .tts import generate, list_voices


def confirm(question, yes):
    if yes:
        return True
    if not sys.stdin.isatty():
        raise PodcastzError(question + ' - non-interactive, rerun with --yes')
    return input(question + ' [y/N] ').strip().lower() in ('y', 'yes', 'a', 'ano')


def cmd_languages(a):
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
    print(f'{q["hours"]:g} h in {LANGS[q["language"]]["name"]} with {q["model"]}: '
          f'~{q["chars"]:,} chars ~ ${q["usd"]:.2f} (${q["usd_per_hour"]:.2f}/h)')


def cmd_new(a):
    path = a.folder if (os.sep in a.folder or '/' in a.folder) else os.path.join(data_home(), a.folder)
    p = create(path, title=a.title, language_code=a.language, model=a.model)
    print(f'Created {p.dir}')
    print('Next: open your AI session in that folder (e.g. `claude`) and ask it to follow AGENTS.md,'
          ' or with the podcastz plugin run /podcastz:prepare.')


def cmd_state(a):
    p = Project(a.project)
    s = p.set_state(a.stage, a.message) if (a.stage or a.message is not None) else p.state()
    print(f'{s.get("stage")}: {s.get("message", "")}  ({s.get("updated", "-")})')


def cmd_check(a):
    issues = check_project(a.project)
    for i in issues:
        print(i)
    errors = sum(1 for i in issues if i.level == 'error')
    warnings = len(issues) - errors
    print(f'{errors} errors, {warnings} warnings')
    return 1 if errors else 0


def cmd_estimate(a):
    p = Project(a.project)
    p.require_audio_config()
    model, cph = p.tts['model'], chars_per_hour(p.lang, p.tts['model'])
    print(f'{p.slug} - {p.cfg["title"]}  [{p.lang}, {model}, {rate_label(model)}, {cph:,} chars/h]')
    print(f'{"episode":42}{"lines":>6}{"chars":>8}{"to gen":>8}{"est min":>9}{"audio min":>10}')
    tl = tc = tn = ta = 0
    for md in p.episodes(a.episode):
        plan = p.plan(md)
        chars = sum(len(t) for _, t, _, _ in plan)
        new = sum(len(t) for _, t, _, s in plan if not done(s))
        dur = duration(p.path('audio', md[:-3] + '.mp3')) / 60
        print(f'{md[:-3][:42]:42}{len(plan):>6}{chars:>8,}{new:>8,}{chars / cph * 60:>9.1f}'
              f'{(f"{dur:.1f}" if dur else "-"):>10}')
        tl, tc, tn, ta = tl + len(plan), tc + chars, tn + new, ta + dur
    print(f'{"TOTAL":42}{tl:>6}{tc:>8,}{tn:>8,}{tc / cph * 60:>9.1f}{(f"{ta:.1f}" if ta else "-"):>10}')
    print(f'Estimated audio {fmt_hours(tc / cph)}; full cost ${cost(tc, model, p.lang):.2f}; '
          f'to generate now {tn:,} chars = ${cost(tn, model, p.lang):.2f}; '
          f'rate ${cost_per_hour(model, p.lang):.2f} per audio hour')
    if ta:
        print(f'Measured on existing audio: {tc / (ta / 60):,.0f} chars/hour')


def cmd_voices(a):
    for v in list_voices(a.provider, a.language):
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
    out = mix(p, [s for *_, s in plan], p.path('audio', 'samples', f'sample-{md[:2]}.mp3'))
    d = duration(out)
    print(f'OK   {out}: {d / 60:.1f} min; measured {total / (d / 3600):,.0f} chars/hour '
          f'(languages.json {p.lang}: {chars_per_hour(p.lang, p.tts["model"]):,})')


def cmd_build(a):
    p = Project(a.project)
    p.require_audio_config()
    plans = {md: p.plan(md) for md in p.episodes(a.episode)}
    new = sum(len(t) for pl in plans.values() for _, t, _, s in pl if not done(s))
    model = p.tts['model']
    print(f'{len(plans)} episodes; {new:,} chars to generate ~ ${cost(new, model, p.lang):.2f} ({model})')
    if a.dry_run or (new and not confirm('Generate?', a.yes)):
        return
    sent = 0
    for md, plan in plans.items():
        try:
            sent += generate(p, plan, on_progress=lambda i, n, s: print(f'\r  {md[:-3]}: {i}/{n}', end=''))
            print()
        except PodcastzError as e:
            print(f'\nFAIL {md[:-3]}: {e}')
            continue
        out = mix_episode(p, md)
        print(f'OK   {md[:-3]}: {duration(out) / 60:.1f} min -> {out}')
    print(f'Characters sent: {sent:,} (~ ${cost(sent, model, p.lang):.2f})')


def cmd_mix(a):
    p = Project(a.project)
    for md in p.episodes(a.episode):
        out = mix_episode(p, md, a.out)
        print(f'OK   {md[:-3]} -> {out}' if out else f'SKIP {md[:-3]}: segments missing (run build)')


def cmd_publish(a):
    p = Project(a.project)
    target = p.cfg.get('publish_dir')
    if not target:
        raise PodcastzError('Set "publish_dir" in podcast.json')
    os.makedirs(target, exist_ok=True)
    for f in sorted(os.listdir(p.path('audio'))):
        src, dst = p.path('audio', f), os.path.join(target, f)
        if not f.endswith('.mp3'):
            continue
        if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src) \
                and os.path.getmtime(dst) >= os.path.getmtime(src):
            continue
        shutil.copy2(src, dst)
        print('copied', f)
    readme = p.path('text', 'README.md')
    if os.path.exists(readme):
        shutil.copy2(readme, os.path.join(target, 'README.md'))
    print('Published to', target)


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
    print(f'{len(stale)} unused cache files')
    if stale and confirm('Delete them? (TTS segments were paid for)', a.yes):
        for f in stale:
            os.remove(f)
        print('deleted')


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='podcastz', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--version', action='version', version=__version__)
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
    s.add_argument('folder', help='new project folder, or a slug created under $PODCASTZ_HOME')
    s.add_argument('--title')
    s.add_argument('--language', help='audio language (may be left for the AI interview)')
    s.add_argument('--model', help=f'TTS model (default {PRICING["default_model"]})')
    s = cmd('state', cmd_state)
    s.add_argument('stage', nargs='?', choices=STAGES)
    s.add_argument('-m', '--message')
    cmd('check', cmd_check)
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

    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except PodcastzError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
