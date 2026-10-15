# Contract fixture validation — 2026-10-15

Candidate: API v0.4. Command: `python docs/contracts/validate_fixtures.py`.

Result: PASS — 12 fixture files validated and 8 intentionally invalid mutations rejected.

Validated: JSON Schema field/type/nullability/format constraints; matching request/result; 1–7 nights and all itinerary dates; adult occupancy; selected offers; itemized costs and references; additional/unknown taxes; provider/estimate subtotals; missing-category and total rules; all three budget states; error HTTP/header mappings.

Rejected mutations: falsely within-budget partial result; nonexistent selected offer; missing itinerary day; duplicated tax item; wrong hotel occupancy; incorrect subtotal; false live-price status; incorrect status when known minimum already exceeds budget.

Limits: Synthetic data only. No APIs called. Actual flight timezone/route matching requires provider provenance; allowed cities, real occupancy evidence, permissions/quotas, conversion and estimates need provider/team review. The internal adapter proposal is documented, not implemented or live-tested. Team approvals are not implied.
