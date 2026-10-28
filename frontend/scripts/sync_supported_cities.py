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
check = '--check' in sys.argv
args = [a for a in sys.argv[1:] if a != '--check']
ref = args[0] if args else json.loads(OUTPUT.read_text(encoding='utf-8'))['source']['commit']
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8')
commit = git('rev-parse', '--verify', ref + '^{commit}').strip()
source = git('show', commit + ':' + PATH)
tree = ast.parse(source)
assignments = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SUPPORTED_CITIES' for t in n.targets)]
assert len(assignments) == 1, 'Ambiguous mapping; review adapter changes.'
cities = ast.literal_eval(assignments[0].value)
assert len(cities) == 80, 'Supported set changed; team review required before updating.'
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_normalize_city_text', 'resolve_supported_city')]
assert len(functions) == 2
normalization = '\n'.join(ast.dump(n, include_attributes=False) for n in functions)
records = [{'name': name, 'country_code': c['country_code'], 'aliases': c['aliases']} for name, c in cities.items()]
assert all(isinstance(c['name'], str) and isinstance(c['country_code'], str) and isinstance(c['aliases'], list) for c in records)
result = {'source': {'path': PATH, 'commit': commit, 'normalization_sha256': hashlib.sha256(normalization.encode()).hexdigest()}, 'cities': records}
if OUTPUT.exists():
    previous = json.loads(OUTPUT.read_text(encoding='utf-8'))
    assert previous['source']['normalization_sha256'] == result['source']['normalization_sha256'], 'Normalization changed; review TypeScript implementation first.'
text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
if check:
    assert OUTPUT.read_text(encoding='utf-8') == text, 'City snapshot differs from authoritative mapping.'
    print('PASS: all 80 names, aliases, country codes and normalization provenance match.')
else:
    OUTPUT.write_text(text, encoding='utf-8')
    print('Derived 80 city records; no adapter code executed.')
