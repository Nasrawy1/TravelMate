# TravelMate backend

FastAPI foundation for local development. The current application exposes only `GET /api/v1/health`; authentication, generation, providers and persistence are not implemented.

## Prerequisites and dependencies

The tested local interpreter is **Python 3.14.8**. The repository's existing virtual environment is `backend/.venv`.

From the repository root in PowerShell:

```powershell
& .\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

Exact installed dependency versions for the tested environment:

- FastAPI: `0.143.3`
- Starlette: `1.8.0`
- Uvicorn: `0.54.0`
- Pydantic: `2.14.1`

## Configure and run

Copy `.env.example` to `.env` and set values for your local environment. The example contains placeholders only. The current health-only foundation does not use the Supabase settings. `CORS_ORIGINS` is a comma-separated list; by default it allows `http://localhost:5173` and `http://127.0.0.1:5173`, matching Vite's default development port.

The application does not load `.env` files automatically. Set the variables in the shell before starting. For example, from `backend/` in PowerShell:

```powershell
$env:CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
$env:PORT = "8000"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $env:PORT
```

To use a different Vite port, set `CORS_ORIGINS` to the exact frontend origin, such as `http://localhost:5174`, and set Vite's port to match. `PORT` controls the backend listening port; when changing it, use the same value in the Uvicorn command and any frontend API base URL configured later.

Open `http://127.0.0.1:8000/api/v1/health`; the expected response is `{"status":"ok","service":"travelmate-api"}`. This endpoint reports local backend health only. The frontend currently does not call the backend.
