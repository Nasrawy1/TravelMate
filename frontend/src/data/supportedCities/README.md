# Supported-city suggestions

Generated from `SUPPORTED_CITIES` in `backend/app/adapters/travelmate.py` at
`upstream/feat/travel-apis`, commit `3d3c79a8912de70b6892fed7d2d6d313ce7f4c3e`.
`cities.json` records the immutable source commit and normalization source digest.
Only canonical labels, explicit aliases and country codes are copied. No independent
allowlist, invented qualifiers, airport IDs, provider credentials or live lookup is used.
Country codes displayed alongside suggestions come directly from the mapping.

The resolver mirrors `_normalize_city_text` and `resolve_supported_city`: Python
whitespace collapse/trim, lowercase, then exact canonical-name or alias match.
Search is a convenience substring filter, not permission to submit partial names.
Requests contain canonical names, never aliases or country suffixes.

`normalization_sha256` is SHA-256 over the UTF-8 original source segments of
`_normalize_city_text`, then `resolve_supported_city`, joined by exactly one LF.
CRLF and CR line endings are normalized to LF before extraction. Segments run
from each `def` to the end of its AST source span, with no added trailing newline.
Comments and formatting inside those spans are preserved, so even nonfunctional
edits can conservatively require review. The digest does not use `ast.dump()` or
bytecode, whose representation can change between Python versions. Decorated,
async, missing or duplicate normalization functions are rejected pending review.
The generator parses source statically and never imports or executes the adapter.

To verify the snapshot from the repository root:

```sh
python frontend/scripts/sync_supported_cities.py --check
```

The default uses the immutable commit recorded in `cities.json`, not the current
branch or a moving remote ref. Checks are verified on Python 3.12.14 and 3.14.5.
Run the focused generator regression tests from the repository root with:

```sh
python -B -m unittest discover -s frontend/tests -p test_sync_supported_cities.py
```

`--check` compares the complete generated snapshot and never writes it, whether
the check passes or fails.

When the adapter changes, fetch/review the approved adapter revision, then run:

```sh
python frontend/scripts/sync_supported_cities.py <approved-git-ref>
python frontend/scripts/sync_supported_cities.py <approved-git-ref> --check
```

Review the generated diff and run frontend tests/typecheck/build. The generator uses
Python AST literal extraction and never executes the adapter. Changes to the count
or normalization stop generation and require review of the generator, frontend
resolver and tests together. Do not hand-edit the JSON or add aliases independently.
If normalization intentionally changes, stop and review the exact pinned source
functions against the TypeScript resolver before approving a new digest. Do not
bypass the guard or accept an unknown fingerprint just to regenerate city data.
The source-digest migration preserves the original pinned commit and all 80 records.

Public v0.4 allows 1–200 characters after trimming. The adapter's older
`validate_city_name` helper has narrower constraints; frontend submission uses
canonical mapped names, while backend validation remains authoritative.
Supported means accepted by the mapping, not guaranteed offers, coverage or prices.
This dataset is not used by the Offline Demo.
