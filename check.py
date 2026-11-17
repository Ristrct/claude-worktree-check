"""Compare Claude Code project hooks across existing Git worktrees."""

import argparse
from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys


SETTINGS_FILES = ('.claude/settings.json', '.claude/settings.local.json')


@dataclass
class HookSettings:
    events: dict[str, Counter[str]] = field(default_factory=dict)
    disabled: bool | None = None
    exists: bool = False


def git(directory: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', '-C', str(directory), *args], capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.decode('utf-8', errors='replace').strip() or 'Git command failed')
    return result.stdout.decode('utf-8', errors='surrogateescape')


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON object key')
        result[key] = value
    return result


def reject_constant(_: str) -> None:
    raise ValueError('nonstandard JSON numeric constant')


def read_hooks(path: Path) -> HookSettings:
    try:
        settings = json.loads(
            path.read_text(encoding='utf-8-sig'),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except FileNotFoundError:
        return HookSettings()
    except json.JSONDecodeError as error:
        raise ValueError(f'invalid JSON at line {error.lineno}, column {error.colno}') from error

    if not isinstance(settings, dict) or not isinstance(settings.get('hooks', {}), dict):
        raise ValueError('expected a settings object containing a hooks object')

    disabled = settings.get('disableAllHooks')
    if 'disableAllHooks' in settings and not isinstance(disabled, bool):
        raise ValueError('expected disableAllHooks to be true or false')

    events: dict[str, Counter[str]] = {}
    for event, groups in settings.get('hooks', {}).items():
        if not isinstance(groups, list):
            raise ValueError(f'expected a list of matcher groups for {event!r}')
        entries: Counter[str] = Counter()
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get('hooks'), list):
                raise ValueError(f'expected a matcher group with a hooks list for {event!r}')
            matcher = group.get('matcher', '')
            if not isinstance(matcher, str):
                raise ValueError(f'expected a string matcher for {event!r}')
            for hook in group['hooks']:
                if not isinstance(hook, dict):
                    raise ValueError(f'expected an object for a hook in {event!r}')
                entries[json.dumps([matcher, hook], sort_keys=True)] += 1
        if entries:
            events[event] = entries
    return HookSettings(events, disabled, exists=True)


def compare(base: Path, target: Path) -> tuple[list[str], list[str]]:
    findings, errors = [], []
    for name in SETTINGS_FILES:
        try:
            expected = read_hooks(base / name)
        except (ValueError, OSError) as error:
            errors.append(f'{base / name}: {error}')
            continue
        try:
            actual = read_hooks(target / name)
        except (ValueError, OSError) as error:
            errors.append(f'{target / name}: {error}')
            continue
        if expected.disabled != actual.disabled:
            findings.append(
                f'{name} | disableAllHooks: expected {json.dumps(expected.disabled)}, '
                f'found {json.dumps(actual.disabled)} (null means unset)'
            )
        for event in sorted(expected.events.keys() | actual.events.keys()):
            before = expected.events.get(event, Counter())
            after = actual.events.get(event, Counter())
            missing = sum((before - after).values())
            extra = sum((after - before).values())
            if missing or extra:
                findings.append(f'{name} | {event!r}: {missing} missing, {extra} different or additional')
        if (expected.events or expected.disabled is not None) and not actual.exists:
            findings.append(
                f'{name} is missing. Check whether it is tracked on that branch. '
                'For intentionally ignored files, review Claude Code’s .worktreeinclude instructions.'
            )
    return findings, errors


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--base', type=Path, default=Path.cwd(), help='Reference checkout (default: current checkout).')
    args = cli.parse_args()
    try:
        root = git(args.base, 'rev-parse', '--show-toplevel')
        base = Path(root.removesuffix('\r\n') if sys.platform == 'win32' and root.endswith('\r\n')
                    else root.removesuffix('\n')).resolve()
        listing = git(base, 'worktree', 'list', '--porcelain', '-z')
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 2
    compared, drift, errors = 0, False, set()
    for record in listing.split('\0\0'):
        path, *attributes = record.split('\0')
        if not path.startswith('worktree ') or 'bare' in attributes:
            continue
        target = Path(path.removeprefix('worktree ')).resolve()
        if target == base:
            continue
        if not target.is_dir() or any(item.split(' ', 1)[0] == 'prunable' for item in attributes):
            errors.add(f'{target}: registered worktree is unavailable')
            continue
        compared += 1
        findings, problems = compare(base, target)
        errors.update(problems)
        if findings:
            drift = True
            print(f'{target}')
            for finding in findings:
                print(f'  {finding}')
    for error in sorted(errors):
        print(error, file=sys.stderr)
    if errors or not compared:
        if not compared:
            print('No other available worktree to compare.', file=sys.stderr)
        return 2
    if not drift:
        print(f'Compared {compared} worktree(s). Project hook entries match {base}.')
    return int(drift)


if __name__ == '__main__':
    sys.exit(main())
