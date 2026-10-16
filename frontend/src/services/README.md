# Service boundary

Future HTTP clients belong here. FE-01 does not initialize services or make requests.

- Use the agreed FastAPI `/api/v1` contract and snake_case wire fields. API v0.4 is currently a review candidate; confirm adoption before implementing models.
- Keep future public backend configuration in `VITE_API_BASE_URL`.
- Add bearer tokens only when Auth integration is implemented. Keep provider credentials server-side.
- Preserve backend budget decisions and null/unknown amounts; never calculate replacement totals or select offers in the browser.
- Add bounded request timeouts, safe error-envelope handling and explicit loading/error states when requests are introduced. Prevent duplicate submissions and automatic AI-generation retries.
- Initialize online services only within the online journey. Offline demo must use local fixtures without hosted sign-in or backend/provider calls.
