"""Offline-only schema/semantic checks; run from frontend with jsonschema installed."""
import copy
import importlib.util
import json
import re
import unittest
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'frontend/src/data/offlineDemo'
spec = importlib.util.spec_from_file_location('fixture_rules', ROOT / 'docs/contracts/validate_fixtures.py')
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)
SAMPLES = {name: json.loads((DATA / f'{name}.json').read_text(encoding='utf-8'))
           for name in ('rome', 'paris', 'barcelona')}
with zipfile.ZipFile(ROOT / 'docs/design/des-02/TravelMate-design-source.zip') as archive:
    source = archive.read('TravelMate-design-source/screens/DemoTrip.dc.html').decode('utf-8')
ORIGINAL = json.loads(re.search(r'const DATA = (.*?);\s*const isDemo', source, re.S).group(1))


class DemoValidation(unittest.TestCase):
    def test_schema_is_valid(self):
        Draft202012Validator.check_schema(rules.SCHEMA)

    def test_provenance_and_fixed_clock(self):
        for name, sample in SAMPLES.items():
            with self.subTest(sample=name):
                p = sample['provenance']
                self.assertEqual(sample['id'], name)
                self.assertEqual(p['label'], 'DEMO')
                self.assertEqual(p['data_mode'], 'offline_demo')
                self.assertIs(p['live_evidence'], False)
                self.assertEqual(p['contract_version'], '0.4')
                self.assertEqual(p['validation_today_utc'], rules.TODAY.isoformat())
                self.assertIn('not live', p['notice'])
                self.assertEqual(p['source_archive'], 'docs/design/des-02/TravelMate-design-source.zip')
                self.assertEqual(p['source_entry'], 'TravelMate-design-source/screens/DemoTrip.dc.html')
                for group in sample['response']['travel_options'].values():
                    for offer in group['offers']:
                        self.assertEqual(offer['source'], 'demo-sample')
                        self.assertTrue(offer['id'].startswith('demo-'))


def valid_case(name):
    def check(self):
        sample = SAMPLES[name]
        rules.response_check(sample['response'], sample['request'])
    return check


def source_case(name):
    def check(self):
        self.assertEqual(SAMPLES[name]['response'], ORIGINAL[name]['response'])
        self.assertEqual(SAMPLES[name]['label'], ORIGINAL[name]['label'])
    return check


for name in SAMPLES:
    setattr(DemoValidation, f'test_{name}_schema_and_semantics', valid_case(name))
    setattr(DemoValidation, f'test_{name}_original_response_unchanged', source_case(name))

# These mutations must be rejected by the repository's real rules, not a parallel
# frontend reimplementation of authoritative budget/selection calculations.
MUTATIONS = {
    'missing_selected_offer': ('rome', lambda r: r['budget'].update(selected_flight_offer_id='missing')),
    'wrong_fee_aware_selection': ('rome', lambda r: r['budget'].update(selected_flight_offer_id=next(
        o['id'] for o in r['travel_options']['flights']['offers'] if o['id'] != r['budget']['selected_flight_offer_id']))),
    'wrong_total': ('rome', lambda r: r['budget'].update(projected_total_usd=1)),
    'wrong_subtotal': ('paris', lambda r: r['budget'].update(provider_subtotal_usd=1)),
    'wrong_budget_status': ('paris', lambda r: r['budget'].update(status='within_budget')),
    'incomplete_itinerary': ('rome', lambda r: r['itinerary'].pop()),
    'invalid_calendar_date': ('rome', lambda r: r['itinerary'][0].update(date='2026-02-30')),
    'wrong_hotel_coverage': ('rome', lambda r: r['travel_options']['hotels']['offers'][0].update(occupancy_adults=4)),
    'unknown_tax_as_zero': ('barcelona', lambda r: r['travel_options']['flights']['offers'][0]['taxes'].update(additional_amount_usd=0)),
    'unknown_ledger_as_zero': ('barcelona', lambda r: next(i for i in r['budget']['cost_items'] if i['kind'] == 'unknown').update(amount_usd=0)),
    'unknown_total_as_zero': ('barcelona', lambda r: r['budget'].update(projected_total_usd=0)),
    'missing_category_lost': ('barcelona', lambda r: r['budget'].update(missing_categories=[])),
    'duplicate_cost_item': ('paris', lambda r: r['budget']['cost_items'].append(copy.deepcopy(r['budget']['cost_items'][0]))),
    'broken_activity_reference': ('paris', lambda r: next(i for i in r['budget']['cost_items'] if i['category'] == 'activities')['activity_ref'].update(order=99)),
    'unknown_schema_property': ('rome', lambda r: r.update(provider_verified=True)),
}


def rejected_case(name, mutate):
    def check(self):
        sample = SAMPLES[name]
        response = copy.deepcopy(sample['response'])
        mutate(response)
        with self.assertRaises((ValueError, ValidationError)):
            rules.response_check(response, sample['request'])
    return check


for label, (name, mutate) in MUTATIONS.items():
    setattr(DemoValidation, f'test_reject_{label}', rejected_case(name, mutate))


if __name__ == '__main__':
    unittest.main(verbosity=2)
