"""Derive public city suggestions without importing/executing the adapter.
Run from repo root: python frontend/scripts/sync_supported_cities.py [git-ref] [--check]
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'frontend/src/data/supportedCities/cities.json'
PATH = 'backend/app/adapters/travelmate.py'
NORMALIZATION_FUNCTIONS = ('_normalize_city_text', 'resolve_supported_city')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8')


def normalization_fingerprint(source):
    """Hash original UTF-8 function segments joined by one LF, not AST displays."""
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    tree = ast.parse(source)
    segments = []
    for name in NORMALIZATION_FUNCTIONS:
        functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        if len(functions) != 1 or not isinstance(functions[0], ast.FunctionDef):
            raise ValueError(f'Expected exactly one synchronous {name} function; review adapter changes.')
        if functions[0].decorator_list:
            raise ValueError(f'Decorated normalization function {name}; review adapter changes.')
        segments.append(ast.get_source_segment(source, functions[0]))
    return hashlib.sha256('\n'.join(segments).encode('utf-8')).hexdigest()


def snapshot_from_source(source, commit):
    tree = ast.parse(source)
    assignments = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SUPPORTED_CITIES' for t in n.targets)]
    if len(assignments) != 1:
        raise ValueError('Ambiguous mapping; review adapter changes.')
    cities = ast.literal_eval(assignments[0].value)
    if len(cities) != 80:
        raise ValueError('Supported set changed; team review required before updating.')
    records = [{'name': name, 'country_code': c['country_code'], 'aliases': c['aliases']} for name, c in cities.items()]
    if not all(isinstance(c['name'], str) and isinstance(c['country_code'], str) and isinstance(c['aliases'], list) for c in records):
        raise ValueError('Invalid city records; review adapter changes.')
    return {'source': {'path': PATH, 'commit': commit, 'normalization_sha256': normalization_fingerprint(source)}, 'cities': records}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    check = '--check' in argv
    args = [a for a in argv if a != '--check']
    ref = args[0] if args else json.loads(OUTPUT.read_text(encoding='utf-8'))['source']['commit']
    commit = git('rev-parse', '--verify', ref + '^{commit}').strip()
    result = snapshot_from_source(git('show', commit + ':' + PATH), commit)
    if OUTPUT.exists():
        previous = json.loads(OUTPUT.read_text(encoding='utf-8'))
        if previous['source']['normalization_sha256'] != result['source']['normalization_sha256']:
            raise ValueError('Normalization changed; review TypeScript implementation first.')
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if check:
        if OUTPUT.read_text(encoding='utf-8') != text:
            raise ValueError('City snapshot differs from authoritative mapping.')
        print('PASS: all 80 names, aliases, country codes and normalization provenance match.')
    else:
        OUTPUT.write_text(text, encoding='utf-8')
        print('Derived 80 city records; no adapter code executed.')


if __name__ == '__main__':
    main()
