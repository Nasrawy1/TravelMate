# PR #35 description draft

Local draft only. GitHub PR #35 has not been updated. This draft includes local,
uncommitted review corrections after `c1b12b4`; it is not a claim that those
corrections are already present in the remote branch.

Proposed title: **FE-04: Real Trip Generation Integration + DES-03 Visual Polish**

Source: `dyarraed:feat/fe-04-real-trip-generation`
Target: `Nasrawy1:main`

---

Closes #28 when merged.

Implements Login → Trip Planner → authenticated `POST /api/v1/trips/generate`
under the adopted v0.4 contract → validated, account-bound in-memory Results.
The shared API client obtains the current Supabase JWT at request time; tokens
are not stored with trip results. Responses retain backend-owned offer selection,
expenses, totals and budget statuses.

- Adapter-derived 80-city suggestions with accessible search and keyboard
  selection, canonical submission and request validation. Suggestions do not
  guarantee offers or current prices.
- Loading and duplicate-submit prevention, safe field/service errors, session
  expiry handling, Retry-After cooldown and deliberate retries. No automatic
  generation retry. Account changes/signout invalidate pending operations,
  including A → B → A, so late responses cannot restore stale Results.
- Shared Results render itinerary, selected flights/hotels, availability, sources,
  UTC retrieval timestamps, taxes, warnings, expense items, unknown/null costs
  and backend-supplied budget assessments. Retrieved prices are not guaranteed
  current or bookable prices; missing costs never become zero.
- Ali-reviewed DES-03 Results/Generation/404/Welcome polish and local
  Figtree/Fraunces fonts with OFL licenses. The three-trip Offline Demo remains
  independent of Auth and backend/provider calls, with permanent DEMO labels.

## Local review corrections

- Match public-schema decimal half-even budget cent normalization without
  tolerances or response mutation: `1500.129 → 1500.13` is accepted; genuine
  mismatches, wrong ties and unrounded responses remain rejected. This matches
  inspected BE-03 `bbe1a84`; Adel's explicit public tie-breaking confirmation
  remains pending, not recorded as a contract agreement.
- Replace interpreter-dependent AST display fingerprints with SHA-256 of original
  normalization function source segments and normalized line endings. Preserve
  the pinned source commit and all 80 records; reject decorated, async,
  missing or duplicate functions pending review.
- Refresh E2E documentation while preserving evidence limitations and the earlier
  partial-price run.

## Automated verification after local fixes

- **372 frontend tests passed, 0 failed.**
- TypeScript, production build and whitespace checks passed.
- City-sync `--check` passed on **Python 3.12.14 and 3.14.5**.
- **13 focused city-sync regression tests passed on each Python version**,
  covering source changes, line endings, decorators, missing/duplicate functions,
  changed mapping and read-only checks.
- Build retains the large-chunk warning. Automated/mock tests are separate from
  live E2E evidence and did not send additional generation/provider requests.

## Real E2E evidence — October 28, 2026

Scenario: Istanbul → Rome, December 1–4, 2026; 2 adults; USD 1,500.

Latest run:

- Frontend: `c1b12b4d0a85973edace6d6a22ca60c73361852a`.
- Backend: `bbe1a841a9a27a81ceecf632086cb72b3847d833`.
- Startup diagnostic confirmed effective `TRAVELMATE_FLIGHT_MODE=live`.
- Exactly one authenticated generation POST; HTTP **200** retained in the safe
  matching backend diagnostic.
- Safe request ID: `c7fef61d-d160-4b3f-b76b-4847c33b5f96`.
- Results displayed **three flight offers**, hotel information and **four itinerary
  days**, with an **Uncertain** budget because some costs remained unknown.
- Diagnostic capture failed: exact `travel_options.flights.status` and the complete
  warnings array were **not retained/recovered**. No Warnings section was visible,
  but that does **not** prove `warnings=[]`. Public `flights.reason_code` was
  **NOT EXPOSED**. Do not infer missing response fields from the UI.
- No additional generation/provider request was made to recover diagnostics.

The earlier run against backend `7987f73` rendered Booking hotel prices, sources,
timestamps, itinerary and budget handling but returned unavailable flights. Its
cause remains unconfirmed for Adel/Ziyad's backend/provider investigation; the
later three-offer display does not retrospectively explain it. Neither run proves
guaranteed current availability or every-provider success.

Separately, the authenticated unsupported-city test passed with HTTP **400
UNSUPPORTED_LOCATION**, a safe `destination_city` detail and matching request
references. Backend source confirms rejection before provider search/AI; provider
traffic was not independently monitored. The temporary rejection control and its
dedicated tests were removed, preserving the original development-only JWT probe.

All three demo journeys and local fonts were manually verified with Wi-Fi
disconnected while the production preview server remained running. This is
distinct from automated asset checks; second-computer handover remains unverified.

Detailed evidence and limitations:
[frontend verification record](../../frontend/README.md#fe-04-authenticated-e2e-verification--october-28-2026).

Backend JWT verification/provider implementation, saved trips, booking and payments
are outside this frontend change. No backend source, secret configuration or
provider credentials are included.
