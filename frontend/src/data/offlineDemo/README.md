# Offline demo sample data (FE-03 step 1)

`rome.json`, `paris.json` and `barcelona.json` contain Ali's complete proposed
journeys from `docs/design/des-02/TravelMate-design-source.zip`, entry
`TravelMate-design-source/screens/DemoTrip.dc.html` (`const DATA`). The response
objects are preserved unchanged. Each local envelope adds its ID, route label,
matching six-field request and explicit DEMO provenance (`live_evidence=false`).

| ID | Route | Budget | Projected total | Status |
|---|---|---|---|---|
| rome | Istanbul → Rome | $1,200.00 | $1,184.00 | within_budget |
| paris | London → Paris | $600.00 | $670.00 | over_budget |
| barcelona | Dubai → Barcelona | $2,500.00 | Unknown (`null`) | uncertain |

All prices, source names and retrieval timestamps are synthetic examples. The
contract-shaped `live`, `provider` and `price_received` values are retained only
for schema compatibility; they do **not** establish real provider evidence.
Never strip the provenance or label this data Live. Estimates are illustrative,
not approved real estimation rates. Unknown hotel/tax costs remain null; explicit
free activities remain zero. No totals or offer selections are recalculated by
the loader.

`index.ts` imports only local JSON and types. It exports the three IDs and
`getOfflineDemoTrip(id)`, returning a fresh copy or null for an unknown ID. No
network, Auth, API, environment configuration or browser storage is required.
The `response` uses the existing `TripResult` type. Demo provenance deliberately
stays separate from `validated_api` and the development fixture manifest.
`/offline-demo` now renders these samples through the shared Results components
with explicit `offline_demo` context, a permanent DEMO banner and Demo price
labels. These production demo samples are separate from DEV-only fixture tools.

## Validation

From `frontend/`, with Python and `jsonschema` available:

```sh
python tests/validate_offline_demo.py
node --experimental-strip-types --test tests/offlineDemo.test.mjs
npm run typecheck
npm run build
```

For an isolated dependency install without changing package files or global
Python packages, the following PowerShell setup uses an ignored local cache
(installation requires internet once; validation itself does not):

```powershell
python -m pip install --target node_modules/.cache/offline-demo-validation jsonschema
$env:PYTHONPATH = (Join-Path (Get-Location) 'node_modules/.cache/offline-demo-validation')
python tests/validate_offline_demo.py
python ../docs/contracts/validate_fixtures.py
```

Run the complete frontend suite with:

```sh
node --experimental-strip-types --test tests/*.test.mjs
```

The Python tests reuse `docs/contracts/validate_fixtures.py` and the checked-in
v0.4 JSON Schema, including format and semantic validation, plus rejected-invalid
mutation tests. Node tests check local loading, provenance, selection and value
preservation with network access forbidden. The fixed validation clock is
2026-10-15 UTC, matching the original fixture context; dates are fixed sample
content, never silently moved forward or submitted for real generation.

The repository still describes v0.4 as a review candidate. Revalidate if the
team adopts a changed contract. Ali/Nasrawy's final journey approval remains
pending in SPEC §10; the user authorized these three proposals for this step.
External font loading has been removed; the demo uses system/Georgia fallbacks,
inline SVG and local production JS/CSS/data. Asset closure tests pass separately
from Diyar's reported successful Wi-Fi-disconnected production preview test.
See the [frontend manual/automated evidence record](../../../README.md#manual-offline-evidence-reported-by-diyar)
for the reported observations, rerun checks and remaining approval/handover items.
Second-computer testing remains unverified. The UI has no Auth/generation/save controls or service
calls; Exit demo and Create account explicitly leave the offline flow.
