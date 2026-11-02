# TravelMate backend

FastAPI foundation for local development. The application exposes `GET /api/v1/health` and a locally gated BE-02 authentication probe. The probe is disabled by default. Generation, providers and persistence are not implemented.

## Prerequisites and dependencies

The tested local interpreter is **Python 3.14.8**. Commands below run in PowerShell from the `backend/` directory. For a first-time setup, open a terminal at the repository root and enter `Set-Location backend` first.

Create and activate the virtual environment, then install dependencies:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Exact installed dependency versions for the tested environment:

- FastAPI: `0.143.3`
- Starlette: `1.8.0`
- Uvicorn: `0.54.0`
- Pydantic: `2.14.1`
- PyJWT: `2.15.1`
- Cryptography (PyJWT crypto extra): `50.0.2`

## Configure and run

Copy `.env.example` to `.env` and set values for your local environment. The example contains placeholders only. The application does not load `.env` automatically. `CORS_ORIGINS` is a comma-separated list; by default it allows `http://localhost:5173` and `http://127.0.0.1:5173`, matching Vite's default development port. BE-02 verifies Supabase access tokens with the configured JWKS URL, issuer, and audience (`authenticated`). The project must use an asymmetric signing key (ES256 or RS256); do not put signing secrets in backend or frontend environment files.

The application does **not** load `.env` files automatically. Copy the example and set variables in the shell before starting. From `backend/` in PowerShell:

```powershell
Copy-Item .env.example .env
$env:CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
$env:PORT = "8000"
$env:SUPABASE_JWKS_URL = "https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json"
$env:SUPABASE_JWT_ISSUER = "https://<project-ref>.supabase.co/auth/v1"
$env:SUPABASE_JWT_AUDIENCE = "authenticated"
$env:ENABLE_AUTH_PROBE = "false"
python -m uvicorn app.main:app --host 127.0.0.1 --port $env:PORT --no-access-log
```

To use a different Vite port, set `CORS_ORIGINS` to the exact frontend origin, such as `http://localhost:5174`, and set Vite's port to match. `PORT` controls the backend listening port; when changing it, use the same value in the Uvicorn command and any frontend API base URL configured later.

Open `http://127.0.0.1:8000/api/v1/health`; the expected response is `{"status":"ok","service":"travelmate-api"}`. This endpoint reports local backend health only. The frontend currently does not call the backend.

## BE-02 authentication probe

`GET /api/v1/auth/probe` verifies a Supabase bearer token and returns its verified `sub` as `user_id`. This isolated integration probe is disabled by default and is not a product endpoint. To enable it for local verification only, set `$env:ENABLE_AUTH_PROBE = "true"` before starting the server, then restart Uvicorn. Send `Authorization: Bearer <access-token>` from a local test session; never paste tokens into source files, logs, or committed documentation. Set the flag back to `false` (or omit it) after testing. Missing, malformed, expired, invalid-signature, wrong-issuer, and wrong-audience tokens receive the standard 401 error envelope and request ID.

## Tests

Run the test suite from `backend/` with the virtual environment activated:

```powershell
python -m pytest
```

## BE-03 — Generate Endpoint

### Integrated endpoint

`POST /api/v1/trips/generate` requires a Supabase bearer token verified by BE-02. It validates the six public request fields, calls the travel and itinerary adapters in worker threads with request and deadline context, selects eligible offers, and uses BE-04 `calculate_budget` as the authoritative ledger and total calculator. Successful responses follow `docs/api-contracts.md` §4. The endpoint does not persist a trip or return a trip ID.

Adapter errors are mapped to the common error envelope without forwarding raw adapter messages. Unsupported locations map to `400 UNSUPPORTED_LOCATION`, adapter input errors to `422 VALIDATION_ERROR`, timeouts to `504 GENERATION_TIMEOUT`, provider unavailability to `503 PROVIDER_UNAVAILABLE`, rate limits to `429 RATE_LIMITED`, and invalid AI output to `502 AI_GENERATION_FAILED`. If AI succeeds while travel categories are unavailable, generation returns 200 with unavailable categories and warnings.

The travel adapter may write its local cache file (`travelmate_cache.json`) even when `save_report=False`. This cache side effect is outside the trip-persistence boundary; generation does not write to Supabase.

### Reproducible examples

A Supabase bearer access token verified by BE-02 is required. Replace the placeholder with a valid access token:

```powershell
curl.exe -i -X POST http://localhost:8000/api/v1/trips/generate `
  -H "Authorization: Bearer <supabase-access-token>" `
  -H "Content-Type: application/json" `
  -d "{\"departure_city\":\"Istanbul\",\"destination_city\":\"Rome\",\"start_date\":\"2026-12-01\",\"return_date\":\"2026-12-04\",\"adults\":2,\"budget_usd\":1500}"
```
