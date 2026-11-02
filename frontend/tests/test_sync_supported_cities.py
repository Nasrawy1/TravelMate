"""Static city-sync regressions; run with both supported Python interpreters."""
import ast
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('city_sync', ROOT / 'frontend/scripts/sync_supported_cities.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
EXPECTED_DIGEST = 'd9fcad511d660eb2fba62b6c9929419b5cd2a1dfc28a607eed9cf75d6450b80e'


class SupportedCitySyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(sync.OUTPUT.read_text(encoding='utf-8'))
        cls.commit = cls.snapshot['source']['commit']
        cls.source = subprocess.check_output(
            ['git', 'show', cls.commit + ':' + sync.PATH], cwd=ROOT,
        ).decode('utf-8')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'cities.json'
        self.output.write_text(json.dumps(self.snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def check_source(self, source):
        before = self.output.read_bytes()
        modified = self.output.stat().st_mtime_ns

        def git(*args):
            if args == ('rev-parse', '--verify', self.commit + '^{commit}'):
                return self.commit + '\n'
            self.assertEqual(args, ('show', self.commit + ':' + sync.PATH))
            return source

        try:
            with patch.object(sync, 'OUTPUT', self.output), patch.object(sync, 'git', side_effect=git), \
                    patch.object(Path, 'write_text', side_effect=AssertionError('--check attempted a write')), \
                    redirect_stdout(io.StringIO()):
                sync.main(['--check'])
        finally:
            self.assertEqual(self.output.read_bytes(), before)
            self.assertEqual(self.output.stat().st_mtime_ns, modified)

    def test_pinned_source_has_same_golden_digest_on_each_python_version(self):
        self.assertEqual(sync.normalization_fingerprint(self.source), EXPECTED_DIGEST)
        self.assertEqual(sync.snapshot_from_source(self.source, self.commit), self.snapshot)

    def test_lf_crlf_and_cr_have_identical_fingerprints_and_pass_check(self):
        lf = self.source.replace('\r\n', '\n').replace('\r', '\n')
        for ending in ('\n', '\r\n', '\r'):
            with self.subTest(ending=repr(ending)):
                source = lf.replace('\n', ending)
                self.assertEqual(sync.normalization_fingerprint(source), EXPECTED_DIGEST)
                self.check_source(source)

    def test_real_normalization_change_fails_check_without_writing(self):
        function = next(n for n in ast.parse(self.source).body
                        if isinstance(n, ast.FunctionDef) and n.name == '_normalize_city_text')
        original = ast.get_source_segment(self.source, function)
        source = self.source.replace(original, original.replace('.strip().lower()', '.strip().upper()', 1), 1)
        self.assertNotEqual(source, self.source)
        with self.assertRaisesRegex(ValueError, 'Normalization changed'):
            self.check_source(source)

    def test_changes_to_resolver_also_fail_check(self):
        source = self.source.replace('return label, city', 'return None, None', 1)
        self.assertNotEqual(source, self.source)
        with self.assertRaisesRegex(ValueError, 'Normalization changed'):
            self.check_source(source)

    def test_decorators_are_rejected_for_each_function(self):
        for name in sync.NORMALIZATION_FUNCTIONS:
            with self.subTest(name=name):
                source = self.source.replace(f'def {name}(', f'@staticmethod\ndef {name}(', 1)
                with self.assertRaisesRegex(ValueError, 'Decorated normalization function'):
                    self.check_source(source)

    def test_missing_functions_are_rejected(self):
        for name in sync.NORMALIZATION_FUNCTIONS:
            with self.subTest(name=name):
                source = self.source.replace(f'def {name}(', f'def removed_{name}(', 1)
                with self.assertRaisesRegex(ValueError, 'Expected exactly one synchronous'):
                    self.check_source(source)

    def test_duplicate_functions_are_rejected_even_if_total_count_is_two(self):
        source = self.source.replace('def resolve_supported_city(', 'def _normalize_city_text(', 1)
        with self.assertRaisesRegex(ValueError, 'Expected exactly one synchronous'):
            self.check_source(source)

    def test_async_functions_are_rejected(self):
        source = self.source.replace('def _normalize_city_text(', 'async def _normalize_city_text(', 1)
        with self.assertRaisesRegex(ValueError, 'Expected exactly one synchronous'):
            self.check_source(source)

    def changed_mapping(self, change):
        tree = ast.parse(self.source)
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'SUPPORTED_CITIES' for t in n.targets))
        mapping = ast.literal_eval(assignment.value)
        change(mapping)
        return self.source.replace(ast.get_source_segment(self.source, assignment),
                                   'SUPPORTED_CITIES = ' + repr(mapping), 1)

    def test_changed_city_records_fail_check_without_writing(self):
        changes = [
            lambda m: m[next(iter(m))].update(country_code='zz'),
            lambda m: m[next(iter(m))]['aliases'].append('unapproved alias'),
            lambda m: m.__setitem__('Unapproved City', m.pop(next(iter(m)))),
        ]
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError, 'City snapshot differs'):
                    self.check_source(self.changed_mapping(change))

    def test_changed_city_count_is_rejected(self):
        source = self.changed_mapping(lambda m: m.pop(next(iter(m))))
        with self.assertRaisesRegex(ValueError, 'Supported set changed'):
            self.check_source(source)

    def test_successful_check_does_not_write(self):
        self.check_source(self.source)

    def test_adapter_is_not_executed_and_unrelated_source_is_not_hashed(self):
        self.check_source('raise RuntimeError("Adapter must never execute")\n' + self.source)

    def test_internal_comment_changes_conservatively_require_review(self):
        source = self.source.replace('def _normalize_city_text(text):',
                                     'def _normalize_city_text(text):\n    # review this edit', 1)
        with self.assertRaisesRegex(ValueError, 'Normalization changed'):
            self.check_source(source)


if __name__ == '__main__':
    unittest.main()
