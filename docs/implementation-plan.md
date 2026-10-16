# TravelMate — Implementation Plan

**Status:** Published planning document; scope and general architecture approved by team lead Nasrawy (Nasrawy1) on 2026-10-15. Task proposals are not a live Project-status snapshot.
**Date:** 2026-10-15
**Baseline:** architecture v1.2, scope v1.3, API wire schema v0.3, database v0.2.

**PLAN-02 preparation update (2026-10-15):** [API contract v0.4](api-contracts.md), [internal adapter contracts](adapter-contracts.md), and [validated structural fixtures](fixtures/README.md) are now available as a review candidate. References below to v0.3 describe the preceding baseline; v0.4 adoption requires Diyar/Adel/Ziyad review and provider compatibility evidence. This update does not approve implementation, provider selection, or optional storage execution.

## Priorities and ownership

P0 unlocks work or resolves feasibility. P1 delivers the mandatory MVP. P2 is optional after core acceptance. Priorities below are proposals, not observed Project statuses. Existing issue assignees are preserved. BE-00 (#15), FE-02 (#16), API-04 (#17), API-05 (#18) and BE-04 (#19) are created issues; other new task codes remain local proposals until separately created.

| Owner | Account | First deliverable | Collaboration |
|---|---|---|---|
| Nasrawy | Nasrawy1 | Reviewed scope/contracts + shared fixtures | All owners; reviews integration |
| Ali | aliyousifalqudsi-bot | Core wireframes, then incremental UI designs | Diyar + Nasrawy |
| Diyar | dyarraed | React setup and fixture-driven screens | Ali for UI; Adel for Auth/API |
| Adel | AdelbahaMattar | FastAPI foundation + Supabase Auth environment | Diyar for Auth; Ziyad for adapters |
| Ziyad | zee0x | AI evidence + real-price provider feasibility | Adel for schemas; Nasrawy for provider decision |

## Work sequence

1. Use the team-lead-approved #10 scope/architecture; continue #11 review, #3 wireframes, #12 React setup, BE-00/#7 backend/Auth setup, and #4/#5 feasibility in parallel. Review the reported #2 completion evidence rather than repeating completed research.
2. Within the first two integration working days, choose one viable travel category and document supported searches. Escalate if neither works; never silently weaken F-08A.
3. Ali releases approved screens one at a time. Diyar builds with fixtures; Adel implements auth/schemas/budget; Ziyad implements AI and the selected travel adapter after agreeing the boundary.
4. Combine the protected real generation endpoint with the UI, then verify failure paths, explicit offline demo and second-computer handover.
5. Optional F09 and API-06 start only after core acceptance and explicit prioritization.

## Approved Phase One First Batch — 2026-10-16

Nasrawy approved this work distribution and the creation of API-04 (#17), API-05 (#18) and BE-04 (#19). This records assignment and delivery order, not implementation completion, provider approval or v0.4 adoption. Project-board fields remain unchanged.

### توزيع العمل وأول تسليم لكل شخص
| الشخص | العمل الحالي | أول تسليم قابل للمراجعة | العمل التالي |
|---|---|---|---|
| علي | DES-02 #6 | تصميم فورم الرحلة مع التحقق والأخطاء؛ يراجعه ديار ونصراوي | تصميم النتائج ومصادر الأسعار والمصاريف والحالات الثلاث |
| ديار | FE-02 #16 | فورم يعمل محلياً + عرض نتيجة Fixture بوسم MOCK واضح، بعد مراجعة الحقول | بقية حالات النتائج ثم ربط Auth مع عادل تحت #8 |
| عادل | BE-01 #7 ثم BE-00 #15 | إعداد Auth موثّق + FastAPI يعمل وhealth يمكن استدعاؤه من الفرونت | BE-02 #8 مع ديار، ثم BE-04 وحساب المصاريف |
| زياد | API-TEST-01 #13 | عينة مصححة: طلب → بيانات مزود منقّحة → بيانات موحّدة → رد AI قابل للتحقق | API-05 لمزود واحد ثم API-04 للـAI، مع إعادة استخدام التصحيحات |
| نصراوي | PLAN-02 #11 ومراجعة التسليمات | سجل اتفاق ديار/عادل/زياد والقرارات المتبقية؛ قائمة الاختبار الأولي أدناه | قبول PRs الصغيرة وتنسيق اختبار التكامل |

**تنظيم السعة:** هذه قائمة ترتيب، وليست تكليفاً لكل شخص بفتح عدة مهام كبيرة بالتزامن. كل شخص يركز على تسليم رئيسي واحد؛ مراجعة العقود والتنسيق تتم بالتوازي.

**Phase Zero:** #7 و#15 و#11 و#13 بحسب دورها التأسيسي الحالي.  
**Phase One:** #6 و#8 و#9 و#16 وAPI-04 وAPI-05 وBE-04.  
التصنيف هنا خطة عمل؛ لا يغيّر حقول البورد.

### بوابات البداية والتسليم
| العمل | ما يمكن بدؤه | ما يلزم قبل اعتباره مكتملًا |
|---|---|---|
| تصميم الشاشات | نطاق MVP وحقول العقد المرشح | مراجعة الشاشة والحقول مع ديار ونصراوي |
| واجهات Mock | الاتفاق على الحقول المستخدمة وتحديد v0.4 كمرشح صراحة | حالات Fixtures تعمل؛ الإغلاق النهائي لـ#16 يتطلب الربط الحقيقي أيضاً |
| تأسيس FastAPI | اعتماد التقنية والنطاق؛ لا ينتظر أسعار السفر | تشغيل محلي موثّق واستدعاء health من الفرونت |
| Auth #8 | إعداد #7 وأساس الفرونت والباكند | دخول فعلي وطلب محمي، ورفض التوكن غير الصحيح |
| API-05 | عينة مزود مصححة واختيار المزود واتفاق حدوده مع عادل | أسعار حقيقية مرتبطة بالمدخلات وتوثيق التغطية والرسوم |
| API-04 | اتفاق مخرجات AI ودليل #13؛ يمكن تطويره بمدخلات موحدة اصطناعية معلّمة | استدعاء AI حقيقي ومخرجات مطابقة، مع اختبار الأخطاء |
| BE-04 | اتفاق قواعد التكاليف والاختيار مع عادل؛ يمكن استخدام Fixtures | حسابات حتمية ناجحة واختبارات حالات النقص والرسوم |
| Generate #9 | هيكل وموديلات بعد #15 | العقد المعتمد + #8 + API-04/API-05 + BE-04 |

الموافقة على v0.4 تبقى تحت #11. إذا كشفت عينة زياد أن أحد الحقول غير مدعوم، يُناقش التغيير هناك قبل اعتماده؛ لا يغيّر أي عضو العقد بصورة منفردة.

## Collaboration rules

- One implementation owner per task; collaborators review interfaces rather than editing the same module without coordination.
- Adel owns routes, auth verification, trip orchestration and budgets; Ziyad owns provider adapters. Agree Python input/output shapes before coding them independently.
- Diyar owns frontend code; Ali owns Figma. Wireframes and setup can proceed together; full high-fidelity design is not a setup blocker.
- Small PRs linked to issues; Nasrawy reviews. Mock-based checks may precede live integration but never prove live pricing.
- This plan assigns no board status: the Project columns were not available through the connector.

## Existing issue alignment

This document distinguishes proposed scope from actual delivery. PLAN-01 (#10) records team-lead approval; PLAN-02 (#11) remains pending contract adoption; BE-01 (#7) is Auth-only setup; FE-01 (#12) was merged in #14 and closed. The Phase One descriptions below become applied issue scope only when their corresponding GitHub updates are published after Nasrawy's explicit approval. Preserve current assignees, labels, state and discussion. Task text alone does not mark implementation complete.

### #1: PLAN-00: Track MVP Foundations

**Owner:** Nasrawy1  
**State:** Remain open as a tracker.

#### Objective
Track the authoritative foundation decisions and handoff links without duplicating the implementation or approval checklists in PLAN-01 and PLAN-02.

#### Checklist
- [x] Link PLAN-01 (#10) for team-lead-approved scope, stack and general architecture.
- [x] Link PLAN-02 (#11) for prepared contracts, schemas, shared fixtures and remaining approval decisions.
- [x] Link provider research #2/#4/#5 and the open corrective follow-up #13.
- [ ] Confirm the relevant team members can access and have reviewed the authoritative documentation.
- [ ] Track completion of PLAN-02 review/decisions and link its recorded integration approval.
- [ ] Record unresolved provider constraints and the handoff to implementation tasks before closing this tracker.

#### References
- [Scope](https://github.com/Nasrawy1/TravelMate/blob/main/docs/mvp-scope.md)
- [Architecture](https://github.com/Nasrawy1/TravelMate/blob/main/docs/architecture.md)
- [API contract](https://github.com/Nasrawy1/TravelMate/blob/main/docs/api-contracts.md)
- [Internal adapters](https://github.com/Nasrawy1/TravelMate/blob/main/docs/adapter-contracts.md)
- [Fixtures](https://github.com/Nasrawy1/TravelMate/blob/main/docs/fixtures/README.md)
- [Implementation plan](https://github.com/Nasrawy1/TravelMate/blob/main/docs/implementation-plan.md)

#### Completion Rule
Close only when foundation approval and handoff evidence are linked. This tracker does not require the entire MVP implementation to finish. Closing research issues is not evidence that #13 corrections or PLAN-02 provider sign-off are complete.

### #2: API-01: Research & Test AI API

**Owner:** zee0x  
**Proposed priority:** P0  
**Start:** Review reported completed research

**Tasks**

- [ ] Preserve the existing completed research checklist.
- [ ] Attach the provider/model, sanitized request and structured output, measured latency, observed cost/limits and recommendation.
- [ ] Compare the sample with the v0.4 review candidate; final integration follows the version explicitly adopted under #11: complete nights + 1 itinerary; no invented live travel offers.
- [ ] Team lead reviews evidence before changing issue state.

**Acceptance**

- [ ] Evidence is linked and compatible with the contract; no repeated research required if existing evidence is adequate.

**Dependencies:** None

### #3: DES-01: Create Core User Flow & Wireframes

**Owner:** aliyousifalqudsi-bot  
**Proposed priority:** P0  
**Start:** Start now

**Tasks**

- [ ] Design online sign-in → trip form → loading → results/error/retry.
- [ ] Design a separate offline-demo entry and selection of 2–3 predefined trips.
- [ ] Use 1–4 adults, 1–7 nights, USD whole-group budget and supported-city selections.
- [ ] Show unknown prices, warnings, selected offers and three budget statuses.
- [ ] Review incrementally with Diyar and the team lead; exclude booking/checkout and defer saved-trip screens.

**Acceptance**

- [ ] Figma flow covers core states; Diyar can begin one approved screen without waiting for the whole set.

**Dependencies:** #10 and #11 candidate docs

### #4: API-02: Evaluate Flight Price Provider Feasibility

**Owner:** zee0x  
**Proposed priority:** P0  
**Start:** Start feasibility now

**Tasks**

- [ ] Check access, permitted use, cost/limits and whether prices are real versus fixed sandbox fixtures.
- [ ] Construct searches from supported cities, dates and adult count.
- [ ] Record round-trip/all-adult coverage, currency, source and retrieval time.
- [ ] Test two distinct input combinations where feasible and preserve sanitized evidence.
- [ ] Compare with #5; recommend one mandatory provider with team lead and Adel within the first two integration working days.

**Acceptance**

- [ ] Document actual outcome and limitations; a viable provider has at least one real-priced result. An unsuccessful candidate may be ruled out, but does not satisfy F-08A.

**Dependencies:** None; coordinate #5

### #5: API-03: Evaluate Hotel Price Provider Feasibility

**Owner:** zee0x  
**Proposed priority:** P0  
**Start:** Start feasibility now

**Tasks**

- [ ] Evaluate Agoda access and alternatives without assuming partner access.
- [ ] Check permitted use, limits/cost and real price availability.
- [ ] Test dates, destination and occupancy; verify full-stay/all-adult coverage and room count where needed.
- [ ] Record currency, source, timestamp and sanitized output; distinguish fixed test data from real offers.
- [ ] Compare with #4 and prioritize the first viable category; escalate if neither is feasible.

**Acceptance**

- [ ] Document actual outcome and limitations; chosen category supplies at least one real price and a second distinct supported query where feasible.

**Dependencies:** None; coordinate #4

### #6: DES-02: Design Core MVP Screens & States

**Owner:** aliyousifalqudsi-bot (Ali)  
**Priority:** P1

#### Objective
Deliver implementation-ready designs for the remaining core TravelMate screens, reusing Ali's existing Riviera Welcome/Auth design and the frontend foundation merged in PR #14.

#### Tasks
- [ ] Review the existing Welcome/Auth design and implementation with Diyar; identify only necessary consistency or missing-state changes rather than rebuilding delivered screens.
- [ ] Document reusable colors, typography, spacing, buttons, inputs, cards and status labels.
- [ ] Design the trip form: departure/destination from supported choices, travel dates, 1–4 adults and positive whole-trip/all-adult USD budget; trip duration is 1–7 nights.
- [ ] Design loading, field-validation, request-error, retry and session-expiry states.
- [ ] Design itinerary results for all trip dates, selected flight/hotel offers, source/retrieval-time labels, itemized costs and warnings.
- [ ] Design within_budget, over_budget and uncertain states; unknown prices must not appear as zero.
- [ ] Design the separate offline-demo entry, sample selection and visible DEMO identification.
- [ ] Document responsive behavior for laptop/desktop and narrower layouts.
- [ ] Deliver screens incrementally with accessible design sources, assets and implementation notes; include a Figma link when used.
- [ ] Review each delivered screen with Diyar and Nasrawy.

#### Acceptance Criteria
- [ ] All mandatory screens and meaningful loading/error/missing-price states have usable specifications.
- [ ] Existing Welcome/Auth work is referenced and reused.
- [ ] Visual fields are mapped to the reviewed contract; unresolved v0.4 fields are explicitly flagged.
- [ ] Diyar can implement one approved screen without waiting for the whole design set.
- [ ] Nasrawy reviews the delivered designs and Diyar confirms access to sources/assets.

#### Scope Boundaries
No booking, checkout, payment or booking-confirmation screens. Saved-trip screens remain deferred under optional F-09. A polished design does not prove live prices or completed integration.

#### Dependencies and Deliverables
Use PLAN-01 (#10), available DES-01 (#3) design sources, and PLAN-02 (#11) candidate fields. Final data-bound designs require the reviewed field agreement. Deliver screen designs, a small shared style/component specification, assets and handoff notes.

### #7: BE-01: Configure Supabase Auth Environment

**Owner:** AdelbahaMattar  
**Proposed priority:** P0  
**Start:** Start now

**Tasks**

- [ ] Create/configure a dedicated development Supabase project.
- [ ] Configure email/password Auth, local redirect settings and document signup/email-confirmation behavior.
- [ ] Document frontend public URL/key and backend token-verification configuration using placeholders.
- [ ] Coordinate access with Diyar without committing secrets.
- [ ] Do not create profiles, travel_requests, itineraries or trips tables for core setup; F-09 migration is deferred.

**Acceptance**

- [ ] The project is available for Auth integration; safe environment instructions exist; no application-table dependency blocks core generation.

**Dependencies:** #10 approved stack

### #8: BE-02: Integrate Supabase Auth & Verify Backend Tokens

**Owner:** AdelbahaMattar (Adel)  
**Collaborator:** dyarraed (Diyar)  
**Priority:** P1

#### Objective
Connect existing frontend authentication UI to Supabase Auth and enforce verified bearer authentication in FastAPI.

#### Tasks — Diyar
- [ ] Connect existing signup, signin and signout flows to Supabase Auth; remove the unconnected-service behavior only when real integration exists.
- [ ] Handle initial session loading, refresh, expiration and signout; avoid misleading authenticated states.
- [ ] Implement signup/email-confirmation behavior agreed in BE-01 (#7), with useful validation/error/loading messages.
- [ ] Connect existing forgot/reset-password forms; require a valid recovery session before allowing an actual password change.
- [ ] Attach the current access token to protected FastAPI calls and handle standardized 401 responses.
- [ ] Keep explicit offline-demo access independent of hosted login and avoid initializing online services in that path.

#### Tasks — Adel
- [ ] Verify JWT signature, expiry and configured issuer/audience as appropriate; derive identity from the verified token.
- [ ] Provide reusable authentication enforcement for protected backend operations.
- [ ] Reject missing, expired, malformed or invalid tokens with the agreed 401 envelope and request_id.
- [ ] Coordinate configuration with Diyar using placeholder-only examples; keep elevated credentials server-side.
- [ ] Validate a protected backend request with Diyar as soon as FastAPI foundation exists. If generation is not ready, use an isolated development/test probe, not a new permanent public product endpoint.

#### Joint Acceptance
- [ ] Signup/confirmation behavior, login/logout and session handling work locally with real Supabase Auth.
- [ ] Recovery works only with a verified recovery session; visiting the reset page alone cannot change credentials.
- [ ] A valid token reaches a protected backend handler; missing/invalid/expired tokens are rejected.
- [ ] Test with at least two test accounts and record sanitized outcomes without tokens or passwords.
- [ ] The offline-demo path does not require online signin.
- [ ] Setup and test instructions are reproducible.

#### Dependencies and Scope
Depends on BE-01 (#7), merged FE-01 (#12 / PR #14), and BE-00 (#15) backend foundation. Coordinate common error details with PLAN-02 (#11). No application tables or optional saved-trip migration are required. Do not build duplicate FastAPI login/signup endpoints. Auth configuration belongs to #7; this issue implements and verifies integration.

#### Deliverables
Frontend Auth integration, backend JWT verification, safe setup instructions and sanitized integration evidence.

### #9: BE-03: Implement Generate Trip Endpoint

**Owner:** AdelbahaMattar (Adel)  
**Priority:** P1

#### Objective
Implement authenticated POST /api/v1/trips/generate, orchestrating normalized travel offers, a validated AI itinerary and backend-owned budget calculation. Generation does not persist a trip.

#### Contract Baseline
Target the v0.4 review candidate in docs/api-contracts.md and docs/contracts/api-v0.4.schema.json. PLAN-02 (#11) must record adoption before final integration acceptance. Do not mix v0.3 models with v0.4 responses or treat this issue rewrite as contract approval.

#### Tasks
- [ ] Implement strict request models for departure_city, destination_city, start_date, return_date, adults and budget_usd.
- [ ] Validate supported canonical locations, distinct cities, future dates, 1–7 nights, 1–4 adults and positive whole-trip USD budget, following the reviewed date convention.
- [ ] Apply BE-02 verified bearer authentication.
- [ ] Call the agreed travel adapter and use normalized eligible offers; no fabricated live-price fallback.
- [ ] Apply reviewed offer-selection rules and pass selected context to the AI adapter.
- [ ] Validate complete nights + 1 itinerary output, required fields, references and cost semantics.
- [ ] Use the BE-04 budget service to construct the expense ledger and calculate totals/statuses; never trust AI-computed authoritative totals.
- [ ] Return the agreed response with travel availability, selected IDs, itemized budget and warnings.
- [ ] Apply common errors, request_id and deadlines; preserve valid generation with explicit unavailable travel categories when AI succeeds.
- [ ] Keep generation independent of database writes; do not return a persisted trip ID.
- [ ] Add meaningful request/auth/response/error checks and document reproducible examples.

#### Example Request
```json
{
  "departure_city": "Istanbul",
  "destination_city": "Rome",
  "start_date": "2026-11-10",
  "return_date": "2026-11-12",
  "adults": 2,
  "budget_usd": 1500
}
```
These dates/cities illustrate the shape only. Runtime tests need future dates and verified supported locations.

#### Acceptance Criteria
- [ ] Valid authenticated requests produce a complete contract-conforming response.
- [ ] Invalid fields/date relationships and unsupported locations use the reviewed error mappings; unauthorized requests are rejected.
- [ ] Totals come from deterministic backend arithmetic with no duplicate fees or unknown-as-zero amounts.
- [ ] Real AI and the chosen mandatory live-price adapter are integrated and evidence is recorded separately from mock tests.
- [ ] Provider no-results/failure and AI invalid-output/timeout cases behave as specified.
- [ ] Generation neither writes a trip to Supabase nor requires application tables.
- [ ] Diyar can consume the documented result and errors locally.

#### Dependencies and Delivery Order
Scaffold/models may start after BE-00 (#15) using the explicitly identified candidate. Final integration depends on PLAN-02 (#11), BE-02 (#8), API-04 (AI adapter), API-05 (mandatory travel adapter), and BE-04 (budget calculation). API-04/API-05/BE-04 are existing planning codes, not newly created issues in this review package. Provider compatibility evidence comes from #13.

#### Deliverables
Generate endpoint, validated models, orchestration, integration checks and frontend-facing examples. Optional saved-trip endpoints remain outside this issue.

### #10: PLAN-01: Align MVP Scope & Architecture

**Owner:** Nasrawy1  
**Priority:** P0  
**Planning status:** Scope and general architecture approved by the team lead on 2026-10-15. Issue #10 was already closed as completed before this documentation update.

**Completed planning deliverables**

- [x] Document scope v1.3 and architecture v1.2.
- [x] Confirm React/Vite + FastAPI + Supabase Auth and real AI with at least one mandatory live flight OR hotel provider.
- [x] Keep the second provider and saved trips optional; defer booking/confirmation UI.
- [x] Define client-only offline demo, component ownership and local handover approach.
- [x] Record team-lead approval and link authoritative documents.

**Outstanding follow-up (not claimed complete)**

- [ ] Review/acknowledge the approved boundaries with the remaining team members and confirm document access.
- [ ] Complete PLAN-02 (#11) contract/interface review and provider feasibility under #2/#4/#5, with corrective evidence tracked in #13.

Approval of this planning baseline is not evidence of implementation or successful live integration.

**Dependencies:** None for the general design; provider evidence gates final integration acceptance.

### #11: PLAN-02: Review API v0.4 & Shared Fixtures

**Owner:** Nasrawy1  
**Proposed priority:** P0  
**Status:** Contract preparation available; review and integration approval pending. No completion of #11 is implied.

**Prepared deliverables**

- [x] Define required/nullable fields in the v0.4 JSON Schema and contract.
- [x] Specify itemized costs, fee treatment, selection proposal and budget arithmetic.
- [x] Propose internal travel/AI adapter inputs and outputs for Adel and Ziyad.
- [x] Supply structural request, success, missing-price, over-budget, unknown-tax and error fixtures, with explicit mock metadata.
- [x] Check fixtures structurally and semantically; reject representative invalid mutations.

**Remaining acceptance**

- [ ] Diyar, Adel and Ziyad agree on fields, internal interfaces, cost rules and demo context.
- [ ] Verify chosen provider/canonical city mappings, occupancy, dates, currency and fees.
- [ ] Approve estimation/conversion policy, selection and timeout settings; unknown amounts remain explicit meanwhile.
- [ ] Record integration baseline approval and update adopted version references consistently.

**Dependencies:** #10 approved scope; #2/#4/#5 and #13 evidence. F-09 HTTP models remain deferred.

### #12: FE-01: Initialize React + Vite Frontend

**Owner:** dyarraed  
**Delivery record:** PR #14 merged on 2026-10-16; issue #12 closed as completed. No Project-board Done status is asserted here.

**Delivered foundation:** React/Vite/TypeScript structure, routes, shared styles, Welcome/Auth/recovery UI, placeholder environment example and setup documentation.

**Verification boundary:** The author's README records clean installation, typecheck/build and local startup checks. This planning update does not claim independently rerun tests, CI success or working Supabase/backend integration.

**Acceptance scope:** Local frontend foundation, organized routes/configuration and documented setup. Contract-shaped mock-result rendering is assigned to FE-02 and is not an outstanding FE-01 acceptance condition.

**Follow-up:** FE-02 owns trip forms and mock/result rendering; BE-02 (#8) owns actual Auth integration jointly with Adel; FE-03 owns complete offline-demo delivery. PLAN-02 (#11) still gates final contract adoption.

## Existing corrective follow-up

### #13: API-TEST-01: Fix AI Test Data Accuracy & Validate End-to-End Results

Ziyad's prototype correction and evidence review is tracked in [#13](https://github.com/Nasrawy1/TravelMate/issues/13). Its distinct code is API-TEST-01. API-04 below remains reserved for implementing the AI adapter; dependencies on API-04 do not refer to #13. Refer to #13 for its current checklist and progress.

## Implementation issues and remaining proposals

### #15: BE-00: Initialize FastAPI Backend

**Issue:** [#15](https://github.com/Nasrawy1/TravelMate/issues/15)

**Phase:** Phase Zero — foundations

**Owner:** AdelbahaMattar  
**Priority:** P0; start alongside remaining setup when capacity permits.

#### Objective
Create the local FastAPI foundation needed for authentication and generation integration.

#### Tasks
- [ ] Organize backend modules for routes, schemas, auth, services and adapters without implementing speculative product endpoints.
- [ ] Implement GET /api/v1/health returning {"status":"ok","service":"travelmate-api"}.
- [ ] Configure explicit local frontend CORS origins, coordinated with Diyar; document port overrides.
- [ ] Add common exception handling and sanitized logs with request_id; error responses include the matching X-Request-ID header.
- [ ] Provide placeholder-only environment examples and keep local secrets out of Git.
- [ ] Document the tested Python version, dependency installation and backend startup command.
- [ ] Confirm the frontend can call the health endpoint locally.
- [ ] Submit a small PR with setup evidence.

#### Acceptance Criteria
- [ ] A teammate can install dependencies and start the backend using documented instructions.
- [ ] Health returns the documented JSON locally and is reachable from the configured frontend origin.
- [ ] Standard error formatting and request correlation are demonstrated.
- [ ] No secrets, application-table requirement or provider-availability dependency blocks startup.

#### Dependencies and Scope
PLAN-01 (#10). Coordinate error conventions with PLAN-02 (#11); final v0.4 adoption remains pending. No dependency on completed Supabase configuration or live travel-provider tests for the health endpoint. Health proves local backend availability only.

#### Deliverables
Backend skeleton, health route, safe config examples, installation/start instructions and local verification evidence.

### #17: API-04: Implement Validated AI Itinerary Adapter

**Issue:** [#17](https://github.com/Nasrawy1/TravelMate/issues/17)

**Owner:** zee0x (Ziyad)  
**Phase:** Phase One  
**Priority:** P1

#### Objective
Implement the real AI adapter inside the FastAPI application using the reviewed internal adapter contract. Reuse the corrected prototype evidence rather than repeating provider research.

#### Entry Conditions
- Relevant AI-output corrections and sanitized evidence from #13 are reviewed.
- Ziyad and Adel agree the adapter inputs/outputs under PLAN-02 (#11).
- BE-00 (#15) provides the backend integration structure.
- v0.4 remains a candidate until adoption is recorded in #11; acceptance uses the explicitly adopted version.

#### Tasks
- [ ] Confirm the provider/model and documented access/limits with Nasrawy; do not treat earlier prototype use as final integration approval.
- [ ] Implement the agreed generate_itinerary module boundary accepting trip_request, selected_offers, travel_availability, estimation_policy, deadline_at and request_id.
- [ ] Pass normalized trip context and only eligible selected travel offers to the real AI provider.
- [ ] Parse and validate structured output: itinerary and ancillary_estimates on success; a typed error on failure.
- [ ] Require nights + 1 ordered dates, valid activities and justified empty travel days according to the public schema and semantic rules.
- [ ] Keep activity costs as estimates/unknown; food and local transport estimates require the reviewed policy and matching policy_id, otherwise return unknown.
- [ ] Never generate authoritative flight/hotel offers, change backend-selected options or provide authoritative budget totals.
- [ ] Map timeout, rate_limited, unavailable and invalid_output to the agreed internal error envelope; Adel owns the public HTTP mapping.
- [ ] Respect the supplied overall deadline and configured per-attempt allowance; do not automatically retry chargeable AI generation.
- [ ] Keep keys server-side, redact credentials from diagnostics and avoid rotating keys to bypass quotas.
- [ ] Supply a sanitized successful real call and reproducible tests for malformed/incomplete output and controlled failure cases.
- [ ] Submit a focused PR with model/configuration notes, setup and evidence.

#### Acceptance Criteria
- [ ] A real AI call returns a validated complete itinerary for the supplied request.
- [ ] Invalid/incomplete output fails safely; it is not published as a successful itinerary.
- [ ] Missing travel prices remain unavailable context, never invented provider facts.
- [ ] Unknown ancillary costs remain unknown when no policy is approved.
- [ ] Deadline/error handling is verified; simulated failure tests are identified as simulated.
- [ ] Adel can consume the documented adapter result without parsing raw provider output.
- [ ] No credentials are committed or exposed in evidence.

#### Dependencies / Exclusions
PLAN-02 (#11), relevant #13 evidence, BE-00 (#15). Implementation can use explicit normalized test context before API-05 is finished; final end-to-end integration uses the actual selected provider. No public endpoint, authoritative ledger calculation, persistence, frontend demo or new provider research is included.

#### Deliverables
AI adapter module, meaningful validation/error tests, sanitized real sample, configuration and handoff instructions.

### #18: API-05: Implement Mandatory Live Travel Adapter

**Issue:** [#18](https://github.com/Nasrawy1/TravelMate/issues/18)

**Owner:** zee0x (Ziyad)  
**Phase:** Phase One  
**Priority:** P1

#### Objective
Implement one approved flight OR hotel provider behind the reviewed travel-adapter boundary, returning genuine request-matched normalized offers. A second category remains optional future work.

#### Entry Conditions
- #13 provides reviewed corrected evidence for the selected category.
- Nasrawy, Adel and Ziyad select the mandatory category/provider and confirm supported searches under #11.
- The agreed normalization/interface baseline and BE-00 (#15) integration structure are available.

#### Tasks
- [ ] Document the actual data provider, endpoint, access conditions and limits; distinguish RapidAPI services from direct official integrations.
- [ ] Implement canonical supported-city to provider-ID mapping; document unsupported searches and coverage limits.
- [ ] Build searches from the requested dates and adult count; validate returned date/route/occupancy scope.
- [ ] Normalize flights to the round trip for all adults OR hotels to all nights and verified adult occupancy, according to the chosen category.
- [ ] Preserve usable IDs, source, retrieval timestamps, normalized prices and fee status; never count known fees twice or discard known charges.
- [ ] Request USD where available. Convert non-USD only under the reviewed conversion policy with source/rate/time evidence; otherwise exclude those quotes and warn.
- [ ] Return both category objects under search_travel; mark the unimplemented optional category unavailable with the agreed reason.
- [ ] Return sanitized provenance for every offer, including coverage evidence, actual query parameters and required flight timezone information.
- [ ] Distinguish no_results, unsupported_search, rate_limited, timeout, auth_error, invalid_response and provider errors using the agreed envelope.
- [ ] Bound lookup time/retries by deadline_at; honor valid retry guidance within the deadline and do not rotate keys to bypass limits.
- [ ] Verify at least one real matching priced result and attempt a second distinct supported query where feasible; document quota/coverage constraints.
- [ ] Add normalization/failure tests and submit a PR with reproducible sanitized evidence.

#### Acceptance Criteria
- [ ] At least one genuine returned price matches the supplied dates, locations and traveler/occupancy scope.
- [ ] Currency, all-trip/group coverage and known taxes are correctly preserved.
- [ ] Mismatched dates, unverified occupancy and unsupported conversion never masquerade as usable USD offers.
- [ ] Multiple-adult normalization is verified with an actual sample where available; any unverified supported range remains an explicit blocker/limitation.
- [ ] Missing/unavailable results contain no fabricated live prices or fixture substitutions.
- [ ] Adel can consume the agreed normalized envelope and sanitized evidence.
- [ ] No exposed credentials, quota-bypass mechanism or unbounded retries remain.

#### Dependencies / Exclusions
PLAN-02 (#11), selected-category corrections under #13, research #4/#5 and BE-00 (#15). Research issues being closed do not themselves satisfy live-price acceptance. Backend orchestration owns selected-offer choice and final budgeting; frontend owns explicit offline demo. No booking, payment, persistence or mandatory second provider.

#### Deliverables
Travel adapter, supported mappings/limits, tests, sanitized real-price evidence and configuration instructions.

### #19: BE-04: Implement Deterministic Budget Assessment

**Issue:** [#19](https://github.com/Nasrawy1/TravelMate/issues/19)

**Owner:** AdelbahaMattar (Adel)  
**Phase:** Phase One  
**Priority:** P1

#### Objective
Select eligible normalized offers and calculate the itemized trip budget deterministically in backend code, following the reviewed contract. AI and frontend do not determine authoritative totals or budget status.

#### Entry Conditions
- BE-00 (#15) is available.
- Ledger, selection, estimation and currency-treatment decisions needed by this component are explicitly reviewed under PLAN-02 (#11).
- Normalized fixtures may be used before real adapters finish; final acceptance uses the adopted contract.

#### Tasks
- [ ] Implement the reviewed fee-aware selection rule: prefer comparable known-fee totals, choose lowest base plus additional fees and tie-break by ID; use the reviewed unknown-fee fallback only when necessary and warn.
- [ ] Select exactly one eligible offer per available category or null; expose selected IDs and reject invalid references.
- [ ] Create one base ledger line each for flights/accommodation, with unknown when no selected offer exists.
- [ ] Add known additional fees exactly once and preserve unknown-fee lines; included fees do not create duplicate costs.
- [ ] Add exactly one ledger entry per itinerary activity with a valid activity_ref.
- [ ] Normalize food and local_transport to whole-trip/all-adult entries; use unknown unless a reviewed estimate policy supports the supplied amount.
- [ ] Use decimal-safe arithmetic; round each normalized ledger item to cents before summing.
- [ ] Calculate provider_subtotal_usd and estimated_subtotal_usd from cost_items only.
- [ ] Set projected_total_usd to null whenever any unknown ledger item exists; generate the unique missing_categories list.
- [ ] Apply status precedence: reliable provider-known subtotal over budget first; otherwise complete total over budget; otherwise complete total within budget; otherwise uncertain.
- [ ] Produce useful missing-cost/fee notes and preserve selected-offer and activity consistency.
- [ ] Test the provided fixture scenarios and meaningful negative/boundary cases; deliver through a focused PR.

#### Acceptance Criteria
- [ ] Within-budget fixture totals: provider 950 + estimates 190 = projected 1140.
- [ ] Same complete costs with budget 1000 produce over_budget.
- [ ] Partial-price fixture produces provider 550, estimates 40, projected total null and uncertain.
- [ ] Known provider subtotal 550 with budget 500 produces over_budget even when other costs are unknown.
- [ ] Unknown taxes keep projected total null and prevent within_budget.
- [ ] A complete total exactly equal to budget is within_budget.
- [ ] Estimates alone do not establish a reliable minimum when other material costs are missing.
- [ ] Duplicate fees/activity references, invalid selected IDs and invalid monetary values are rejected; unknown never becomes zero.
- [ ] Results are deterministic and usable by BE-03 (#9), without provider access for fixture-based tests.

#### Dependencies / Exclusions
PLAN-02 (#11), BE-00 (#15); coordinate inputs with API-04/API-05 and output with BE-03 (#9). Does not call AI/providers, create API routes, persist trips or implement frontend calculations. Real adapter completion is not required to start fixture-based development once rules are agreed.

#### Deliverables
Offer selection/budget module, focused arithmetic/semantic tests and documented input/output handoff to orchestration.

### #16: FE-02: Implement Trip Form & Contract-Based Results

**Issue:** [#16](https://github.com/Nasrawy1/TravelMate/issues/16)

**Phase:** Phase One — implementation

**Owner:** dyarraed  
**Priority:** P1

#### Objective
Build the core trip form and reusable results UI, beginning with structural fixtures and later consuming the real generation API. Reuse Welcome/Auth UI from FE-01; actual Auth integration remains tracked jointly under BE-02 (#8).

#### Tasks
- [ ] Review v0.4 public fields and fixtures with Adel and Nasrawy under PLAN-02 (#11); track any required changes explicitly.
- [ ] Implement departure/destination choices, dates, adults and whole-trip USD budget with reviewed validation and no unsupported-city promises.
- [ ] While real provider coverage is pending, identify fixture-only city choices as mock; do not publish them as confirmed live coverage.
- [ ] Implement a frontend API boundary that submits the reviewed request and consumes the standard response/errors.
- [ ] Render complete daily itineraries, selected offers, source/retrieval metadata, itemized expenses, missing costs and budget statuses.
- [ ] Implement the contract-shaped mock renderer transferred from FE-01. Load fixture metadata alongside responses and show a visible MOCK/DEMO banner.
- [ ] Cover within-budget, over-budget, partial/no-price, unknown-tax and known-minimum-over-budget fixtures, plus validation/auth/AI/timeout/rate-limit errors.
- [ ] Add loading, duplicate-submit prevention, safe errors/retry and session-expiry handling coordinated with #8.
- [ ] Preserve backend offer selection, totals and status; do not independently choose offers or redefine budget arithmetic.
- [ ] Connect the real protected generation API when #8/#9 and the reviewed contract are ready.
- [ ] Record responsive UI and integration verification with Ali and Nasrawy.

#### Acceptance Criteria
- [ ] Forms and reusable results work against the reviewed fixture set before provider integration.
- [ ] Unknown amounts remain unknown; all fixture output is visibly identified as artificial, including simulated live-shaped offer fields.
- [ ] Selected IDs and arithmetic/status values are rendered faithfully.
- [ ] Loading/error/retry behavior and prevention of duplicate generation are verified.
- [ ] Final integration consumes the actual authenticated API with the agreed contract.
- [ ] Ali/Nasrawy review screens incrementally and setup instructions describe mock versus online behavior.

#### Dependencies and Boundaries
FE-01 (#12 / PR #14) is merged. Depend on DES-01/DES-02 (#3/#6) per screen and PLAN-02 (#11) field agreement; live integration depends on BE-02 (#8) and BE-03 (#9). Mock development can proceed against the identified candidate with review changes tracked. The final 2–3 curated offline journeys, network-disabled operation and offline packaging belong to FE-03; a mock renderer does not complete FE-03. No saved-trip, booking or payment UI.

#### Deliverables
Trip form, shared result components, fixture-driven mock development, API integration and verification notes.

### FE-03: Implement Explicit Offline Demo

**Owner:** dyarraed  
**Proposed priority:** P1  
**Start:** Parallel with results UI

**Tasks**

- [ ] Bundle 2–3 complete predefined sample trips with visible DEMO identification.
- [ ] Use the same result components with explicit demo context; prevent fixture fields being presented as real live evidence.
- [ ] Allow offline access without backend generation, Supabase SDK network activity or saving.
- [ ] Lazy-initialize online auth/services only when online flow is selected.

**Acceptance**

- [ ] All demo cases run with network disabled after local dependencies/assets are installed; no online sign-in or provider requests.

**Dependencies:** #12, FE-02 result components; #3/#6 demo design

### QA-01: Verify Core End-to-End Acceptance

**Owner:** Nasrawy1  
**Proposed priority:** P1  
**Start:** Prepare checklist now; execute incrementally

**Tasks**

- [ ] With Adel/Diyar/Ziyad, test real sign-in → form → AI + selected live provider → results.
- [ ] Verify auth/input errors, invalid AI output, deadlines, missing prices, budget outcomes and double-submit prevention.
- [ ] Test offline demo without network; capture sanitized live-provider evidence separately.
- [ ] Record failures and fixes; do not mark optional saving as mandatory.

**Acceptance**

- [ ] Mandatory scope checklist passes with evidence; known failures and open provider constraints are explicit.

**Dependencies:** #8/#9, API-04/API-05, BE-04, FE-02/FE-03

### OPS-01: Package Local Startup & Second-Computer Handover

**Owner:** Nasrawy1  
**Proposed priority:** P1  
**Start:** Prepare during setup; verify before delivery

**Tasks**

- [ ] Agree supported evaluator OS; add startup script(s) for implemented frontend/backend.
- [ ] Document tested prerequisites, dependency installation, environment configuration, ports and troubleshooting.
- [ ] Separate internet-dependent online operation from offline demo; explain initial dependency installation requirement.
- [ ] Test on a second computer; use dedicated demo credentials securely and never package production secrets.

**Acceptance**

- [ ] A teammate can follow README for online and offline-demo runs on a second computer; commands/scripts are actually tested.

**Dependencies:** #12, BE-00; final validation after QA-01 fixes

### F09: Implement Optional Saved Trips

**Owner:** AdelbahaMattar  
**Proposed priority:** P2  
**Start:** Deferred until core passes and feature approved

**Tasks**

- [ ] Finalize HTTP models with Diyar before implementation.
- [ ] Review and execute one public.trips migration in a test project.
- [ ] Implement explicit save/list/reopen through FastAPI only, with verified owner filtering, size/schema validation and historical/unverified labels.
- [ ] Test cross-user isolation and denial of browser Data API access; no update/delete endpoints.

**Acceptance**

- [ ] Only if approved: documented schema/permission/ownership tests pass; generation remains independent.

**Dependencies:** Core acceptance, explicit F-09 prioritization, agreed HTTP schemas; Diyar handles optional UI

### API-06: Implement Optional Second Travel Provider

**Owner:** zee0x  
**Proposed priority:** P2  
**Start:** Deferred until core passes

**Tasks**

- [ ] Implement the other travel category using the same normalized interface and provenance rules.
- [ ] Retest budget selection and missing-category handling with both providers.

**Acceptance**

- [ ] Second provider supplies genuine supported prices without delaying core delivery.

**Dependencies:** QA-01 core pass and explicit prioritization

## Approval and publication boundary

This document is published in the repository. The canonical contract is `docs/api-contracts.md`; the earlier filename migration is already complete.

On 2026-10-15, Nasrawy (Nasrawy1) explicitly approved the scope/general architecture and authorized the documentation and PLAN-01 description alignment. This is not a record of full-team acknowledgment, provider approval, completed implementation, or Project-column changes. PLAN-02 and provider evidence remain separate gates.

Task proposals not explicitly applied remain proposals. Research issues #2, #4 and #5 are recorded closed. Their closure does not establish that #13 corrections or provider compatibility gates under #11 have passed. Keep implementation checklists tied to actual evidence. Optional F-09 migration remains deferred.


**Publication record (2026-10-16):** Nasrawy approved the Phase One preparation review. Issues #1, #6, #8 and #9 were aligned; [BE-00 #15](https://github.com/Nasrawy1/TravelMate/issues/15) was created for Adel under Phase Zero, and [FE-02 #16](https://github.com/Nasrawy1/TravelMate/issues/16) for Diyar under Phase One. Phase assignment here is documented scope, not a Project-field update.

**Phase One preparation:** Mock-result rendering is transferred from FE-01 to FE-02. Phase One planning publication does not approve v0.4, choose providers, mark pending tasks complete or change Project-board status. API-04 (#17), API-05 (#18) and BE-04 (#19) were subsequently created under the approved first batch. FE-03, QA-01 and OPS-01 remain future task proposals unless separately created.
