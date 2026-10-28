# Supported-city suggestions

Generated from `SUPPORTED_CITIES` in `backend/app/adapters/travelmate.py` at
`upstream/feat/travel-apis`, commit `3d3c79a8912de70b6892fed7d2d6d313ce7f4c3e`.
`cities.json` records the immutable source commit and normalization function AST digest.
Only canonical labels, explicit aliases and country codes are copied. No independent
allowlist, invented qualifiers, airport IDs, provider credentials or live lookup is used.
Country codes displayed alongside suggestions come directly from the mapping.

The resolver mirrors `_normalize_city_text` and `resolve_supported_city`: Python
whitespace collapse/trim, lowercase, then exact canonical-name or alias match.
Search is a convenience substring filter, not permission to submit partial names.
Requests contain canonical names, never aliases or country suffixes.

To verify the snapshot from the repository root:

```sh
python frontend/scripts/sync_supported_cities.py --check
```

When the adapter changes, fetch/review the approved adapter revision, then run:

```sh
python frontend/scripts/sync_supported_cities.py <approved-git-ref>
python frontend/scripts/sync_supported_cities.py <approved-git-ref> --check
```

Review the generated diff and run frontend tests/typecheck/build. The generator uses
Python AST literal extraction and never executes the adapter. Changes to the count
or normalization stop generation and require review of the generator, frontend
resolver and tests together. Do not hand-edit the JSON or add aliases independently.

Public v0.4 allows 1–200 characters after trimming. The adapter's older
`validate_city_name` helper has narrower constraints; frontend submission uses
canonical mapped names, while backend validation remains authoritative.
Supported means accepted by the mapping, not guaranteed offers, coverage or prices.
This dataset is not used by the Offline Demo.
