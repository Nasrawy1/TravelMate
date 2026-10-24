"""
TravelMate travel and AI adapters (API-05 #18, API-04 #17).

Public boundaries for BE-03:
  search_travel(trip_request, categories, deadline_at=..., request_id=...)      -> flights + hotels (live providers)
  generate_itinerary(trip_request, selected_offers, travel_availability, estimation_policy, deadline_at=..., request_id=...)
Both are synchronous and never raise: call them with fastapi.concurrency.run_in_threadpool.
Contract and examples: prototypes/travel-adapter/INTEGRATION_GUIDE.md (section 0).
Local CLI, offline tests and evidence: prototypes/travel-adapter/ (travalmate.py there loads this module).
"""
import requests
import json
import os
import re
import sys
import math
import time
import uuid
import shutil
import hashlib
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import groq

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; plain environment variables still work
    load_dotenv = None

# Engine log messages go through this logger (silent by default when imported by a backend).
# main() below turns it on so messages are printed during local testing.
logger = logging.getLogger("TravelMate")
logger.addHandler(logging.NullHandler())

# ==========================================
# 1. ENVIRONMENT CONFIGURATION & CREDENTIALS
# ==========================================
# Local files (.env, .env.exhausted, cache, report) live in TRAVELMATE_HOME. Default: the backend/ folder, so the
# backend reads backend/.env; the prototype CLI and tests set it to prototypes/travel-adapter/.
BASE_DIR = os.path.abspath(os.environ.get("TRAVELMATE_HOME")
                           or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ENV_FILE = os.path.join(BASE_DIR, ".env")
if load_dotenv:
    load_dotenv(ENV_FILE)

def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")

def _env_number(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)

SKYSCANNER_HOST = "skyscanner-scraper-api.p.rapidapi.com"
BOOKING_HOST = "booking-com15.p.rapidapi.com"
EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/USD"  # Direct public API, no key required
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
AI_TEMPERATURE = 0.1

CACHE_FILE = os.path.join(BASE_DIR, "travelmate_cache.json")
REPORT_FILE = os.path.join(BASE_DIR, "travelmate_final_report.json")
CACHE_TTL_HOURS = _env_number("TRAVELMATE_CACHE_TTL_HOURS", 12)  # Fresh-cache lifetime for provider responses
CACHE_MAX_AGE_HOURS = 168           # Entries older than this are deleted from the cache file
DESTINATION_ID_TTL_HOURS = 720      # Verified city -> provider ID lookups change rarely
FX_CACHE_TTL_HOURS = 12
FX_MAX_RATE_AGE_HOURS = 48          # Conversion policy: rates older than this are not used

# Flight mode (see INTEGRATION_GUIDE.md section 2):
#   "disabled"   -> flights category is "unavailable" / "not_configured"; no flight provider calls (default).
#   "live"       -> Google Flights live round-trip search: real dates, all-adult totals, real departure times.
#   "indicative" -> Skyscanner cached quotes; ONLY exact-date quotes are selectable, labeled indicative.
FLIGHT_MODE = os.getenv("TRAVELMATE_FLIGHT_MODE", "disabled").strip().lower()
GOOGLE_FLIGHTS_HOST = "google-flights2.p.rapidapi.com"
GOOGLE_FLIGHTS_TIMEOUT_SECONDS = 20   # One-way searchFlights measured 2.4-3 s (worst seen ~25 s); timeouts not retried
GOOGLE_FLIGHTS_RETURN_OPTIONS = 3     # Public round-trip offers (cheapest combinations of the per-leg results)
# Local maintenance: remove a key from the local .env after quota exhaustion or an auth error (never mid-request)
PRUNE_DEAD_KEYS = _env_flag("TRAVELMATE_PRUNE_DEAD_KEYS", False)
# LOCAL DEVELOPMENT ONLY: move a dead key to .env.exhausted and continue with the next key in the SAME request.
# Must stay false in shared / deployed environments: issue #18 forbids rotating keys to bypass provider limits.
LOCAL_KEY_ROTATION = _env_flag("TRAVELMATE_LOCAL_KEY_ROTATION", False)
EXHAUSTED_KEYS_FILE = os.path.join(BASE_DIR, ".env.exhausted")

# Contract defaults (docs/api-contracts.md section 5)
DEFAULT_DEADLINE_SECONDS = _env_number("TRAVELMATE_DEFAULT_DEADLINE_SECONDS", 60)
PER_ATTEMPT_TIMEOUT_SECONDS = 10    # Travel lookup timeout per request
MAX_TRAVEL_RETRIES = 1              # At most ONE retry per idempotent travel lookup (transient failure or Retry-After)
RETRY_BACKOFF_SECONDS = 1.0
MAX_RETRY_AFTER_SECONDS = 10        # Provider Retry-After guidance is honored only up to this value
AI_TIMEOUT_SECONDS = 35             # AI timeout per attempt
AI_MIN_SECONDS_REQUIRED = 5         # The AI call is skipped (timeout) if less time than this is left
AI_RESERVED_SECONDS = 25            # Engine: travel searches must finish this long before deadline_at
AI_MAX_COMPLETION_TOKENS = 8192

MIN_ADULTS, MAX_ADULTS = 1, 4       # Public contract range
MIN_NIGHTS, MAX_NIGHTS = 1, 7       # Public contract range
DEFAULT_ROOMS = 1                   # Adapter-internal (rooms are not a public request field)
HOTEL_COVERAGE_RADIUS_KM = 60

PROVIDER_INFO = {
    "skyscanner_route": {
        "label": "Flight Route Quotes",
        "provider": "Skyscanner Scraper API (RapidAPI marketplace)",
        "integration_type": "rapidapi_third_party",
        "upstream_source": "skyscanner.net route pages (cached fare quotes, not a live fare search)",
        "host": SKYSCANNER_HOST,
        "path": "/v1/skyscanner/route",
        "key_env_prefix": "SKYSCANNER"
    },
    "google_flights_search": {
        "label": "Google Flights Search",
        "provider": "Google Flights (google-flights2, RapidAPI marketplace)",
        "integration_type": "rapidapi_third_party",
        "upstream_source": "google.com/travel/flights live one-way search (one call per direction)",
        "host": GOOGLE_FLIGHTS_HOST,
        "path": "/api/v1/searchFlights",
        "key_env_prefix": "GOOGLE_FLIGHTS",
        "timeout_seconds": GOOGLE_FLIGHTS_TIMEOUT_SECONDS,
        "retry_on_timeout": False  # A slow search is not retried: it would double the user's waiting time
    },
    "google_flights_airport": {
        "label": "Google Flights City Lookup",
        "provider": "Google Flights (google-flights2, RapidAPI marketplace)",
        "integration_type": "rapidapi_third_party",
        "upstream_source": "google.com/travel/flights airport and city search",
        "host": GOOGLE_FLIGHTS_HOST,
        "path": "/api/v1/searchAirport",
        "key_env_prefix": "GOOGLE_FLIGHTS",
        "timeout_seconds": GOOGLE_FLIGHTS_TIMEOUT_SECONDS,
        "retry_on_timeout": False
    },
    "booking_destination": {
        "label": "Hotel Destination Lookup",
        "provider": "Booking COM booking-com15 (RapidAPI marketplace)",
        "integration_type": "rapidapi_third_party",
        "upstream_source": "booking.com destination search",
        "host": BOOKING_HOST,
        "path": "/api/v1/hotels/searchDestination",
        "key_env_prefix": "BOOKING"
    },
    "booking_hotels": {
        "label": "Hotel Search",
        "provider": "Booking COM booking-com15 (RapidAPI marketplace)",
        "integration_type": "rapidapi_third_party",
        "upstream_source": "booking.com live hotel availability search",
        "host": BOOKING_HOST,
        "path": "/api/v1/hotels/searchHotels",
        "key_env_prefix": "BOOKING"
    }
}
HOTEL_SOURCE_LABEL = "Booking COM booking-com15 (RapidAPI)"
FLIGHT_SOURCE_LABEL = "Skyscanner Scraper API (RapidAPI, cached route quotes)"
GOOGLE_FLIGHTS_SOURCE_LABEL = "Google Flights (google-flights2, RapidAPI)"

def load_key_pool(key_env_prefix):
    """
    Reads the keys of one service from the environment. Supported forms (merged, duplicates removed):
      <PREFIX>_RAPIDAPI_KEYS = "key1,key2"      and/or      <PREFIX>_RAPIDAPI_KEY_1 ... <PREFIX>_RAPIDAPI_KEY_10
    Only the FIRST key is used for requests. Placeholder values from .env.example are ignored.
    """
    candidates = os.getenv(f"{key_env_prefix}_RAPIDAPI_KEYS", "").split(",")
    candidates += [os.getenv(f"{key_env_prefix}_RAPIDAPI_KEY_{i}", "") for i in range(1, 11)]
    keys = []
    for key in (c.strip() for c in candidates):
        if key and not key.lower().startswith(("your_", "paste_", "<")) and " " not in key and key not in keys:
            keys.append(key)
    return keys

# ==========================================
# 2. CREDENTIAL REDACTION (LOGS, ERRORS & EVIDENCE)
# ==========================================
REDACTED = "***REDACTED***"
SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),                              # Groq keys
    re.compile(r"\b[0-9a-f]{10}msh[0-9a-f]{10,}jsn[0-9a-f]{8,}\b"),  # RapidAPI keys
]
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(x-rapidapi-key|api[_-]?key|authorization|bearer)(['\"]?\s*[:=]?\s*['\"]?\s*)([A-Za-z0-9_\-\.]{12,})")

def _configured_secrets():
    secrets = [os.getenv("GROQ_API_KEY", "").strip()]
    for info in PROVIDER_INFO.values():
        secrets += load_key_pool(info["key_env_prefix"])
    return [s for s in set(secrets) if len(s) >= 8]

def redact(text):
    """Removes every configured credential and anything that looks like an API key from a string."""
    text = str(text)
    for secret in _configured_secrets():
        text = text.replace(secret, REDACTED)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return SECRET_ASSIGNMENT_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)

def sanitize(value):
    """Recursively redacts credentials inside dicts / lists / strings (used for errors and evidence)."""
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return redact(value)
    return value

def mask_key(key):
    return f"...{key[-4:]}" if key and len(key) > 8 else "***"

class RedactingFilter(logging.Filter):
    """Makes sure no credential ever reaches a log handler, including exception tracebacks."""
    def filter(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
            record.exc_text = None
        record.msg = redact(message)
        record.args = None
        return True

logger.addFilter(RedactingFilter())

# ==========================================
# 3. ERROR ENVELOPE & WARNINGS
# ==========================================
# Internal error codes. Travel codes match adapter-contracts.md reason_code values; AI codes match the
# AI adapter failure codes (timeout, rate_limited, unavailable, invalid_output).
ERROR_MESSAGES = {
    "invalid_input": "The request is invalid. Please check the highlighted fields.",
    "unsupported_search": "This search is outside the supported provider coverage.",
    "not_configured": "This travel category is not configured for live prices.",
    "no_results": "No offers matching the requested dates, destination and travelers were found.",
    "rate_limited": "The provider rate limit was reached. Please try again later.",
    "timeout": "The request did not finish before the deadline.",
    "auth_error": "The provider rejected the configured credentials.",
    "invalid_response": "The provider returned an unexpected response.",
    "provider_error": "The provider is currently failing. Please try again later.",
    "unavailable": "This service is currently unavailable.",
    "invalid_output": "The AI output failed validation and was not published.",
    "internal_error": "An internal error occurred. Please try again later."
}
AI_ERROR_CODES = {"timeout", "rate_limited", "unavailable", "invalid_output"}

class TravelMateError(Exception):
    """Typed adapter error. Its message and details are always user-safe (never raw exception text)."""
    def __init__(self, code, message=None, details=None, retry_after_seconds=None, transient=False,
                 quota_exhausted=False):
        code = code if code in ERROR_MESSAGES else "internal_error"
        super().__init__(message or ERROR_MESSAGES[code])
        self.code = code
        self.message = message or ERROR_MESSAGES[code]
        self.details = details or {}
        self.retry_after_seconds = retry_after_seconds
        self.transient = transient
        self.quota_exhausted = quota_exhausted

    def to_envelope(self):
        return build_error(self.code, self.message)

def build_error(code, message=None):
    """Contract error shape: {code, message}. Diagnostics are returned separately and sanitized."""
    code = code if code in ERROR_MESSAGES else "internal_error"
    return {"code": code, "message": redact(message or ERROR_MESSAGES[code])}

def build_warning(code, message):
    """Contract warning shape: {code, message} (docs/api-contracts.md section 5)."""
    return {"code": code, "message": redact(message)}

# ==========================================
# 4. DEADLINE & NUMBER HELPERS
# ==========================================
def utc_now():
    return datetime.now(timezone.utc)

def utc_now_iso():
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")

def _today_utc():
    """Contract validation reference: today's UTC calendar date (separate function so tests can freeze it)."""
    return utc_now().date()

def resolve_deadline(deadline_at=None):
    """Accepts None (default budget), an aware/naive datetime or an ISO-8601 string. Naive values are treated as UTC."""
    if deadline_at is None:
        return utc_now() + timedelta(seconds=DEFAULT_DEADLINE_SECONDS)
    if isinstance(deadline_at, datetime):
        deadline = deadline_at
    else:
        try:
            deadline = datetime.fromisoformat(str(deadline_at).strip().replace("Z", "+00:00"))
        except ValueError:
            raise TravelMateError("invalid_input", "deadline_at must be an ISO-8601 datetime.",
                                  {"fields": [{"field": "deadline_at", "message": "Invalid ISO-8601 datetime."}]})
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline.astimezone(timezone.utc)

def seconds_left(deadline):
    return (deadline - utc_now()).total_seconds()

def _has_time_for(deadline, seconds_needed):
    return seconds_left(deadline) > seconds_needed

_sleep = time.sleep  # Indirection so tests can skip real waiting

def round_money(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def valid_amount(value, allow_zero=False):
    """Returns the amount as float, or None for missing, non-numeric, negative, NaN or Infinity values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        return None
    return value

def parse_iso_date(value):
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

def normalize_utc_timestamp(value):
    """Returns 'YYYY-MM-DDTHH:MM:SSZ' for provider timestamps such as '2026-10-08T04:50Z', else None."""
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def new_request_id():
    return f"tm-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

# ==========================================
# 5. LOCAL CACHE (THREAD & PROCESS SAFE)
# ==========================================
_cache_thread_lock = threading.RLock()

class _FileLock:
    """Cross-process lock based on an exclusive lock file (works on Windows and Linux)."""
    def __init__(self, path, timeout=5.0, stale_after=30.0):
        self.path = path
        self.timeout = timeout
        self.stale_after = stale_after
        self.fd = None

    def __enter__(self):
        start = time.monotonic()
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > self.stale_after:
                        os.remove(self.path)  # Lock left behind by a crashed process
                        continue
                except OSError:
                    pass
                if time.monotonic() - start > self.timeout:
                    raise TimeoutError("File lock timeout")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            os.close(self.fd)
        try:
            os.remove(self.path)
        except OSError:
            pass

def atomic_write_text(path, text):
    """Writes text to a temp file in the same folder, then atomically replaces the target file."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=folder, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        for attempt in range(5):
            try:
                os.replace(temp_path, path)
                return
            except PermissionError:  # Windows: target briefly opened by another reader
                time.sleep(0.05 * (attempt + 1))
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def atomic_write_json(path, data):
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))

def _read_cache_unlocked():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        logger.warning("[!] Cache file is unreadable. Starting with an empty cache...")
        return {}

def _entry_age_hours(entry):
    try:
        saved_at = datetime.fromisoformat(str(entry.get("saved_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if saved_at.tzinfo is None:
        saved_at = saved_at.replace(tzinfo=timezone.utc)
    return (utc_now() - saved_at).total_seconds() / 3600

def build_cache_key(url, querystring):
    """
    Builds a unique key from the endpoint URL and search parameters.
    The API key is NOT part of the cache key, so a result is reused whichever key fetched it.
    """
    raw_key = json.dumps({"url": url, "params": querystring}, sort_keys=True)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

def cache_get(cache_key, ttl_hours):
    """Returns a fresh cache entry or None. Expired entries are never served."""
    try:
        with _cache_thread_lock, _FileLock(CACHE_FILE + ".lock"):
            entry = _read_cache_unlocked().get(cache_key)
    except TimeoutError:
        logger.warning("[!] Cache is locked by another process. Skipping cache read...")
        return None
    if not isinstance(entry, dict) or "response" not in entry:
        return None
    age = _entry_age_hours(entry)
    return entry if age is not None and age <= ttl_hours else None

def cache_put(cache_key, service_name, response):
    """Read-merge-write under a thread lock + process lock, with an atomic file replace (never a half-written file)."""
    try:
        with _cache_thread_lock, _FileLock(CACHE_FILE + ".lock"):
            cache = _read_cache_unlocked()
            # Drop entries older than the maximum age so the cache file does not grow forever
            cache = {k: v for k, v in cache.items()
                     if isinstance(v, dict) and (_entry_age_hours(v) or CACHE_MAX_AGE_HOURS + 1) <= CACHE_MAX_AGE_HOURS}
            cache[cache_key] = {"service": service_name, "saved_at": utc_now_iso(), "response": response}
            atomic_write_json(CACHE_FILE, cache)
    except (TimeoutError, OSError) as e:
        logger.warning(f"[!] Could not write cache file ({type(e).__name__}). Continuing without caching...")

# ==========================================
# 6. LOCAL .ENV DEAD-KEY PRUNING (NO RUNTIME KEY ROTATION)
# ==========================================
# Each request uses ONLY the first configured key. If that key fails with an exhausted quota or an auth error,
# the request fails with that error (no retry with another key). When TRAVELMATE_PRUNE_DEAD_KEYS is enabled,
# the dead key is removed from the local .env (a .env.bak backup is written first), so the next key becomes the
# primary key for LATER requests. Deployments without a local .env file are never modified.
_env_lock = threading.Lock()
ENV_LINE_PATTERN = re.compile(r"^(\s*)([A-Z0-9_]+)(\s*=\s*)(.*?)(\s*)$")

def _archive_dead_key(key_env_prefix, dead_key, reason, reset_at):
    """Appends the dead key to .env.exhausted (copy-paste ready, so it can be restored after the quota resets)."""
    header = "# Keys moved out of .env by TravelMate (local only, never commit). Move a key back after its quota resets.\n"
    entry = (f"# {utc_now_iso()} | {key_env_prefix} | {reason}"
             + (f" | quota resets around {reset_at}" if reset_at else "") + "\n"
             + f"{key_env_prefix}_RAPIDAPI_KEYS={dead_key}\n")
    existing = ""
    if os.path.exists(EXHAUSTED_KEYS_FILE):
        with open(EXHAUSTED_KEYS_FILE, "r", encoding="utf-8") as f:
            existing = f.read()
    atomic_write_text(EXHAUSTED_KEYS_FILE, (existing or header) + entry)

def prune_dead_key(key_env_prefix, dead_key, reason, env_path=None, reset_at=None):
    """
    Removes dead_key from <PREFIX>_RAPIDAPI_KEYS / <PREFIX>_RAPIDAPI_KEY_n in the local .env (backup: .env.bak) and
    archives it in .env.exhausted with the reason and the expected quota reset time. Returns True if pruned.
    """
    env_path = env_path or ENV_FILE
    if not dead_key or not os.path.exists(env_path):
        return False
    list_name = f"{key_env_prefix}_RAPIDAPI_KEYS"
    indexed = re.compile(rf"^{key_env_prefix}_RAPIDAPI_KEY_\d+$")
    try:
        with _env_lock, _FileLock(env_path + ".lock"):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            new_lines, changed = [], False
            for line in lines:
                match = ENV_LINE_PATTERN.match(line)
                if match and not line.lstrip().startswith("#"):
                    name, value = match.group(2), match.group(4)
                    if name == list_name:
                        keys = [k.strip() for k in value.split(",") if k.strip()]
                        if dead_key in keys:
                            keys.remove(dead_key)
                            line = f"{match.group(1)}{name}{match.group(3)}{','.join(keys)}"
                            changed = True
                    elif indexed.match(name) and value.strip() == dead_key:
                        changed = True
                        continue  # Drop the dead indexed key line
                new_lines.append(line)
            if not changed:
                return False
            shutil.copyfile(env_path, env_path + ".bak")
            atomic_write_text(env_path, "\n".join(new_lines) + "\n")
            _archive_dead_key(key_env_prefix, dead_key, reason, reset_at)
    except (OSError, TimeoutError) as e:
        logger.error(f"[-] Could not prune the dead key from .env ({type(e).__name__}).")
        return False

    # Keep the running process consistent with the file for LATER requests (the current request already failed)
    current = [k.strip() for k in os.getenv(list_name, "").split(",") if k.strip() and k.strip() != dead_key]
    os.environ[list_name] = ",".join(current)
    for i in range(1, 11):
        if os.getenv(f"{key_env_prefix}_RAPIDAPI_KEY_{i}", "").strip() == dead_key:
            os.environ.pop(f"{key_env_prefix}_RAPIDAPI_KEY_{i}", None)
    remaining = load_key_pool(key_env_prefix)
    logger.warning(f"[!] {key_env_prefix} key {mask_key(dead_key)} pruned from .env ({reason}). "
                   f"{len(remaining)} key(s) left; next primary: {mask_key(remaining[0]) if remaining else 'none'}. "
                   "Moved to .env.exhausted (backup: .env.bak).")
    return True

def _quota_reset_at(error):
    """Expected quota reset time from RapidAPI's x-ratelimit-requests-reset header (seconds), if present."""
    try:
        seconds = float((error.details.get("rate_limit") or {}).get("x-ratelimit-requests-reset"))
        return (utc_now() + timedelta(seconds=seconds)).isoformat(timespec="minutes").replace("+00:00", "Z")
    except (TypeError, ValueError):
        return None

# ==========================================
# 7. PROVIDER REQUEST HANDLER (CLASSIFIED ERRORS & ONE BOUNDED RETRY)
# ==========================================
def _record_provider_call(evidence, service_key, provenance, payload):
    if isinstance(evidence, dict):
        evidence.setdefault("provider_calls", []).append({
            "service": service_key,
            "provenance": json.loads(json.dumps(provenance)),
            "response": payload
        })

def _rate_limit_headers(response):
    return {k.lower(): v for k, v in response.headers.items()
            if k.lower().startswith("x-ratelimit") and len(str(v)) < 40}

def _safe_provider_message(value):
    return redact(str(value))[:200] if value else None

def _body_message(response):
    try:
        body = response.json()
        if isinstance(body, dict):
            return _safe_provider_message(body.get("message") or body.get("error"))
    except ValueError:
        pass
    return _safe_provider_message(response.text[:200])

def _classify_provider_message(message):
    text = str(message or "").lower()
    if any(word in text for word in ["quota", "too many requests", "rate limit", "exceeded"]):
        return "rate_limited"
    if any(word in text for word in ["not subscribed", "invalid api key", "unauthorized", "forbidden"]):
        return "auth_error"
    return "provider_error"

def _is_quota_exhausted(message):
    text = str(message or "").lower()
    return "quota" in text and any(word in text for word in ["monthly", "daily", "plan", "exceeded"])

def _parse_retry_after(response):
    try:
        value = float(response.headers.get("Retry-After", ""))
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None

def _attempt_request(url, host, api_key, params, deadline, per_attempt_timeout=None):
    """One HTTP attempt. Returns (payload, meta) or raises a classified TravelMateError."""
    timeout = min(per_attempt_timeout or PER_ATTEMPT_TIMEOUT_SECONDS, seconds_left(deadline))
    if timeout <= 0.5:
        raise TravelMateError("timeout", details={"reason": "deadline_reached"})
    headers = {"x-rapidapi-host": host, "x-rapidapi-key": api_key, "accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.Timeout:
        raise TravelMateError("timeout", details={"reason": "provider_timeout"}, transient=True)
    except requests.RequestException:
        raise TravelMateError("provider_error", details={"reason": "connection_error"}, transient=True)

    meta = {"http_status": response.status_code, "rate_limit": _rate_limit_headers(response)}
    status = response.status_code

    if status == 200:
        try:
            payload = response.json()
        except ValueError:
            raise TravelMateError("invalid_response", details={"reason": "non_json_body", **meta})
        if isinstance(payload, dict) and payload.get("status") is False:
            # Hidden provider error inside a 200 OK response
            message = payload.get("message")
            raise TravelMateError(_classify_provider_message(message),
                                  details={"reason": "provider_status_false",
                                           "provider_message": _safe_provider_message(message), **meta},
                                  quota_exhausted=_is_quota_exhausted(message))
        if not isinstance(payload, (dict, list)):
            raise TravelMateError("invalid_response", details={"reason": "unexpected_body_type", **meta})
        return payload, meta

    message = _body_message(response)
    details = {"provider_message": message, **meta}
    if status == 429:
        raise TravelMateError("rate_limited", details={"reason": "http_429", **details},
                              retry_after_seconds=_parse_retry_after(response),
                              quota_exhausted=_is_quota_exhausted(message))
    if status in (401, 403):
        if _is_quota_exhausted(message):
            raise TravelMateError("rate_limited", details={"reason": "quota_exhausted", **details}, quota_exhausted=True)
        raise TravelMateError("auth_error", details={"reason": f"http_{status}", **details})
    if status in (400, 404, 422):
        raise TravelMateError("unsupported_search", "The provider rejected these search parameters.",
                              details={"reason": f"http_{status}", **details})
    if status >= 500:
        raise TravelMateError("provider_error", details={"reason": f"http_{status}", **details}, transient=True)
    raise TravelMateError("invalid_response", details={"reason": f"unexpected_http_{status}", **details})

def provider_get(service_key, params, deadline, cache_ttl_hours=None, cache_mode="default", evidence=None):
    """
    Sends a GET request to a RapidAPI provider and returns (payload, provenance).
      1. Local cache first (cache_mode "default"). "refresh" skips the read but stores the result, "off" does neither.
      2. Single key: only the first configured key is used. No key rotation inside a request.
      3. At most ONE retry, only for transient failures or a Retry-After (<= 10 s) that fits deadline_at.
      4. Quota exhaustion / auth errors fail the request and (optionally) prune the dead key from the local .env.
    """
    info = PROVIDER_INFO[service_key]
    url = f"https://{info['host']}{info['path']}"
    ttl = CACHE_TTL_HOURS if cache_ttl_hours is None else cache_ttl_hours
    cache_key = build_cache_key(url, params)
    provenance = {
        "provider": info["provider"],
        "integration_type": info["integration_type"],
        "upstream_source": info["upstream_source"],
        "endpoint": f"GET {info['path']}",
        "query_parameters": dict(params),
        "retrieved_at": None,
        "cache_status": "miss",
        "http_status": None,
        "attempts": 0,
        "rate_limit": {}
    }

    if cache_mode == "default":
        entry = cache_get(cache_key, ttl)
        if entry:
            provenance.update(retrieved_at=entry["saved_at"], cache_status="hit")
            logger.info(f"[+] {info['label']} loaded from local cache (no API quota used).")
            _record_provider_call(evidence, service_key, provenance, entry["response"])
            return entry["response"], provenance

    keys = load_key_pool(info["key_env_prefix"])
    if not keys:
        raise TravelMateError("auth_error", f"No API key is configured for {info['label']}.",
                              {"reason": "missing_credentials", "env_variable": f"{info['key_env_prefix']}_RAPIDAPI_KEYS"})
    # Default: only the first key. LOCAL_KEY_ROTATION (local development only) walks the remaining keys.
    key_pool = keys if LOCAL_KEY_ROTATION else keys[:1]
    last_error = None
    for slot, api_key in enumerate(key_pool, start=1):
        retries_used = 0
        while True:
            provenance["attempts"] += 1
            try:
                payload, meta = _attempt_request(url, info["host"], api_key, params, deadline,
                                                 info.get("timeout_seconds"))
            except TravelMateError as error:
                last_error = error
                provenance["http_status"] = error.details.get("http_status")
                provenance["rate_limit"] = error.details.get("rate_limit", {})
                no_timeout_retry = error.code == "timeout" and info.get("retry_on_timeout") is False
                if retries_used < MAX_TRAVEL_RETRIES and not no_timeout_retry:
                    wait = None
                    if error.transient:
                        wait = RETRY_BACKOFF_SECONDS
                    elif (error.code == "rate_limited" and not error.quota_exhausted
                          and error.retry_after_seconds is not None and error.retry_after_seconds <= MAX_RETRY_AFTER_SECONDS):
                        wait = error.retry_after_seconds
                    if wait is not None and _has_time_for(deadline, wait + 1):
                        retries_used += 1
                        logger.warning(f"[!] {info['label']} {error.code}. Single retry in {wait:.0f}s...")
                        _sleep(wait)
                        continue
                break  # This key failed; decide below whether another key may be tried

            provenance.update(meta, retrieved_at=utc_now_iso(), key_slot=slot,
                              cache_status="refresh" if cache_mode == "refresh" else "miss")
            logger.info(f"[+] {info['label']} fetched successfully (200 OK, key slot #{slot}, attempt {provenance['attempts']}).")
            if cache_mode != "off":
                cache_put(cache_key, service_key, payload)
            _record_provider_call(evidence, service_key, provenance, payload)
            return payload, provenance

        dead_key = last_error.quota_exhausted or (last_error.code == "auth_error"
                                                  and last_error.details.get("reason") != "missing_credentials")
        if dead_key and (PRUNE_DEAD_KEYS or LOCAL_KEY_ROTATION):
            prune_dead_key(info["key_env_prefix"], api_key,
                           "quota_exhausted" if last_error.quota_exhausted else "auth_error",
                           reset_at=_quota_reset_at(last_error))
        if dead_key and slot < len(key_pool) and _has_time_for(deadline, 1):
            logger.warning(f"[!] LOCAL KEY ROTATION: {info['label']} key slot #{slot} is dead ({last_error.code}). "
                           f"Continuing with key slot #{slot + 1}...")
            continue
        break

    logger.error(f"[-] {info['label']} failed: {last_error.code} ({last_error.details.get('reason')}).")
    last_error.details.setdefault("service", info["label"])
    raise last_error

# ==========================================
# 8. CURRENCY CONVERSION POLICY (EVERYTHING TO USD)
# ==========================================
# Policy: USD amounts are used as-is. Other currencies are converted ONLY with live rates from
# open.er-api.com that are at most FX_MAX_RATE_AGE_HOURS old; every conversion records rate, source and time.
# If no valid rate exists, the quote is excluded and a warning is returned. There are no hardcoded fallback rates.
FX_SOURCE = "ExchangeRate-API open access (open.er-api.com)"
# PR #25 review, item 4: until the team approves a conversion policy, conversion is OFF. Non-USD prices are excluded
# with a CURRENCY_UNAVAILABLE warning and no exchange-rate request is made. Both live providers are queried in USD.
FX_CONVERSION_ENABLED = os.getenv("TRAVELMATE_FX_CONVERSION", "false").strip().lower() == "true"
FX_DISABLED_NOTE = "not priced in USD (currency conversion is disabled until a conversion policy is approved)"

def fetch_usd_exchange_rates(deadline, cache_mode="default", evidence=None):
    cache_key = build_cache_key(EXCHANGE_RATE_URL, {})
    provenance = {"provider": FX_SOURCE, "integration_type": "direct_public_api", "endpoint": "GET /v6/latest/USD",
                  "query_parameters": {}, "retrieved_at": None, "cache_status": "miss"}
    payload = None
    if cache_mode == "default":
        entry = cache_get(cache_key, FX_CACHE_TTL_HOURS)
        if entry:
            payload = entry["response"]
            provenance.update(retrieved_at=entry["saved_at"], cache_status="hit")

    if payload is None:
        timeout = min(PER_ATTEMPT_TIMEOUT_SECONDS, seconds_left(deadline))
        if timeout <= 0.5:
            return {"available": False, "reason": "deadline_reached", "provenance": provenance}
        try:
            response = requests.get(EXCHANGE_RATE_URL, timeout=timeout)
            payload = response.json() if response.status_code == 200 else None
        except (requests.RequestException, ValueError):
            payload = None
        if not isinstance(payload, dict):
            logger.warning("[!] Exchange rate service unreachable. Non-USD quotes will be excluded.")
            return {"available": False, "reason": "rate_service_unreachable", "provenance": provenance}
        provenance.update(retrieved_at=utc_now_iso(), cache_status="refresh" if cache_mode == "refresh" else "miss")
        if cache_mode != "off":
            cache_put(cache_key, "exchange_rates", payload)

    _record_provider_call(evidence, "exchange_rates", provenance, payload)
    rates = payload.get("rates")
    if payload.get("result") != "success" or not isinstance(rates, dict):
        return {"available": False, "reason": "invalid_rate_response", "provenance": provenance}
    updated_unix = payload.get("time_last_update_unix")
    if not isinstance(updated_unix, (int, float)) or time.time() - updated_unix > FX_MAX_RATE_AGE_HOURS * 3600:
        return {"available": False, "reason": "rates_too_old", "provenance": provenance}
    return {"available": True, "rates": rates, "rate_timestamp": payload.get("time_last_update_utc"),
            "retrieved_at": provenance["retrieved_at"], "provenance": provenance}

class LazyExchangeRates:
    """Fetches exchange rates only when a non-USD amount actually needs converting."""
    def __init__(self, deadline, cache_mode="default", evidence=None):
        self.deadline = deadline
        self.cache_mode = cache_mode
        self.evidence = evidence
        self.policy = None

    def __call__(self):
        if self.policy is None:
            self.policy = fetch_usd_exchange_rates(self.deadline, self.cache_mode, self.evidence)
        return self.policy

def convert_to_usd(amount, currency, fx):
    """
    Returns (usd_amount, conversion). conversion follows adapter-contracts.md: null for USD, otherwise
    {source, rate_to_usd, converted_at, ...}. usd_amount is None when the policy does not allow the conversion.
    """
    currency = str(currency or "").strip().upper()
    if not currency:
        return None, {"status": "unknown_currency"}
    if currency == "USD":
        return round_money(amount), None
    if not FX_CONVERSION_ENABLED:
        return None, {"status": "not_usd", "original_currency": currency, "reason": "conversion_policy_not_approved"}
    policy = fx()
    if not policy.get("available"):
        return None, {"status": "rates_unavailable", "original_currency": currency, "reason": policy.get("reason")}
    rate_per_usd = policy["rates"].get(currency)
    if valid_amount(rate_per_usd) is None:
        return None, {"status": "unsupported_currency", "original_currency": currency}
    return round_money(amount / rate_per_usd), {
        "source": FX_SOURCE,
        "rate_to_usd": round(1 / rate_per_usd, 8),  # USD per 1 unit of the original currency
        "converted_at": policy["retrieved_at"],
        "rate_timestamp": policy["rate_timestamp"]
    }

# ==========================================
# 9. SUPPORTED CITIES, AIRPORTS & COVERAGE LIMITS
# ==========================================
# Google search IDs (google_city_id), no lookup request at run time:
#   - the first 12 cities: Google city IDs verified live with searchAirport on 2026-10-21/23
#     (evidence/google-flights-city-lookup-20261023/);
#   - cities added 2026-10-24 with SEVERAL airports: Google city IDs (Freebase IDs from Wikidata, the same source that
#     matched all first 12 cities) verified live with searchAirport (evidence/city-table-20261024/);
#   - cities added 2026-10-24 with ONE airport: the airport code itself, which gives the same flights as a city search
#     and cannot point to a wrong area (e.g., Google's "Alexandria" area lists CAI and the closed ALY, not HBE).
# Time zones and airport cities come from the airportsdata table; city centers from Wikidata.
# Canonical city labels (public request values). "booking_dest_id" is either pinned (verified value) or resolved once
# through Booking.com searchDestination, verified (type = city, same country code and name) and cached.
# Cities that are not listed here are unsupported searches.
SUPPORTED_CITIES = {
    "Istanbul": {"country_code": "tr", "airports": ["IST", "SAW"], "timezone": "Europe/Istanbul",
                 "center": (41.0082, 28.9784), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "/m/09949m"},  # Verified 2026-10-21 (searchAirport: IST + SAW)
    "Cairo": {"country_code": "eg", "airports": ["CAI"], "timezone": "Africa/Cairo",
              "center": (30.0444, 31.2357), "booking_dest_id": "-290692", "aliases": [],
             "google_city_id": "/m/01w2v"},  # Verified 2026-10-17
    "Rome": {"country_code": "it", "airports": ["FCO", "CIA"], "timezone": "Europe/Rome",
             "center": (41.9028, 12.4964), "booking_dest_id": None, "aliases": ["roma"],
            "google_city_id": "/m/06c62"},
    "Riyadh": {"country_code": "sa", "airports": ["RUH"], "timezone": "Asia/Riyadh",
               "center": (24.7136, 46.6753), "booking_dest_id": None, "aliases": ["ar riyadh", "al riyadh"],
              "google_city_id": "/m/0dlm_"},
    "Jeddah": {"country_code": "sa", "airports": ["JED"], "timezone": "Asia/Riyadh",
               "center": (21.4858, 39.1925), "booking_dest_id": None, "aliases": ["jedda", "jiddah"],
              "google_city_id": "/m/01pk8b"},
    "Dubai": {"country_code": "ae", "airports": ["DXB", "DWC"], "timezone": "Asia/Dubai",
              "center": (25.2048, 55.2708), "booking_dest_id": None, "aliases": [],
              "google_city_id": "/m/01f08r"},  # Verified 2026-10-23 (also covers SHJ / AUH: other cities)
    "Doha": {"country_code": "qa", "airports": ["DOH"], "timezone": "Asia/Qatar",
             "center": (25.2854, 51.5310), "booking_dest_id": None, "aliases": [],
            "google_city_id": "/m/0f2yw"},
    "Amman": {"country_code": "jo", "airports": ["AMM"], "timezone": "Asia/Amman",
              "center": (31.9539, 35.9106), "booking_dest_id": None, "aliases": [],
             "google_city_id": "/m/0c7zf"},
    "Baghdad": {"country_code": "iq", "airports": ["BGW"], "timezone": "Asia/Baghdad",
                "center": (33.3152, 44.3661), "booking_dest_id": None, "aliases": [],
               "google_city_id": "/m/01fqm"},
    "Erbil": {"country_code": "iq", "airports": ["EBL"], "timezone": "Asia/Baghdad",
              "center": (36.1911, 44.0092), "booking_dest_id": None, "aliases": ["arbil", "hawler"],
             "google_city_id": "/m/03n7br"},
    "London": {"country_code": "gb", "airports": ["LHR", "LGW", "STN", "LTN", "LCY", "SEN"], "timezone": "Europe/London",
               "center": (51.5074, -0.1278), "booking_dest_id": None, "aliases": [],
              "google_city_id": "/m/04jpl"},
    "Paris": {"country_code": "fr", "airports": ["CDG", "ORY"], "timezone": "Europe/Paris",
              "center": (48.8566, 2.3522), "booking_dest_id": None, "aliases": [],
             "google_city_id": "/m/05qtj"},
    # ---- Well-known cities added 2026-10-24 (see the note above SUPPORTED_CITIES) ----
    "Abu Dhabi": {"country_code": "ae", "airports": ["AUH"], "timezone": "Asia/Dubai",
                 "center": (24.4511, 54.3969), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "AUH"},
    "Sharjah": {"country_code": "ae", "airports": ["SHJ"], "timezone": "Asia/Dubai",
               "center": (25.3375, 55.4119), "booking_dest_id": None, "aliases": [],
               "google_city_id": "SHJ"},
    "Muscat": {"country_code": "om", "airports": ["MCT"], "timezone": "Asia/Muscat",
              "center": (23.6139, 58.5922), "booking_dest_id": None, "aliases": [],
              "google_city_id": "MCT"},
    "Kuwait City": {"country_code": "kw", "airports": ["KWI"], "timezone": "Asia/Kuwait",
                   "center": (29.375, 47.98), "booking_dest_id": None, "aliases": ["kuwait"],
                   "google_city_id": "KWI"},
    "Manama": {"country_code": "bh", "airports": ["BAH"], "timezone": "Asia/Bahrain",
              "center": (26.2167, 50.5833), "booking_dest_id": None, "aliases": ["bahrain"],
              "google_city_id": "BAH"},
    "Medina": {"country_code": "sa", "airports": ["MED"], "timezone": "Asia/Riyadh",
              "center": (24.47, 39.61), "booking_dest_id": None, "aliases": ["madinah", "al madinah"],
              "google_city_id": "MED"},
    "Dammam": {"country_code": "sa", "airports": ["DMM"], "timezone": "Asia/Riyadh",
              "center": (26.4333, 50.1), "booking_dest_id": None, "aliases": [],
              "google_city_id": "DMM"},
    "Beirut": {"country_code": "lb", "airports": ["BEY"], "timezone": "Asia/Beirut",
              "center": (33.8869, 35.5131), "booking_dest_id": None, "aliases": [],
              "google_city_id": "BEY"},
    "Basra": {"country_code": "iq", "airports": ["BSR"], "timezone": "Asia/Baghdad",
             "center": (30.515, 47.81), "booking_dest_id": None, "aliases": ["basrah"],
             "google_city_id": "BSR"},
    "Sulaymaniyah": {"country_code": "iq", "airports": ["ISU"], "timezone": "Asia/Baghdad",
                    "center": (35.55, 45.4333), "booking_dest_id": None, "aliases": ["sulaimani", "slemani"],
                    "google_city_id": "ISU"},
    "Najaf": {"country_code": "iq", "airports": ["NJF"], "timezone": "Asia/Baghdad",
             "center": (32.029, 44.3396), "booking_dest_id": None, "aliases": [],
             "google_city_id": "NJF"},
    "Casablanca": {"country_code": "ma", "airports": ["CMN"], "timezone": "Africa/Casablanca",
                  "center": (33.5992, -7.62), "booking_dest_id": None, "aliases": [],
                  "google_city_id": "CMN"},
    "Marrakesh": {"country_code": "ma", "airports": ["RAK"], "timezone": "Africa/Casablanca",
                 "center": (31.6295, -7.9811), "booking_dest_id": None, "aliases": ["marrakech"],
                 "google_city_id": "RAK"},
    "Tunis": {"country_code": "tn", "airports": ["TUN"], "timezone": "Africa/Tunis",
             "center": (36.8008, 10.18), "booking_dest_id": None, "aliases": [],
             "google_city_id": "TUN"},
    "Algiers": {"country_code": "dz", "airports": ["ALG"], "timezone": "Africa/Algiers",
               "center": (36.7764, 3.0586), "booking_dest_id": None, "aliases": [],
               "google_city_id": "ALG"},
    "Alexandria": {"country_code": "eg", "airports": ["HBE"], "timezone": "Africa/Cairo",
                  "center": (31.1975, 29.8925), "booking_dest_id": None, "aliases": [],
                  "google_city_id": "HBE"},
    "Sharm El Sheikh": {"country_code": "eg", "airports": ["SSH"], "timezone": "Africa/Cairo",
                       "center": (27.8519, 34.305), "booking_dest_id": None, "aliases": ["sharm el-sheikh", "sharm"],
                       "google_city_id": "SSH"},
    "Hurghada": {"country_code": "eg", "airports": ["HRG"], "timezone": "Africa/Cairo",
                "center": (27.2578, 33.8117), "booking_dest_id": None, "aliases": [],
                "google_city_id": "HRG"},
    "Antalya": {"country_code": "tr", "airports": ["AYT"], "timezone": "Europe/Istanbul",
               "center": (36.9081, 30.6956), "booking_dest_id": None, "aliases": [],
               "google_city_id": "AYT"},
    "Izmir": {"country_code": "tr", "airports": ["ADB"], "timezone": "Europe/Istanbul",
             "center": (38.4127, 27.1384), "booking_dest_id": None, "aliases": [],
             "google_city_id": "ADB"},
    "Ankara": {"country_code": "tr", "airports": ["ESB"], "timezone": "Europe/Istanbul",
              "center": (39.9358, 32.8387), "booking_dest_id": None, "aliases": [],
              "google_city_id": "ESB"},
    "Trabzon": {"country_code": "tr", "airports": ["TZX"], "timezone": "Europe/Istanbul",
               "center": (41.005, 39.7225), "booking_dest_id": None, "aliases": [],
               "google_city_id": "TZX"},
    "Baku": {"country_code": "az", "airports": ["GYD"], "timezone": "Asia/Baku",
            "center": (40.3667, 49.8352), "booking_dest_id": None, "aliases": [],
            "google_city_id": "GYD"},
    "Tbilisi": {"country_code": "ge", "airports": ["TBS"], "timezone": "Asia/Tbilisi",
               "center": (41.7225, 44.7925), "booking_dest_id": None, "aliases": [],
               "google_city_id": "TBS"},
    "Tashkent": {"country_code": "uz", "airports": ["TAS"], "timezone": "Asia/Tashkent",
                "center": (41.3111, 69.2797), "booking_dest_id": None, "aliases": [],
                "google_city_id": "TAS"},
    "Berlin": {"country_code": "de", "airports": ["BER"], "timezone": "Europe/Berlin",
              "center": (52.5167, 13.3833), "booking_dest_id": None, "aliases": [],
              "google_city_id": "BER"},
    "Munich": {"country_code": "de", "airports": ["MUC"], "timezone": "Europe/Berlin",
              "center": (48.1375, 11.575), "booking_dest_id": None, "aliases": ["munchen", "münchen"],
              "google_city_id": "MUC"},
    "Frankfurt": {"country_code": "de", "airports": ["FRA"], "timezone": "Europe/Berlin",
                 "center": (50.1106, 8.6822), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "FRA"},
    "Vienna": {"country_code": "at", "airports": ["VIE"], "timezone": "Europe/Vienna",
              "center": (48.2083, 16.3725), "booking_dest_id": None, "aliases": ["wien"],
              "google_city_id": "VIE"},
    "Amsterdam": {"country_code": "nl", "airports": ["AMS"], "timezone": "Europe/Amsterdam",
                 "center": (52.3667, 4.8833), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "AMS"},
    "Brussels": {"country_code": "be", "airports": ["BRU"], "timezone": "Europe/Brussels",
                "center": (50.8467, 4.3517), "booking_dest_id": None, "aliases": [],
                "google_city_id": "BRU"},
    "Madrid": {"country_code": "es", "airports": ["MAD"], "timezone": "Europe/Madrid",
              "center": (40.4169, -3.7033), "booking_dest_id": None, "aliases": [],
              "google_city_id": "MAD"},
    "Barcelona": {"country_code": "es", "airports": ["BCN"], "timezone": "Europe/Madrid",
                 "center": (41.3825, 2.1769), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "BCN"},
    "Lisbon": {"country_code": "pt", "airports": ["LIS"], "timezone": "Europe/Lisbon",
              "center": (38.708, -9.139), "booking_dest_id": None, "aliases": ["lisboa"],
              "google_city_id": "LIS"},
    "Milan": {"country_code": "it", "airports": ["MXP", "LIN"], "timezone": "Europe/Rome",
             "center": (45.4669, 9.19), "booking_dest_id": None, "aliases": ["milano"],
             "google_city_id": "/m/0947l"},  # City ID verified live 2026-10-24 (searchAirport)
    "Athens": {"country_code": "gr", "airports": ["ATH"], "timezone": "Europe/Athens",
              "center": (37.9842, 23.7281), "booking_dest_id": None, "aliases": [],
              "google_city_id": "ATH"},
    "Prague": {"country_code": "cz", "airports": ["PRG"], "timezone": "Europe/Prague",
              "center": (50.0875, 14.4214), "booking_dest_id": None, "aliases": [],
              "google_city_id": "PRG"},
    "Budapest": {"country_code": "hu", "airports": ["BUD"], "timezone": "Europe/Budapest",
                "center": (47.4983, 19.0408), "booking_dest_id": None, "aliases": [],
                "google_city_id": "BUD"},
    "Zurich": {"country_code": "ch", "airports": ["ZRH"], "timezone": "Europe/Zurich",
              "center": (47.3744, 8.5411), "booking_dest_id": None, "aliases": ["zürich"],
              "google_city_id": "ZRH"},
    "Geneva": {"country_code": "ch", "airports": ["GVA"], "timezone": "Europe/Zurich",
              "center": (46.2, 6.15), "booking_dest_id": None, "aliases": [],
              "google_city_id": "GVA"},
    "Copenhagen": {"country_code": "dk", "airports": ["CPH"], "timezone": "Europe/Copenhagen",
                  "center": (55.6761, 12.5689), "booking_dest_id": None, "aliases": [],
                  "google_city_id": "CPH"},
    "Stockholm": {"country_code": "se", "airports": ["ARN", "BMA"], "timezone": "Europe/Stockholm",
                 "center": (59.3294, 18.0686), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "/m/06mxs"},  # City ID verified live 2026-10-24 (searchAirport)
    "Manchester": {"country_code": "gb", "airports": ["MAN"], "timezone": "Europe/London",
                  "center": (53.4794, -2.2453), "booking_dest_id": None, "aliases": [],
                  "google_city_id": "MAN"},
    "Dublin": {"country_code": "ie", "airports": ["DUB"], "timezone": "Europe/Dublin",
              "center": (53.3497, -6.2603), "booking_dest_id": None, "aliases": [],
              "google_city_id": "DUB"},
    "Sarajevo": {"country_code": "ba", "airports": ["SJJ"], "timezone": "Europe/Sarajevo",
                "center": (43.8564, 18.4131), "booking_dest_id": None, "aliases": [],
                "google_city_id": "SJJ"},
    "Warsaw": {"country_code": "pl", "airports": ["WAW"], "timezone": "Europe/Warsaw",
              "center": (52.23, 21.0111), "booking_dest_id": None, "aliases": [],
              "google_city_id": "WAW"},
    "Bangkok": {"country_code": "th", "airports": ["BKK", "DMK"], "timezone": "Asia/Bangkok",
               "center": (13.75, 100.5167), "booking_dest_id": "-3414440", "aliases": [],
               "google_city_id": "/m/0fn2g"},  # City ID verified live 2026-10-24 (searchAirport)
    "Phuket": {"country_code": "th", "airports": ["HKT"], "timezone": "Asia/Bangkok",
              "center": (7.89, 98.3983), "booking_dest_id": None, "aliases": [],
              "google_city_id": "HKT"},
    "Kuala Lumpur": {"country_code": "my", "airports": ["KUL"], "timezone": "Asia/Kuala_Lumpur",
                    "center": (3.1478, 101.6953), "booking_dest_id": None, "aliases": [],
                    "google_city_id": "KUL"},
    "Singapore": {"country_code": "sg", "airports": ["SIN"], "timezone": "Asia/Singapore",
                 "center": (1.3, 103.8), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "SIN"},
    "Jakarta": {"country_code": "id", "airports": ["CGK"], "timezone": "Asia/Jakarta",
               "center": (-6.1753, 106.8269), "booking_dest_id": None, "aliases": [],
               "google_city_id": "CGK"},
    "Tokyo": {"country_code": "jp", "airports": ["HND", "NRT"], "timezone": "Asia/Tokyo",
             "center": (35.6894, 139.6917), "booking_dest_id": None, "aliases": [],
             "google_city_id": "/m/07dfk"},  # City ID verified live 2026-10-24 (searchAirport)
    "Seoul": {"country_code": "kr", "airports": ["ICN", "GMP"], "timezone": "Asia/Seoul",
             "center": (37.56, 126.99), "booking_dest_id": None, "aliases": [],
             "google_city_id": "/m/0hsqf"},  # City ID verified live 2026-10-24 (searchAirport)
    "Beijing": {"country_code": "cn", "airports": ["PEK", "PKX"], "timezone": "Asia/Shanghai",
               "center": (39.904, 116.4075), "booking_dest_id": None, "aliases": [],
               "google_city_id": "/m/01914"},  # City ID verified live 2026-10-24 (searchAirport)
    "Shanghai": {"country_code": "cn", "airports": ["PVG", "SHA"], "timezone": "Asia/Shanghai",
                "center": (31.2325, 121.4692), "booking_dest_id": None, "aliases": [],
                "google_city_id": "/m/06wjf"},  # City ID verified live 2026-10-24 (searchAirport)
    "Hong Kong": {"country_code": "hk", "airports": ["HKG"], "timezone": "Asia/Hong_Kong",
                 "center": (22.2783, 114.1586), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "HKG"},
    "Male": {"country_code": "mv", "airports": ["MLE"], "timezone": "Indian/Maldives",
            "center": (4.175, 73.5083), "booking_dest_id": None, "aliases": ["malé"],
            "google_city_id": "MLE"},
    "Delhi": {"country_code": "in", "airports": ["DEL"], "timezone": "Asia/Kolkata",
             "center": (28.6667, 77.2167), "booking_dest_id": None, "aliases": ["new delhi"],
             "google_city_id": "DEL"},
    "Mumbai": {"country_code": "in", "airports": ["BOM"], "timezone": "Asia/Kolkata",
              "center": (19.0758, 72.8775), "booking_dest_id": None, "aliases": [],
              "google_city_id": "BOM"},
    "Karachi": {"country_code": "pk", "airports": ["KHI"], "timezone": "Asia/Karachi",
               "center": (24.86, 67.01), "booking_dest_id": None, "aliases": [],
               "google_city_id": "KHI"},
    "Lahore": {"country_code": "pk", "airports": ["LHE"], "timezone": "Asia/Karachi",
              "center": (31.5497, 74.3436), "booking_dest_id": None, "aliases": [],
              "google_city_id": "LHE"},
    "Islamabad": {"country_code": "pk", "airports": ["ISB"], "timezone": "Asia/Karachi",
                 "center": (33.6989, 73.0369), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "ISB"},
    "New York": {"country_code": "us", "airports": ["JFK", "LGA", "EWR"], "timezone": "America/New_York",
                "center": (40.7128, -74.0061), "booking_dest_id": None, "aliases": ["new york city", "nyc"],
                "google_city_id": "/m/02_286"},  # City ID verified live 2026-10-24 (searchAirport)
    "Los Angeles": {"country_code": "us", "airports": ["LAX"], "timezone": "America/Los_Angeles",
                   "center": (34.0522, -118.2437), "booking_dest_id": None, "aliases": [],
                   "google_city_id": "LAX"},
    "Miami": {"country_code": "us", "airports": ["MIA"], "timezone": "America/New_York",
             "center": (25.7742, -80.1936), "booking_dest_id": None, "aliases": [],
             "google_city_id": "MIA"},
    "Toronto": {"country_code": "ca", "airports": ["YYZ", "YTZ"], "timezone": "America/Toronto",
               "center": (43.6703, -79.3867), "booking_dest_id": None, "aliases": [],
               "google_city_id": "/m/0h7h6"},  # City ID verified live 2026-10-24 (searchAirport)
    "Nairobi": {"country_code": "ke", "airports": ["NBO"], "timezone": "Africa/Nairobi",
               "center": (-1.2864, 36.8172), "booking_dest_id": None, "aliases": [],
               "google_city_id": "NBO"},
    "Cape Town": {"country_code": "za", "airports": ["CPT"], "timezone": "Africa/Johannesburg",
                 "center": (-33.9253, 18.4239), "booking_dest_id": None, "aliases": [],
                 "google_city_id": "CPT"}
}
AIRPORT_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")
# Every configured airport code must be exactly three letters
assert all(AIRPORT_CODE_PATTERN.match(a) for c in SUPPORTED_CITIES.values() for a in c["airports"])

# City names of airports that Google Flights includes in a city area but that belong to ANOTHER city.
# Flights using them are never selected; they can only appear as labeled nearby-airport alternatives.
NEARBY_AIRPORT_CITIES = {"SHJ": "Sharjah", "AUH": "Abu Dhabi", "BVA": "Beauvais", "HHN": "Hahn",
                         "ADB": "Izmir", "ESB": "Ankara", "MCT": "Muscat", "BGY": "Bergamo", "NYO": "Nyköping"}
NEARBY_AIRPORT_TIMEZONES = {"SHJ": "Asia/Dubai", "AUH": "Asia/Dubai", "BVA": "Europe/Paris", "HHN": "Europe/Berlin",
                            "ADB": "Europe/Istanbul", "ESB": "Europe/Istanbul", "MCT": "Asia/Muscat",
                            "BGY": "Europe/Rome", "NYO": "Europe/Stockholm"}

# IANA time zones used to verify that flight dates are local departure dates
AIRPORT_TIMEZONES = {airport: city["timezone"] for city in SUPPORTED_CITIES.values() for airport in city["airports"]}
AIRPORT_TIMEZONES.update({code: zone for code, zone in NEARBY_AIRPORT_TIMEZONES.items() if code not in AIRPORT_TIMEZONES})

def _normalize_city_text(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())

def resolve_supported_city(city_name):
    """Returns (canonical_label, city_record) or (None, None)."""
    normalized = _normalize_city_text(city_name)
    for label, city in SUPPORTED_CITIES.items():
        if normalized == label.lower() or normalized in city["aliases"]:
            return label, city
    return None, None

def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))

# ==========================================
# 10. INPUT VALIDATION (PUBLIC REQUEST, docs/api-contracts.md section 3)
# ==========================================
PUBLIC_REQUEST_FIELDS = ["departure_city", "destination_city", "start_date", "return_date", "adults", "budget_usd"]
# Public requests are ROUND TRIPS only (v0.4: "no one-way switch"; PR #25 review, item 3). "one_way" exists only as an
# adapter-internal option (validate_request / search_travel trip_type argument) until a contract change is approved.
TRIP_TYPES = ("round_trip", "one_way")

# Every validator returns (clean_value, error_message). error_message is None when the value is valid.
def validate_city_name(value, field_label):
    city = re.sub(r"\s+", " ", value.strip()) if isinstance(value, str) else ""
    if not (2 <= len(city) <= 80) or not re.fullmatch(r"[^\W\d_]+(?:[ \-'.][^\W\d_]+)*\.?", city):
        return None, f"{field_label} must be a city name made of letters (e.g., Cairo)."
    return city, None

def validate_date(value, field_label):
    text = value.strip() if isinstance(value, str) else ""
    parsed = parse_iso_date(text) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None
    if parsed is None:
        return None, f"{field_label} must be a valid date in YYYY-MM-DD format (e.g., 2026-11-10)."
    return parsed, None

def validate_adults(value):
    """Contract: integer 1-4; reject booleans, fractions and numeric strings."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None, "adults must be a whole number (not text, boolean or fraction)."
    if not MIN_ADULTS <= value <= MAX_ADULTS:
        return None, f"adults must be between {MIN_ADULTS} and {MAX_ADULTS}."
    return value, None

def validate_budget(value, field_label="budget_usd"):
    """The budget must be a number that stays strictly positive after rounding to cents."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"{field_label} must be a number."
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None, f"{field_label} must be a number."
    if not amount.is_finite():
        return None, f"{field_label} must be a finite number."
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        return None, f"{field_label} must be greater than 0.00 after rounding to cents."
    return float(amount), None

def validate_airport_code(value, field_label):
    """Adapter-internal override check: exactly three letters."""
    code = value.strip().upper() if isinstance(value, str) else ""
    if not AIRPORT_CODE_PATTERN.match(code):
        return None, f"{field_label} must be exactly 3 letters (IATA code, e.g., IST)."
    return code, None

def validate_request(request_data, require_budget=True, rooms=None, origin_airport=None, destination_airport=None,
                     trip_type="round_trip"):
    """
    Validates the public request BEFORE any external call. Returns a clean trip dict or raises:
      invalid_input       -> one entry per invalid field in details["fields"]
      unsupported_search  -> valid input, but a city is outside the supported coverage
    rooms / origin_airport / destination_airport / trip_type are adapter-internal options, NOT public request fields.
    """
    if not isinstance(request_data, dict):
        raise TravelMateError("invalid_input", "Request data must be a JSON object.",
                              {"fields": [{"field": "request", "message": "Expected a JSON object."}]})

    field_errors = []

    def check(field, result):
        value, error = result
        if error:
            field_errors.append({"field": field, "message": error})
        return value

    unknown = sorted(set(request_data) - set(PUBLIC_REQUEST_FIELDS))
    for field in unknown:
        field_errors.append({"field": field, "message": "Unknown field (not part of the public request)."})
    departure_city = check("departure_city", validate_city_name(request_data.get("departure_city"), "departure_city"))
    destination_city = check("destination_city", validate_city_name(request_data.get("destination_city"), "destination_city"))
    start = check("start_date", validate_date(request_data.get("start_date"), "start_date"))
    end = check("return_date", validate_date(request_data.get("return_date"), "return_date"))
    adults = check("adults", validate_adults(request_data.get("adults")))
    if trip_type not in TRIP_TYPES:
        field_errors.append({"field": "trip_type", "message": "trip_type must be 'round_trip' or 'one_way'."})
    budget_usd = None
    if require_budget or "budget_usd" in request_data:
        budget_usd = check("budget_usd", validate_budget(request_data.get("budget_usd")))
    if rooms is None:
        rooms = DEFAULT_ROOMS
    elif isinstance(rooms, bool) or not isinstance(rooms, int) or rooms < 1:
        field_errors.append({"field": "rooms", "message": "rooms must be a positive whole number."})

    # Cross-field date rules (contract: start_date strictly after today's UTC date, 1-7 nights)
    if start and start <= _today_utc():
        field_errors.append({"field": "start_date", "message": f"start_date must be after {_today_utc().isoformat()} (UTC)."})
    if start and end:
        nights = (end - start).days
        if nights < MIN_NIGHTS:
            field_errors.append({"field": "return_date", "message": "return_date must be after start_date."})
        elif nights > MAX_NIGHTS:
            field_errors.append({"field": "return_date", "message": f"The trip cannot be longer than {MAX_NIGHTS} nights."})
    if isinstance(rooms, int) and adults and rooms > adults:
        field_errors.append({"field": "rooms", "message": "rooms cannot be more than adults."})

    if field_errors:
        raise TravelMateError("invalid_input", details={"fields": field_errors})

    origin_label, origin_city = resolve_supported_city(departure_city)
    destination_label, destination_record = resolve_supported_city(destination_city)
    unsupported = [name for name, city in ((departure_city, origin_city), (destination_city, destination_record)) if city is None]
    if unsupported:
        raise TravelMateError("unsupported_search", f"Unsupported city: {', '.join(unsupported)}.",
                              {"reason": "city_not_in_coverage", "supported_cities": sorted(SUPPORTED_CITIES)})
    if origin_label == destination_label:
        raise TravelMateError("invalid_input", details={"fields": [{
            "field": "destination_city", "message": "destination_city must be different from departure_city."}]})

    airports = {}
    for field, override, city in (("origin_airport", origin_airport, origin_city),
                                  ("destination_airport", destination_airport, destination_record)):
        if override is None:
            airports[field] = city["airports"][0]
            continue
        code, error = validate_airport_code(override, field)
        if error or code not in city["airports"]:
            raise TravelMateError("invalid_input", details={"fields": [{
                "field": field, "message": error or f"{field} must be one of {', '.join(city['airports'])}."}]})
        airports[field] = code

    return {
        "departure_city": origin_label,
        "destination_city": destination_label,
        "start_date": start.isoformat(),
        "return_date": end.isoformat(),
        "nights": (end - start).days,
        "adults": adults,
        "budget_usd": budget_usd,
        "trip_type": trip_type,  # Adapter-internal (public requests are always round trips)
        # Adapter-internal values (never part of the public request)
        "adapter": {"origin_airport": airports["origin_airport"], "destination_airport": airports["destination_airport"],
                    "rooms": rooms, "rooms_source": "default" if rooms == DEFAULT_ROOMS else "adapter_option"}
    }

def public_trip_request(trip):
    """Returns the public request fields exactly (safe to store and display)."""
    return {k: trip[k] for k in PUBLIC_REQUEST_FIELDS if trip.get(k) is not None}

# ==========================================
# 11. FLIGHT PROVIDER (SKYSCANNER ROUTE QUOTES - INDICATIVE ONLY)
# ==========================================
# Documented provider behavior (verified with live responses on 2026-10-17 and 2026-10-19):
#   - The /route endpoint returns Skyscanner's CACHED quotes for a city pair ("not a live search" per its usage_note).
#   - "date", "adults" and "currency" query parameters are NOT honored: dates spread over ~12 months, GBP prices.
#   - Deep links contain no adult count, so each quote is a SINGLE-ADULT one-way fare.
#   - No departure times are returned; only local departure dates.
# Therefore flights are "not_configured" by default. In "indicative" mode, ONLY exact-date quotes are selectable;
# total_price_usd = single-adult quote x travelers (unverified) and every flight price stays indicative.
SELECTED_FLIGHT_FIELDS = ["airline", "carrier_codes", "origin_airport", "destination_airport", "flight_date",
                          "requested_date", "date_matches_request", "days_from_requested_date", "is_direct",
                          "stops_label", "price_per_person_usd", "travelers", "total_price_usd", "quoted_at",
                          "booking_link"]
FLIGHT_FEE_EVIDENCE = ("Skyscanner displays fares inclusive of taxes and carrier-imposed charges (provider convention); "
                       "baggage and optional extras are not included.")

def flight_leg_id(leg):
    """Same synthetic format BE-04 builds: airline-date-origin-destination."""
    return f"{leg['airline']}-{leg['flight_date']}-{leg['origin_airport']}-{leg['destination_airport']}"

def round_trip_offer_id(outbound, returning):
    """Matches BE-04's synthetic round-trip flight ID (and therefore CostItem.source_offer_id)."""
    return f"{flight_leg_id(outbound)}__{flight_leg_id(returning)}"

def flight_leg_key(leg, schedule):
    """
    Adapter ID of ONE real flight: BE-04's synthetic leg ID + flight numbers + local departure time (HHMM).
    BE-04's synthetic ID alone is not unique: two flights of the same airline, day and route share it.
    """
    numbers = "+".join(n.replace(" ", "") for n in schedule.get("flight_numbers") or []) or "NA"
    clock = str(schedule.get("departure_local") or "")[11:16].replace(":", "") or "NA"
    return f"{flight_leg_id(leg)}-{numbers}-{clock}"

def fetch_flight_quotes(origin, destination, travel_date, adults, deadline, label, cache_mode="default", evidence=None):
    # The requested scope is sent to the provider, then validated against what it actually returns
    params = {"origin": origin.lower(), "destination": destination.lower(), "date": travel_date,
              "adults": str(adults), "currency": "USD", "market": "US", "locale": "en-US"}
    logger.info(f"[*] Fetching {label} quotes {origin} -> {destination} for {travel_date} ({adults} adult(s))...")
    return provider_get("skyscanner_route", params, deadline, cache_mode=cache_mode, evidence=evidence)

def _build_stops_label(is_direct, stops, transit_airports):
    if is_direct:
        return "Direct"
    if stops is None:
        return "With stops (count and transit airports not provided by provider)"
    label = f"{stops} stop(s)"
    if transit_airports:
        label += f" via {', '.join(transit_airports)}"
    return label

def normalize_flight_quotes(payload, direction, origin, destination, requested_date, travelers, fx, provenance,
                            max_results=5):
    """
    Returns (exact_date_legs, alternative_date_legs, provenance_entries, coverage).
    Legs use the exact BE-04 SelectedFlight fields. date_matches_request is ALWAYS computed as
    flight_date == requested_date; alternative-date legs are never selectable.
    """
    section = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(section, dict) or not isinstance(section.get("deals"), list):
        raise TravelMateError("invalid_response", details={"reason": "missing_deals_list", "direction": direction})

    deals = section["deals"]
    currency = section.get("currency")
    target_date = parse_iso_date(requested_date)
    excluded = {"route_mismatch": 0, "invalid_price": 0, "unconvertible_currency": 0, "malformed": 0}
    returned_dates = set()
    exact, alternatives = [], []

    for d in deals:
        legs = [leg for leg in (d.get("legs") or []) if isinstance(leg, dict)] if isinstance(d, dict) else []
        if not legs:
            excluded["malformed"] += 1
            continue
        first_leg, last_leg = legs[0], legs[-1]
        leg_origin = str((first_leg.get("origin") or {}).get("sky_code") or "").upper()
        leg_destination = str((last_leg.get("destination") or {}).get("sky_code") or "").upper()
        if leg_origin != origin or leg_destination != destination:
            excluded["route_mismatch"] += 1
            continue
        flight_date = parse_iso_date(first_leg.get("date"))
        quoted_at = normalize_utc_timestamp(first_leg.get("quoted_at"))
        deep_link = d.get("deep_link_path")
        if flight_date is None or quoted_at is None or not deep_link:
            excluded["malformed"] += 1
            continue
        returned_dates.add(flight_date.isoformat())
        price = valid_amount(d.get("price"))
        if price is None:
            excluded["invalid_price"] += 1
            continue
        price_usd, conversion = convert_to_usd(price, currency, fx)
        if price_usd is None:
            excluded["unconvertible_currency"] += 1
            continue

        # Airline names and codes come from the flight segments (legs), NOT from the deal ID
        airline_names, carrier_codes = [], []
        for leg in legs:
            if leg.get("carrier_name") and leg["carrier_name"] not in airline_names:
                airline_names.append(leg["carrier_name"])
            if leg.get("carrier_code") and leg["carrier_code"] not in carrier_codes:
                carrier_codes.append(leg["carrier_code"])
        transit_airports = [(leg.get("destination") or {}).get("sky_code") for leg in legs[:-1]
                            if (leg.get("destination") or {}).get("sky_code")]
        is_direct = bool(d.get("direct"))
        stops = 0 if is_direct else (len(legs) - 1 if len(legs) > 1 else None)

        leg_view = {
            "airline": " + ".join(airline_names) or "Unknown Airline",
            "carrier_codes": carrier_codes,
            "origin_airport": leg_origin,
            "destination_airport": leg_destination,
            "flight_date": flight_date.isoformat(),
            "requested_date": requested_date,
            "date_matches_request": flight_date == target_date,        # Strictly derived, never set by hand
            "days_from_requested_date": (flight_date - target_date).days,  # Signed: + later / - earlier
            "is_direct": is_direct,
            "stops_label": _build_stops_label(is_direct, stops, transit_airports),
            "price_per_person_usd": price_usd,
            "travelers": travelers,
            "total_price_usd": round_money(price_usd * travelers),
            "quoted_at": quoted_at,
            "booking_link": f"https://www.skyscanner.net{deep_link}"
        }
        leg_provenance = {
            "offer_id": flight_leg_id(leg_view),
            "category": "flights",
            "direction": direction,
            "source": FLIGHT_SOURCE_LABEL,
            "provider_offer_id": d.get("id"),
            "retrieved_at": provenance["retrieved_at"],
            "cache_status": provenance["cache_status"],
            "original_currency": currency,
            "original_amount": price,
            "quote_timestamp": quoted_at,
            "conversion": conversion,
            "provider_query": provenance["query_parameters"],
            "coverage_evidence": (
                f"Cached single-adult one-way quote ({direction}); total_price_usd = price_per_person_usd x {travelers} "
                f"(unverified group price). Provider ignores date/adults/currency parameters. {FLIGHT_FEE_EVIDENCE}"),
            "fees": {"included_in_base": True, "additional_fees_usd": None},
            "price_authority": "indicative",
            "transit_airports": transit_airports,
            "airport_timezones": {"departure": AIRPORT_TIMEZONES.get(leg_origin, "unknown"),
                                  "destination": AIRPORT_TIMEZONES.get(leg_destination, "unknown")}
        }
        (exact if leg_view["date_matches_request"] else alternatives).append((leg_view, leg_provenance))

    exact.sort(key=lambda item: (item[0]["total_price_usd"], flight_leg_id(item[0])))
    alternatives.sort(key=lambda item: (abs(item[0]["days_from_requested_date"]), item[0]["total_price_usd"]))
    exact, alternatives = exact[:max_results], alternatives[:max_results]
    coverage = {
        "deals_returned": len(deals),
        "exact_date_quotes": len(exact),
        "alternative_date_quotes": len(alternatives),
        "excluded": excluded,
        "requested_date": requested_date,
        "returned_date_range": [min(returned_dates), max(returned_dates)] if returned_dates else None,
        "date_parameter_honored": bool(returned_dates) and returned_dates == {requested_date},
        "returned_currency": currency,
        "currency_parameter_honored": str(currency).upper() == "USD",
        "provider_usage_note": str(section.get("usage_note") or "")[:400] or None
    }
    return ([v for v, _ in exact], [v for v, _ in alternatives],
            [p for _, p in exact] + [p for _, p in alternatives], coverage)

# ==========================================
# 11.1 FLIGHT PROVIDER (GOOGLE FLIGHTS - LIVE ROUND TRIP)
# ==========================================
# Documented provider behavior (verified with live responses on 2026-10-21):
#   - searchFlights honors the requested date and adults: every result departs on the requested local date.
#   - Without return_date it is a ONE-WAY search; "price" is then the provider's one-way total for ALL adults
#     (1 adult $248 vs 2 adults $495 on the round-trip search; another flight $617 vs $1,556: priced by the provider,
#     never multiplied by us). One-way IST-CAI $272 + CAI-IST $223 = $495, the same as the round-trip fare.
#   - Round trips = two one-way searches run in parallel (~2.4-3 s each), so each leg has its own real total and
#     nothing is split. The slower getNextFlights round-trip flow (23 s+) is not used.
#   - currency=USD is honored (the same search with currency=EUR returned prices ~0.89x, the market rate).
#   - Segment times are LOCAL airport times, sometimes unpadded ("2026-11-1 09:35"); they are normalized and
#     converted to UTC with IANA zones.
#   - The same flight can appear several times with different fares / tokens; only the cheapest is kept.
#   - The provider "stops" field is unreliable (always 0, even with a layover); stops are counted from segments.
#   - No tax field: Google Flights shows totals including required taxes and fees (provider convention).
GOOGLE_FEE_EVIDENCE = ("Google Flights shows total fares including required taxes and fees (provider convention); "
                       "checked bags and optional extras are not included.")

def local_to_utc(local_text, airport_code):
    """'2026-11-20 12:15' at airport_code -> ('2026-11-20T09:15:00Z', date(2026, 11, 20)), or (None, None)."""
    zone = AIRPORT_TIMEZONES.get(airport_code)
    try:
        local = datetime.strptime(str(local_text).strip(), "%Y-%m-%d %H:%M")
        aware = local.replace(tzinfo=ZoneInfo(zone))
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return None, None
    return aware.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), local.date()

def utc_to_local_date(utc_text, airport_code):
    """Inverse check used to verify that a UTC departure is on the requested LOCAL date at that airport."""
    zone = AIRPORT_TIMEZONES.get(airport_code)
    try:
        moment = datetime.fromisoformat(str(utc_text).replace("Z", "+00:00"))
        return moment.astimezone(ZoneInfo(zone)).date().isoformat()
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return None

def _local_clock(local_text):
    """'2026-11-1 9:35' -> '09:35' (provider times are not always zero-padded)."""
    return datetime.strptime(str(local_text).strip(), "%Y-%m-%d %H:%M").strftime("%H:%M")

def _google_options(payload, stage):
    itineraries = ((payload or {}).get("data") or {}).get("itineraries") if isinstance(payload, dict) else None
    if not isinstance(itineraries, dict):
        raise TravelMateError("invalid_response", details={"reason": "missing_itineraries", "stage": stage})
    options = (itineraries.get("topFlights") or []) + (itineraries.get("otherFlights") or [])
    return [o for o in options if isinstance(o, dict)]

def summarize_google_option(option, origin_airports, destination_airports, travel_date):
    """
    Validates one Google Flights option (route by city airports, local departure date, segments, time zones) and
    returns (summary, problem). problem is None when the option is eligible.
    """
    segments = option.get("flights")
    if not isinstance(segments, list) or not segments or not all(isinstance(s, dict) for s in segments):
        return None, "malformed"
    departure = segments[0].get("departure_airport") or {}
    arrival = segments[-1].get("arrival_airport") or {}
    departure_code = str(departure.get("airport_code") or "").upper()
    arrival_code = str(arrival.get("airport_code") or "").upper()
    # origin_airports / destination_airports = None means "any airport" (used only for nearby alternatives)
    if origin_airports is not None and (departure_code not in origin_airports or arrival_code not in destination_airports):
        return None, "route_mismatch"
    if option.get("self_transfer"):
        return None, "self_transfer"  # Separate tickets are not one bookable round trip
    departure_utc, departure_date = local_to_utc(departure.get("time"), departure_code)
    arrival_utc, arrival_date = local_to_utc(arrival.get("time"), arrival_code)
    if departure_utc is None or arrival_utc is None:
        return None, "unknown_timezone"
    if departure_date.isoformat() != travel_date:
        return None, "date_mismatch"
    airlines, flight_numbers = [], []
    for segment in segments:
        if segment.get("airline") and segment["airline"] not in airlines:
            airlines.append(segment["airline"])
        if segment.get("flight_number"):
            flight_numbers.append(str(segment["flight_number"]))
    transit = [str((s.get("arrival_airport") or {}).get("airport_code") or "") for s in segments[:-1]]
    stops = len(segments) - 1  # The provider "stops" field is not reliable
    return {
        "airline": " + ".join(airlines) or "Unknown Airline",
        "flight_numbers": flight_numbers,
        "departure_airport": departure_code,
        "arrival_airport": arrival_code,
        "departure_airport_name": departure.get("airport_name"),
        "arrival_airport_name": arrival.get("airport_name"),
        "departure_date": departure_date.isoformat(),
        "departure_local": f"{departure_date.isoformat()} {_local_clock(departure.get('time'))}",
        "arrival_local": f"{arrival_date.isoformat()} {_local_clock(arrival.get('time'))}",
        "departure_utc": departure_utc,
        "arrival_utc": arrival_utc,
        "stops": stops,
        "transit_airports": [t for t in transit if t],
        "stops_label": _build_stops_label(stops == 0, stops, [t for t in transit if t]),
        "duration_minutes": (option.get("duration") or {}).get("raw"),
        "checked_bags_included": (option.get("bags") or {}).get("checked")
    }, None

def _provider_timestamp(payload):
    stamp = payload.get("timestamp") if isinstance(payload, dict) else None
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        return datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return None

def _carrier_code(flight_number):
    match = re.match(r"^\s*([A-Z0-9]{2})\s*\d", str(flight_number or ""))
    return match.group(1) if match else None

def _google_search_link(origin, destination, travel_date):
    """Public Google Flights search link for the leg (the provider booking_token is not a URL)."""
    return (f"https://www.google.com/travel/flights?q=Flights%20from%20{origin}%20to%20{destination}"
            f"%20on%20{travel_date}%20one%20way")

def resolve_google_city_scope(label, city, main_airport, deadline, cache_mode="default", evidence=None):
    """
    Google Flights search scope for a canonical city: its Google city ID, so ALL its airports are searched like on
    the website (e.g., Istanbul = IST + SAW). Pinned IDs need no call; others are looked up once with searchAirport,
    verified (same city name, contains one of our airports) and cached. Falls back to the main airport.
    """
    if city.get("google_city_id"):
        return {"search_id": city["google_city_id"], "source": "pinned_mapping", "airport_cities": {}}
    params = {"query": label, "language_code": "en-US", "country_code": "US"}
    try:
        payload, _ = provider_get("google_flights_airport", params, deadline, cache_ttl_hours=DESTINATION_ID_TTL_HOURS,
                                  cache_mode=cache_mode, evidence=evidence)
    except TravelMateError as error:
        logger.warning(f"[!] Google city lookup for {label} failed ({error.code}); searching {main_airport} only.")
        return {"search_id": main_airport, "source": f"fallback_main_airport ({error.code})", "airport_cities": {}}
    for item in (payload.get("data") if isinstance(payload, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        airports = {a.get("id"): a.get("city") for a in item.get("list") or [] if isinstance(a, dict) and a.get("id")}
        if (str(item.get("id", "")).startswith(("/m/", "/g/")) and _normalize_city_text(item.get("city")) == label.lower()
                and set(airports) & set(city["airports"])):
            logger.info(f"[+] Google city ID for {label}: {item['id']} (airports: {', '.join(airports)})")
            return {"search_id": item["id"], "source": "verified_lookup", "airport_cities": airports}
    return {"search_id": main_airport, "source": "fallback_main_airport (no verified city match)", "airport_cities": {}}

def _airport_city(code, airport_cities, airport_name):
    """Real city of an airport outside the requested city. Our table wins: Google labels e.g. BVA as "Paris"."""
    return NEARBY_AIRPORT_CITIES.get(code) or airport_cities.get(code) or airport_name or code

def _nearby_alternative(price, summary, direction, origin_label, destination_label, origin_airports,
                        destination_airports, airport_cities, adults, selected_total):
    """A cheaper flight using an airport of ANOTHER city: labeled alternative only, never selected or budgeted."""
    notes = []
    if summary["departure_airport"] not in origin_airports:
        notes.append(f"Departs from {_airport_city(summary['departure_airport'], airport_cities, summary['departure_airport_name'])} "
                     f"({summary['departure_airport']}), not {origin_label}")
    if summary["arrival_airport"] not in destination_airports:
        notes.append(f"Lands in {_airport_city(summary['arrival_airport'], airport_cities, summary['arrival_airport_name'])} "
                     f"({summary['arrival_airport']}), not {destination_label}")
    total = round_money(price)
    return {
        "label": "Alternative: " + "; ".join(notes),
        "direction": direction,
        "airline": summary["airline"],
        "flight_numbers": summary["flight_numbers"],
        "origin_airport": summary["departure_airport"],
        "origin_airport_name": summary["departure_airport_name"],
        "origin_city": _airport_city(summary["departure_airport"], airport_cities, summary["departure_airport_name"]),
        "destination_airport": summary["arrival_airport"],
        "destination_airport_name": summary["arrival_airport_name"],
        "destination_city": _airport_city(summary["arrival_airport"], airport_cities, summary["arrival_airport_name"]),
        "flight_date": summary["departure_date"],
        "departure_local": summary["departure_local"],
        "departure_utc": summary["departure_utc"],
        "stops_label": summary["stops_label"],
        "travelers": adults,
        "total_price_usd": total,
        "saving_vs_selected_usd": round_money(selected_total - total) if selected_total is not None else None,
        "price_authority": "live_provider_quote",
        "eligible": False,
        "reason": "airport_outside_requested_city",
        "usage": "alternative only; never selected, never sent to BE-04"
    }

def _google_leg_search(direction, origin, destination, travel_date, adults, deadline, cache_mode, evidence):
    """One ONE-WAY search (no return_date): its price is the provider total for ALL adults for that leg."""
    params = {"departure_id": origin, "arrival_id": destination, "outbound_date": travel_date,
              "travel_class": "ECONOMY", "adults": str(adults), "show_hidden": "1", "currency": "USD",
              "language_code": "en-US", "country_code": "US", "search_type": "best"}
    logger.info(f"[*] Google Flights: one-way {direction} {origin} -> {destination} on {travel_date} ({adults} adult(s))...")
    payload, provenance = provider_get("google_flights_search", params, deadline, cache_mode=cache_mode, evidence=evidence)
    return payload, provenance, params

def normalize_google_legs(payload, provenance, direction, origin_airports, destination_airports, requested_date,
                          adults, max_results=3, nearby=None):
    """
    Returns (legs, schedules, coverage). legs use the exact BE-04 SelectedFlight fields with the REAL provider leg
    total; duplicates of the same flight (different fares / tokens) keep only the cheapest.
    """
    options = _google_options(payload, direction)
    excluded = {"route_mismatch": 0, "date_mismatch": 0, "invalid_price": 0, "self_transfer": 0,
                "unknown_timezone": 0, "malformed": 0, "duplicate": 0}
    quoted_at = _provider_timestamp(payload) or normalize_utc_timestamp(provenance["retrieved_at"]) or utc_now_iso()
    best_by_flight = {}
    for option in options:
        summary, problem = summarize_google_option(option, origin_airports, destination_airports, requested_date)
        price = valid_amount(option.get("price"))
        if problem == "route_mismatch" and price is not None and nearby is not None:
            # Outside the requested city (e.g., SHJ for Dubai): kept aside as a possible labeled alternative only
            other, other_problem = summarize_google_option(option, None, None, requested_date)
            if other_problem is None:
                nearby.append((price, other))
        if problem:
            excluded[problem] += 1
            continue
        if price is None:
            excluded["invalid_price"] += 1
            continue
        flight_key = ("+".join(summary["flight_numbers"]) or summary["airline"], summary["departure_local"])
        if flight_key in best_by_flight:
            excluded["duplicate"] += 1
            if best_by_flight[flight_key][0] <= price:
                continue
        best_by_flight[flight_key] = (price, summary, option.get("booking_token"))

    ranked = sorted(best_by_flight.values(), key=lambda item: (item[0], item[1]["flight_numbers"]))
    legs, schedules = [], []
    for price, summary, booking_token in ranked[:max_results]:
        total = round_money(price)
        flight_date = parse_iso_date(summary["departure_date"])  # Parsed from the provider local time
        leg = {
            "airline": summary["airline"],
            "carrier_codes": sorted({c for c in (_carrier_code(n) for n in summary["flight_numbers"]) if c}),
            "origin_airport": summary["departure_airport"],
            "destination_airport": summary["arrival_airport"],
            "flight_date": flight_date.isoformat(),
            "requested_date": requested_date,
            "date_matches_request": flight_date.isoformat() == requested_date,
            "days_from_requested_date": (flight_date - parse_iso_date(requested_date)).days,
            "is_direct": summary["stops"] == 0,
            "stops_label": summary["stops_label"],
            "price_per_person_usd": round_money(total / adults),  # Average of the provider group total (informative)
            "travelers": adults,
            "total_price_usd": total,                              # Provider one-way total for ALL adults
            "quoted_at": quoted_at,
            "booking_link": _google_search_link(summary["departure_airport"], summary["arrival_airport"], requested_date)
        }
        legs.append(leg)
        schedules.append({
            "leg_id": None,  # Set below from the flight numbers and the local departure time
            "be04_leg_id": flight_leg_id(leg),
            "direction": direction,
            "flight_numbers": summary["flight_numbers"],
            "departure_local": summary["departure_local"],
            "arrival_local": summary["arrival_local"],
            "departure_utc": summary["departure_utc"],
            "arrival_utc": summary["arrival_utc"],
            "stops": summary["stops"],
            "transit_airports": summary["transit_airports"],
            "duration_minutes": summary["duration_minutes"],
            "checked_bags_included": summary["checked_bags_included"],
            "booking_token_sha256": hashlib.sha256(str(booking_token).encode("utf-8")).hexdigest()[:16] if booking_token else None,
            "query_parameters": provenance["query_parameters"],
            "retrieved_at": provenance["retrieved_at"],
            "cache_status": provenance["cache_status"],
            "original_amount": price
        })
        schedules[-1]["leg_id"] = flight_leg_key(leg, schedules[-1])
    coverage = {"options_returned": len(options), "eligible_flights": len(best_by_flight), "excluded": excluded,
                "requested_date": requested_date, "requested_currency": "USD",
                "currency_evidence": "currency parameter verified 2026-10-21 (EUR comparison); response has no currency field"}
    return legs, schedules, coverage

def _public_flight_offer(trip, outbound, out_schedule, returning, ret_schedule):
    """
    v0.4 public flight offer. For round trips the adapter combines two valid one-way quotes (allowed by the contract).
    Price, times and evidence all come from the SAME leg/schedule pairs; the ID names those exact flights.
    """
    total = round_money(outbound["total_price_usd"] + (returning["total_price_usd"] if returning else 0))
    offer_id = f"{out_schedule['leg_id']}__{ret_schedule['leg_id']}" if returning else out_schedule["leg_id"]
    airline = outbound["airline"] if not returning or outbound["airline"] == returning["airline"] \
        else f"{outbound['airline']} / {returning['airline']}"
    return {
        "id": offer_id,
        "source": GOOGLE_FLIGHTS_SOURCE_LABEL,
        "retrieved_at": normalize_utc_timestamp((ret_schedule or out_schedule)["retrieved_at"]) or utc_now_iso(),
        "price": {"amount_usd": total, "kind": "provider", "coverage": "entire_trip_all_travelers"},
        "taxes": {"status": "included", "additional_amount_usd": 0.0},
        "airline": airline,
        "departure_airport_code": outbound["origin_airport"],
        "arrival_airport_code": outbound["destination_airport"],
        "outbound_departure_at": out_schedule["departure_utc"],
        # One-way trips have no return departure: this needs a contract change (v0.4 requires a round trip)
        "return_departure_at": ret_schedule["departure_utc"] if ret_schedule else None,
        "adults": trip["adults"]
    }, total

def search_google_flights(trip, deadline, cache_mode="default", evidence=None):
    """
    Live flights: one ONE-WAY search per direction, run in parallel (1 call for one-way trips, 2 for round trips).
    Each leg keeps its own REAL provider total, so BE-04 can price the legs directly (nothing is split or invented).
    Returns (outbound_legs, return_legs, public_offers, candidates, provenance_entries, schedules, coverage).
    """
    adapter = trip["adapter"]
    origin_label, destination_label = trip["departure_city"], trip["destination_city"]
    origin_city, destination_city = SUPPORTED_CITIES[origin_label], SUPPORTED_CITIES[destination_label]
    # Search by city (all airports, like the website); selection still accepts ONLY the requested cities' airports
    origin_scope = resolve_google_city_scope(origin_label, origin_city, adapter["origin_airport"], deadline, cache_mode, evidence)
    destination_scope = resolve_google_city_scope(destination_label, destination_city, adapter["destination_airport"],
                                                  deadline, cache_mode, evidence)
    airport_cities = {**origin_scope["airport_cities"], **destination_scope["airport_cities"]}
    directions = [("outbound", origin_scope["search_id"], destination_scope["search_id"], trip["start_date"],
                   origin_city["airports"], destination_city["airports"], origin_label, destination_label)]
    if trip["trip_type"] == "round_trip":
        directions.append(("return", destination_scope["search_id"], origin_scope["search_id"], trip["return_date"],
                           destination_city["airports"], origin_city["airports"], destination_label, origin_label))

    with ThreadPoolExecutor(max_workers=len(directions), thread_name_prefix="flight-leg") as pool:
        futures = {d[0]: pool.submit(_google_leg_search, d[0], d[1], d[2], d[3], trip["adults"], deadline,
                                     cache_mode, evidence) for d in directions}
        searched = {direction: future.result() for direction, future in futures.items()}  # A failed leg fails all

    legs, pairs = {"outbound": [], "return": []}, {"outbound": [], "return": []}
    coverage = {"provider_calls": len(directions),
                "search_scope": {"origin": {k: v for k, v in origin_scope.items() if k != "airport_cities"},
                                 "destination": {k: v for k, v in destination_scope.items() if k != "airport_cities"}}}
    alternatives = {"outbound": [], "return": []}
    for direction, _, _, travel_date, from_airports, to_airports, from_label, to_label in directions:
        payload, provenance, _ = searched[direction]
        nearby = []
        legs[direction], leg_schedules, coverage[direction] = normalize_google_legs(
            payload, provenance, direction, from_airports, to_airports, travel_date, trip["adults"], nearby=nearby)
        pairs[direction] = list(zip(legs[direction], leg_schedules))  # Each leg stays tied to its own schedule
        coverage[direction]["nearby_airport_options"] = len(nearby)
        # Only a CHEAPER nearby-airport flight is shown, and only as a labeled alternative
        selected_total = legs[direction][0]["total_price_usd"] if legs[direction] else None
        nearby.sort(key=lambda item: (item[0], item[1]["flight_numbers"]))
        if nearby and (selected_total is None or round_money(nearby[0][0]) < selected_total):
            alternatives[direction].append(_nearby_alternative(
                nearby[0][0], nearby[0][1], direction, from_label, to_label, from_airports, to_airports,
                airport_cities, trip["adults"], selected_total))
    offers = {}
    if pairs["outbound"] and (trip["trip_type"] == "one_way" or pairs["return"]):
        returns = pairs["return"] if trip["trip_type"] == "round_trip" else [(None, None)]
        for outbound, out_schedule in pairs["outbound"]:
            for returning, ret_schedule in returns:
                offer, total = _public_flight_offer(trip, outbound, out_schedule, returning, ret_schedule)
                offers[offer["id"]] = (offer, total, outbound, out_schedule, returning, ret_schedule)
    ranked = sorted(offers.values(), key=lambda item: (item[1], item[0]["id"]))[:GOOGLE_FLIGHTS_RETURN_OPTIONS]

    public_offers, candidates, provenance_entries, selections = [], [], [], []
    for offer, total, outbound, out_schedule, returning, ret_schedule in ranked:
        public_offers.append(offer)
        candidates.append({"id": offer["id"], "base_usd": total, "additional_fees_usd": None, "included_in_base": True})
        leg_schedules = [out_schedule] + ([ret_schedule] if returning else [])
        selections.append({"offer": offer, "outbound": outbound, "return": returning,
                           "schedule": {"outbound": out_schedule, "return": ret_schedule}})
        provenance_entries.append({
            "offer_id": offer["id"],
            "be04_flight_offer_id": round_trip_offer_id(outbound, returning) if returning else flight_leg_id(outbound),
            "category": "flights",
            "source": GOOGLE_FLIGHTS_SOURCE_LABEL,
            "provider_offer_id": [s["booking_token_sha256"] for s in leg_schedules],
            "retrieved_at": offer["retrieved_at"],
            "cache_status": {s["direction"]: s["cache_status"] for s in leg_schedules},
            "original_currency": "USD",
            "original_amount": round_money(sum(s["original_amount"] for s in leg_schedules)),
            "quote_timestamp": outbound["quoted_at"],
            "conversion": None,
            "provider_query": {s["direction"]: s["query_parameters"] for s in leg_schedules},
            "coverage_evidence": (
                f"{'Sum of two' if returning else 'One'} provider one-way total(s) for {trip['adults']} adult(s), "
                "each priced by the provider (not multiplied or split by the adapter): "
                + "; ".join(f"{s['direction']} {' + '.join(s['flight_numbers'])} {s['departure_local']} local "
                            f"= ${s['original_amount']}" for s in leg_schedules)
                + ". Two one-way tickets can cost more than one round-trip ticket. " + GOOGLE_FEE_EVIDENCE),
            "fees": {"status": "included", "included_in_base": True, "additional_fees_usd": None},
            "price_authority": "live_provider_quote",
            "itinerary": {s["direction"]: s for s in leg_schedules},
            "airport_timezones": {"departure": AIRPORT_TIMEZONES.get(outbound["origin_airport"]),
                                  "destination": AIRPORT_TIMEZONES.get(outbound["destination_airport"])}
        })
    return (legs["outbound"], legs["return"], public_offers, candidates, provenance_entries, selections, coverage,
            alternatives)

# ==========================================
# 12. HOTEL PROVIDER (BOOKING.COM - LIVE, VERIFIED PER OFFER)
# ==========================================
OCCUPANCY_PATTERN = re.compile(r"Price for (\d+) nights?, (\d+) adults?", re.IGNORECASE)
# Unit configuration line, e.g. " 1 private suite • 1 hotel room : 2 beds." or " Hotel room : 4 beds."
UNIT_LINE_PATTERN = re.compile(r"^\s*([^\n:]+?)\s*:\s*\d+\s*beds?\b", re.IGNORECASE | re.MULTILINE)
UNIT_COUNT_PATTERN = re.compile(
    r"(\d+)\s+(?:[^\W\d_]+\s+)?(?:rooms?|suites?|apartments?|studios?|villas?|units?|bungalows?|chalets?)\b",
    re.IGNORECASE)
DISTANCE_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(km|m)\b\s*from", re.IGNORECASE)
AREA_PATTERN = re.compile(r"^\s*[‎‏]?([^\n••]+?)[‬]?\s*[••]\s*[‎]?\d+(?:[.,]\d+)?\s*(?:km|m)\s+from",
                          re.IGNORECASE | re.MULTILINE)
HOTEL_OFFER_FIELDS = ["hotel_id", "name", "star_rating", "review_score", "nights", "base_price_usd",
                      "taxes_and_fees_usd", "total_price_usd", "price_per_night_usd", "fits_budget"]

def _parse_booked_units(label):
    """Returns (unit_count, evidence_text) from the unit configuration line, or (None, None) if it is not stated."""
    line = UNIT_LINE_PATTERN.search(label or "")
    if not line:
        return None, None
    segment = line.group(1).strip()
    counts = [int(n) for n in UNIT_COUNT_PATTERN.findall(segment)]
    return (sum(counts) if counts else 1), segment  # No number means a single unit ("Hotel room", "Entire studio")

def _parse_distance_km(text):
    match = DISTANCE_PATTERN.search(text or "")
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return round(value / 1000, 2) if match.group(2).lower() == "m" else round(value, 2)

def _parse_area(text):
    """Booking labels sometimes state a district before the distance, e.g. 'Nasr City • 11.1 km from downtown'."""
    match = AREA_PATTERN.search(text or "")
    if not match:
        return None
    area = re.sub(r"[‎‏‪-‮]", "", match.group(1)).strip(" .")
    return area or None

def resolve_booking_destination(label, city, deadline, cache_mode="default", evidence=None):
    """Canonical city -> Booking.com destination ID (pinned, or looked up once and verified)."""
    if city.get("booking_dest_id"):
        return {"dest_id": city["booking_dest_id"], "search_type": "CITY", "source": "pinned_mapping"}

    params = {"query": label, "languagecode": "en-us"}  # Request English destination names
    logger.info(f"[*] Resolving Booking.com destination ID for: {label}...")
    payload, _ = provider_get("booking_destination", params, deadline, cache_ttl_hours=DESTINATION_ID_TTL_HOURS,
                              cache_mode=cache_mode, evidence=evidence)
    results = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise TravelMateError("invalid_response", details={"reason": "destination_list_missing"})
    for item in results:
        if (isinstance(item, dict) and str(item.get("dest_type", "")).lower() == "city"
                and str(item.get("cc1", "")).lower() == city["country_code"]
                and _normalize_city_text(item.get("name") or item.get("city_name")) in {label.lower(), *city["aliases"]}
                and item.get("dest_id")):
            logger.info(f"[+] Verified destination ID: {item['dest_id']} ({item.get('label')})")
            return {"dest_id": str(item["dest_id"]), "search_type": "CITY", "source": "verified_lookup"}
    raise TravelMateError("unsupported_search", f"Booking.com did not return a verified city match for {label}.",
                          {"reason": "destination_not_verified"})

def fetch_hotel_offers(dest_id, search_type, trip, deadline, cache_mode="default", evidence=None):
    params = {
        "dest_id": dest_id,
        "search_type": search_type,
        "arrival_date": trip["start_date"],
        "departure_date": trip["return_date"],
        "adults": str(trip["adults"]),
        "room_qty": str(trip["adapter"]["rooms"]),
        "page_number": "1",
        "units": "metric",
        "temperature_unit": "c",
        "languagecode": "en-us",  # Request English hotel names and labels
        "currency_code": "USD"
    }
    logger.info(f"[*] Fetching hotels {trip['start_date']} -> {trip['return_date']} "
                f"({trip['adults']} adult(s), {trip['adapter']['rooms']} room(s))...")
    return provider_get("booking_hotels", params, deadline, cache_mode=cache_mode, evidence=evidence)

def normalize_hotel_offers(payload, trip, city, fx, provenance):
    """
    Returns (hotel_offers, public_offers, candidates, provenance_entries, coverage).
      hotel_offers  -> exact BE-04 HotelOffer fields (hotel_id is an int; offer ID = str(hotel_id))
      public_offers -> v0.4 public hotel schema (docs/contracts/api-v0.4.schema.json)
      candidates    -> BE-04 OfferCandidate {id, base_usd, additional_fees_usd, included_in_base}
    A hotel is eligible only if its dates, adult count (and unit count when stated) and location match the request.
    Final price = grossPrice + excludedPrice; missing or unconvertible taxes stay unknown (never 0).
    """
    section = payload.get("data") if isinstance(payload, dict) else None
    hotel_list = section.get("hotels") if isinstance(section, dict) else None
    if not isinstance(hotel_list, list):
        raise TravelMateError("invalid_response", details={"reason": "missing_hotels_list"})

    rooms = trip["adapter"]["rooms"]
    excluded = {"date_mismatch": 0, "occupancy_mismatch": 0, "occupancy_unverified": 0, "destination_mismatch": 0,
                "destination_unverified": 0, "invalid_price": 0, "unconvertible_currency": 0, "malformed": 0,
                "duplicate": 0}
    hotel_offers, public_offers, candidates, provenance_entries, seen_ids = [], [], [], [], set()

    for h in hotel_list:
        prop = h.get("property") if isinstance(h, dict) else None
        if not isinstance(prop, dict):
            excluded["malformed"] += 1
            continue
        raw_id = h.get("hotel_id") or prop.get("id")
        if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0 or not prop.get("name"):
            excluded["malformed"] += 1
            continue
        if raw_id in seen_ids:
            excluded["duplicate"] += 1
            continue
        label = str(h.get("accessibilityLabel") or "")

        # 1. Dates must match exactly
        if prop.get("checkinDate") != trip["start_date"] or prop.get("checkoutDate") != trip["return_date"]:
            excluded["date_mismatch"] += 1
            continue

        # 2. Adult occupancy must be stated and match; unit count must match when the provider states it
        occupancy = OCCUPANCY_PATTERN.search(label)
        if not occupancy:
            excluded["occupancy_unverified"] += 1
            continue
        if int(occupancy.group(1)) != trip["nights"]:
            excluded["date_mismatch"] += 1
            continue
        if int(occupancy.group(2)) != trip["adults"]:
            excluded["occupancy_mismatch"] += 1
            continue
        booked_units, units_evidence = _parse_booked_units(label)
        if booked_units is not None and booked_units != rooms:
            excluded["occupancy_mismatch"] += 1
            continue

        # 3. Location must be inside the canonical city coverage radius (or the city name must match)
        latitude, longitude = prop.get("latitude"), prop.get("longitude")
        if prop.get("countryCode") and str(prop["countryCode"]).lower() != city["country_code"]:
            excluded["destination_mismatch"] += 1
            continue
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            if haversine_km(latitude, longitude, *city["center"]) > HOTEL_COVERAGE_RADIUS_KM:
                excluded["destination_mismatch"] += 1
                continue
        elif _normalize_city_text(prop.get("wishlistName")) != trip["destination_city"].lower():
            excluded["destination_unverified"] += 1
            continue

        # 4. Prices: reject negative / NaN / Infinity, convert under the policy, never count fees twice
        breakdown = prop.get("priceBreakdown") or {}
        gross = breakdown.get("grossPrice") or {}
        base_price = valid_amount(gross.get("value"))
        if base_price is None:
            excluded["invalid_price"] += 1
            continue
        base_usd, base_conversion = convert_to_usd(base_price, gross.get("currency"), fx)
        if base_usd is None:
            excluded["unconvertible_currency"] += 1
            continue

        excluded_charges = breakdown.get("excludedPrice")
        taxes_usd, taxes_conversion = None, None
        if isinstance(excluded_charges, dict) and "value" in excluded_charges:
            taxes_value = valid_amount(excluded_charges.get("value"), allow_zero=True)
            if taxes_value is None:
                excluded["invalid_price"] += 1
                continue
            taxes_usd, taxes_conversion = convert_to_usd(
                taxes_value, excluded_charges.get("currency") or gross.get("currency"), fx)
        # Fee status: included (0 extra), additional_known (> 0 extra) or unknown (missing / unconvertible)
        if taxes_usd is None:
            fee_status, included_in_base = "unknown", False
        elif taxes_usd == 0:
            fee_status, included_in_base = "included", True
        else:
            fee_status, included_in_base = "additional_known", False
        total_usd = round_money(base_usd + taxes_usd) if taxes_usd is not None else None

        star = prop.get("accuratePropertyClass") or prop.get("propertyClass") or prop.get("qualityClass")
        star_rating = int(star) if isinstance(star, (int, float)) and not isinstance(star, bool) and star > 0 else None
        # Booking reports reviewScore 0 for properties without reviews: that is "no rating", not a 0/10 rating
        review = prop.get("reviewScore")
        review_score = float(review) if isinstance(review, (int, float)) and not isinstance(review, bool) \
            and 0 < review <= 10 and prop.get("reviewCount") != 0 else None
        offer_id = str(raw_id)
        retrieved_at = normalize_utc_timestamp(provenance["retrieved_at"]) or utc_now_iso()
        seen_ids.add(raw_id)

        hotel_offers.append({
            "hotel_id": raw_id,
            "name": prop["name"],
            "star_rating": star_rating,
            "review_score": review_score,
            "nights": trip["nights"],
            "base_price_usd": base_usd,
            "taxes_and_fees_usd": taxes_usd,
            "total_price_usd": total_usd,
            "price_per_night_usd": round_money(total_usd / trip["nights"]) if total_usd is not None else None,
            "fits_budget": None  # Budget fit is decided by BE-04, not by the adapter
        })
        public_offers.append({
            "id": offer_id,
            "source": HOTEL_SOURCE_LABEL,
            "retrieved_at": retrieved_at,
            "price": {"amount_usd": base_usd, "kind": "provider", "coverage": "entire_trip_all_travelers"},
            "taxes": {"status": fee_status,
                      "additional_amount_usd": 0.0 if fee_status == "included" else
                      (taxes_usd if fee_status == "additional_known" else None)},
            "name": prop["name"],
            "area": _parse_area(label),
            "check_in": prop["checkinDate"],
            "check_out": prop["checkoutDate"],
            "occupancy_adults": trip["adults"],
            "room_qty": booked_units
        })
        candidates.append({"id": offer_id, "base_usd": base_usd,
                           "additional_fees_usd": taxes_usd if fee_status == "additional_known" else None,
                           "included_in_base": included_in_base})
        provenance_entries.append({
            "offer_id": offer_id,
            "category": "hotels",
            "source": HOTEL_SOURCE_LABEL,
            "provider_offer_id": raw_id,
            "retrieved_at": retrieved_at,
            "cache_status": provenance["cache_status"],
            "original_currency": str(gross.get("currency") or "").upper(),
            "original_amount": base_price,
            "quote_timestamp": None,
            "conversion": base_conversion,
            "taxes_conversion": taxes_conversion,
            "provider_query": provenance["query_parameters"],
            "coverage_evidence": (
                f"Provider label '{occupancy.group(0)}'"
                + (f" and '{units_evidence}'" if units_evidence else " (unit count not stated)")
                + f"; check-in {prop['checkinDate']} / check-out {prop['checkoutDate']}; "
                + {"included": "excludedPrice is 0, so the base price includes all known fees.",
                   "additional_known": "excludedPrice reported as additional taxes and fees, counted once.",
                   "unknown": "excludedPrice missing or not convertible; fees unknown."}[fee_status]),
            "fees": {"status": fee_status, "included_in_base": included_in_base,
                     "additional_fees_usd": taxes_usd if fee_status == "additional_known" else None},
            "price_authority": "live_provider_quote",
            "distance_from_center_km": _parse_distance_km(label),
            "airport_timezones": None
        })

    coverage = {"hotels_returned": len(hotel_list), "eligible": len(hotel_offers), "excluded": excluded,
                "page_number": 1, "coverage_radius_km": HOTEL_COVERAGE_RADIUS_KM}
    return hotel_offers, public_offers, candidates, provenance_entries, coverage

# ==========================================
# 13. LIVE TRAVEL ADAPTER BOUNDARY (search_travel)
# ==========================================
def _empty_flights(reason_code):
    """
    The flights category in every state (adapter-contracts.md): offers and public_offers are v0.4 public flight
    offers, [] whenever status is unavailable; legs holds BE-04 SelectedFlight options per direction.
    """
    return {"status": "unavailable", "reason_code": reason_code, "price_authority": None,
            "offers": [], "public_offers": [], "selected_offer": None,
            "selected_outbound_flight": None, "selected_return_flight": None, "schedule": None,
            "legs": {"outbound": [], "return": []}, "nearby_airport_alternatives": {"outbound": [], "return": []},
            "indicative_quotes": None, "coverage": {}}

def _empty_hotels(reason_code):
    """The hotels category in every state: offers are BE-04 HotelOffer (agreed point 1), public_offers are v0.4."""
    return {"status": "unavailable", "reason_code": reason_code, "offers": [], "public_offers": [], "coverage": {},
            "destination_mapping": None}

def _category_reason(error):
    """Contract reason_code for a failed category (a missing provider key means the category is not configured)."""
    return "not_configured" if error.details.get("reason") == "missing_credentials" else error.code

def _search_flights(trip, deadline, fx, cache_mode, evidence, warnings, provenance_out):
    flights = _empty_flights("not_configured")
    if FLIGHT_MODE == "live":
        return _search_live_flights(trip, deadline, cache_mode, evidence, warnings, provenance_out, flights)
    if FLIGHT_MODE != "indicative":
        warnings.append(build_warning("FLIGHTS_UNAVAILABLE", "Flight prices are not configured for live search; "
                                      "the flight provider cannot return round-trip prices for all travelers."))
        return flights, []

    # Indicative mode (PR #25 review, item 1): Skyscanner cached single-adult quotes are kept FOR INFORMATION ONLY.
    # They never become selected legs or BE-04 candidates, even when a quote matches the requested date, so an
    # indicative price can never be counted as a provider price in the budget.
    flights["price_authority"] = "indicative"
    flights["reason_code"] = "not_configured"  # Live flight prices are not configured in this mode
    flights["indicative_quotes"] = {"exact_date": {"outbound": [], "return": []},
                                    "alternative_dates": {"outbound": [], "return": []},
                                    "usage": "information only; never selected, never sent to BE-04"}
    adapter = trip["adapter"]
    directions = [("outbound", adapter["origin_airport"], adapter["destination_airport"], trip["start_date"])]
    if trip["trip_type"] == "round_trip":
        directions.append(("return", adapter["destination_airport"], adapter["origin_airport"], trip["return_date"]))
    try:
        for direction, origin, destination, travel_date in directions:
            payload, provenance = fetch_flight_quotes(origin, destination, travel_date, trip["adults"], deadline,
                                                      f"{direction.title()} Flight", cache_mode, evidence)
            exact, alternatives, entries, coverage = normalize_flight_quotes(
                payload, direction, origin, destination, travel_date, trip["adults"], fx, provenance)
            flights["indicative_quotes"]["exact_date"][direction] = exact
            flights["indicative_quotes"]["alternative_dates"][direction] = alternatives
            flights["coverage"][direction] = coverage
            provenance_out.extend(dict(entry, informational_only=True) for entry in entries)
            if coverage["excluded"]["unconvertible_currency"]:
                warnings.append(build_warning("CURRENCY_UNAVAILABLE",
                                              f"{coverage['excluded']['unconvertible_currency']} {direction} flight quote(s) "
                                              f"in {coverage['returned_currency']} were excluded: " +
                                              (FX_DISABLED_NOTE if not FX_CONVERSION_ENABLED else "no valid USD rate.")))
    except TravelMateError as error:
        flights["reason_code"] = _category_reason(error)
        warnings.append(build_warning("TRAVEL_RATE_LIMITED" if error.code == "rate_limited" else
                                      "TRAVEL_TIMEOUT" if error.code == "timeout" else "FLIGHTS_UNAVAILABLE",
                                      f"Flight search failed ({flights['reason_code']})."))
        return flights, []

    warnings.append(build_warning("FLIGHT_PRICES_INDICATIVE", "Indicative cached flight quotes are shown for "
                                  "information only. They are never selected and never used in the budget."))
    return flights, []  # No selected legs and no candidates in indicative mode

def _search_live_flights(trip, deadline, cache_mode, evidence, warnings, provenance_out, flights):
    """Google Flights live mode: real per-leg one-way quotes, v0.4 public offers and BE-04 candidates."""
    flights["price_authority"] = "live_provider_quote"
    try:
        outbound, returning, offers, candidates, entries, selections, coverage, alternatives = search_google_flights(
            trip, deadline, cache_mode, evidence)
    except TravelMateError as error:
        flights["reason_code"] = _category_reason(error)
        warnings.append(build_warning("TRAVEL_RATE_LIMITED" if error.code == "rate_limited" else
                                      "TRAVEL_TIMEOUT" if error.code == "timeout" else "FLIGHTS_UNAVAILABLE",
                                      f"Flight search failed ({flights['reason_code']})."))
        return flights, []
    flights["coverage"] = coverage
    flights["legs"] = {"outbound": outbound, "return": returning}
    flights["nearby_airport_alternatives"] = alternatives
    for alternative in alternatives["outbound"] + alternatives["return"]:
        warnings.append(build_warning("NEARBY_AIRPORT_ALTERNATIVE", f"{alternative['label']}: "
                                      f"{alternative['airline']} ${alternative['total_price_usd']:.2f} "
                                      "(shown as an alternative only, not selected)."))
    if not offers:
        flights["reason_code"] = "no_results"
        warnings.append(build_warning("FLIGHTS_UNAVAILABLE", "No flight matched the requested dates, route and "
                                      "travelers for every requested direction."))
        return flights, []
    provenance_out.extend(entries)
    # The cheapest offer is selected as a whole: its legs (each with its REAL provider total), times and evidence
    # all belong to the same flights, so BE-04 prices exactly the flights the offer ID names
    selected = selections[0]
    flights.update(status="available", reason_code=None, offers=offers, public_offers=offers,
                   selected_outbound_flight=selected["outbound"], selected_return_flight=selected["return"],
                   selected_offer=selected["offer"], schedule=selected["schedule"])
    return flights, candidates

def _search_hotels(trip, deadline, fx, cache_mode, evidence, warnings, provenance_out):
    hotels = _empty_hotels("provider_error")
    label = trip["destination_city"]
    try:
        destination = resolve_booking_destination(label, SUPPORTED_CITIES[label], deadline, cache_mode, evidence)
        hotels["destination_mapping"] = destination
        payload, provenance = fetch_hotel_offers(destination["dest_id"], destination["search_type"], trip, deadline,
                                                 cache_mode, evidence)
        offers, public_offers, candidates, entries, coverage = normalize_hotel_offers(
            payload, trip, SUPPORTED_CITIES[label], fx, provenance)
    except TravelMateError as error:
        hotels["reason_code"] = _category_reason(error)
        warnings.append(build_warning("TRAVEL_RATE_LIMITED" if error.code == "rate_limited" else
                                      "TRAVEL_TIMEOUT" if error.code == "timeout" else "HOTELS_UNAVAILABLE",
                                      f"Hotel search failed ({hotels['reason_code']})."))
        return hotels, []

    hotels.update(offers=offers, public_offers=public_offers, coverage=coverage)
    provenance_out.extend(entries)
    if coverage["excluded"]["unconvertible_currency"]:
        warnings.append(build_warning("CURRENCY_UNAVAILABLE", f"{coverage['excluded']['unconvertible_currency']} hotel "
                                      "offer(s) were excluded: " +
                                      (FX_DISABLED_NOTE if not FX_CONVERSION_ENABLED else "no valid USD rate.")))
    unknown_fees = sum(1 for o in public_offers if o["taxes"]["status"] == "unknown")
    if unknown_fees:
        warnings.append(build_warning("TAXES_UNKNOWN", f"{unknown_fees} hotel offer(s) have unknown taxes and fees."))
    if not offers:
        hotels["reason_code"] = "no_results"
        warnings.append(build_warning("HOTELS_UNAVAILABLE", "No hotel matched the requested dates, travelers and city."))
        return hotels, []
    hotels.update(status="available", reason_code=None)
    return hotels, candidates

def _data_mode(provenance_entries):
    statuses = set()
    for entry in provenance_entries:
        status = entry.get("cache_status")
        statuses.update(status.values() if isinstance(status, dict) else [status])  # Live flights: per-call statuses
    return "includes_cached" if "hit" in statuses else "live"

def _search_travel_validated(trip, deadline, request_id, categories=("flights", "hotels"), cache_mode="default",
                             evidence=None):
    fx = LazyExchangeRates(deadline, cache_mode, evidence)
    flight_warnings, flight_provenance, hotel_warnings, hotel_provenance = [], [], [], []

    def guarded(search, empty, label, warning_code, warnings, provenance_out):
        """An unexpected programming failure in one category becomes that category's warning (adapter-contracts.md)."""
        try:
            return search(trip, deadline, fx, cache_mode, evidence, warnings, provenance_out)
        except Exception:
            logger.exception(f"[-] Unexpected {label} adapter error (request_id={request_id}).")
            provenance_out.clear()
            warnings.append(build_warning(warning_code, f"{label.title()} search failed (provider_error)."))
            return empty("provider_error"), []

    # Flights and hotels are independent: they run in parallel so a slow provider never consumes the other's time.
    # A category that was not requested is still returned explicitly (unavailable / not_requested), never null.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="travel") as pool:
        flight_future = pool.submit(guarded, _search_flights, _empty_flights, "flight", "FLIGHTS_UNAVAILABLE",
                                    flight_warnings, flight_provenance) if "flights" in categories else None
        hotel_future = pool.submit(guarded, _search_hotels, _empty_hotels, "hotel", "HOTELS_UNAVAILABLE",
                                   hotel_warnings, hotel_provenance) if "hotels" in categories else None
        flights, flight_candidates = flight_future.result() if flight_future else (_empty_flights("not_requested"), [])
        hotels, hotel_candidates = hotel_future.result() if hotel_future else (_empty_hotels("not_requested"), [])
    warnings, provenance = flight_warnings + hotel_warnings, flight_provenance + hotel_provenance
    if fx.policy and not fx.policy.get("available"):
        warnings.append(build_warning("CURRENCY_UNAVAILABLE", f"Exchange rates unavailable ({fx.policy.get('reason')}); "
                                      "non-USD quotes were excluded."))
    return {
        "request_id": request_id,
        "status": "ok",
        "trip_request": public_trip_request(trip),
        "flights": flights,
        "hotels": hotels,
        # Exact BE-04 ZiyadReportSlice travel fields (ai_recommendation_report is added by the engine / BE-03)
        "report_slice": {
            "flights_data": {"selected_outbound_flight": flights["selected_outbound_flight"],
                             "selected_return_flight": flights["selected_return_flight"]},
            "hotels_data": hotels["offers"]
        },
        # BE-04 OfferCandidate lists (string IDs + included_in_base) for fee-aware selection by BE-03
        "flight_candidates": flight_candidates,
        "hotel_candidates": hotel_candidates,
        "warnings": warnings,
        "provenance": provenance,
        "data_mode": _data_mode(provenance)
    }

def search_travel(trip_request, categories=("flights", "hotels"), deadline_at=None, request_id=None, rooms=None,
                  cache_mode="default", evidence=None, trip_type="round_trip"):
    """
    Live travel adapter boundary (adapter-contracts.md). Returns both category objects with
    status available | unavailable and reason_code, BE-04-ready report_slice and candidates, warnings and provenance.
    Never raises: invalid input, unsupported cities and unexpected errors are returned as {"status": "error", ...}.
    """
    request_id = request_id or new_request_id()
    try:
        trip = validate_request(trip_request, require_budget=False, rooms=rooms, trip_type=trip_type)
        deadline = resolve_deadline(deadline_at)
        categories = tuple(categories) if isinstance(categories, (list, tuple, set)) else (categories,)
        if not categories or not set(categories) <= {"flights", "hotels"}:
            raise TravelMateError("invalid_input", "categories must contain flights, hotels, or both.",
                                  {"fields": [{"field": "categories", "message": "Allowed: flights, hotels."}]})
        return _search_travel_validated(trip, deadline, request_id, categories, cache_mode, evidence)
    except TravelMateError as error:
        return {"request_id": request_id, "status": "error", "error": error.to_envelope(),
                "diagnostics": sanitize(error.details)}
    except Exception:
        logger.exception(f"[-] Unexpected search_travel error (request_id={request_id}).")
        return {"request_id": request_id, "status": "error", "error": build_error("internal_error"), "diagnostics": {}}

def select_default_hotel(hotel_offers, candidates):
    """
    Prototype selection mirroring BE-04 select_offer: prefer known totals (included or known fees), lowest
    base + fees, tie-break by ID; fall back to the lowest base only if every fee is unknown. BE-03 owns the final choice.
    """
    if not candidates:
        return None, None
    known = [c for c in candidates if c["included_in_base"] or c["additional_fees_usd"] is not None]
    pool = known or candidates
    chosen = min(pool, key=lambda c: (round_money(c["base_usd"] + (c["additional_fees_usd"] or 0)), c["id"]))
    hotel = next(h for h in hotel_offers if str(h["hotel_id"]) == chosen["id"])
    return hotel, chosen["id"]

# ==========================================
# 14. STRUCTURED AI ITINERARY ADAPTER (generate_itinerary)
# ==========================================
ALLOWED_ACTIVITY_KINDS = {"estimate", "unknown"}  # "provider" is never allowed for AI activities
MEAL_PATTERN = re.compile(r"\b(breakfast|brunch|lunch|dinner|supper|meal|restaurant|street food|food tour|dining)\b",
                          re.IGNORECASE)

def _approved_policy_ids():
    return {p.strip() for p in os.getenv("TRAVELMATE_APPROVED_POLICY_IDS", "").split(",") if p.strip()}

def validate_estimation_policy(policy):
    """
    Contract shape {id, food, local_transport}: id is a reviewed policy identifier, food / local_transport are
    methodology descriptions (or null). Returns the policy only if its id is in TRAVELMATE_APPROVED_POLICY_IDS.
    """
    if not isinstance(policy, dict) or not isinstance(policy.get("id"), str) or not policy["id"].strip():
        return None
    if policy["id"].strip() not in _approved_policy_ids():
        return None
    return {"id": policy["id"].strip(),
            "food": policy.get("food") if isinstance(policy.get("food"), str) and policy["food"].strip() else None,
            "local_transport": policy.get("local_transport")
            if isinstance(policy.get("local_transport"), str) and policy["local_transport"].strip() else None}

def unknown_estimate(basis):
    return {"amount_usd": None, "kind": "unknown", "basis": basis, "policy_id": None}

def _flight_offer_is_eligible(leg, trip, expected_date):
    """A selected flight leg must be an exact-date leg whose date flag is consistent with its dates."""
    if not isinstance(leg, dict):
        return False
    flight_date, requested = parse_iso_date(leg.get("flight_date")), parse_iso_date(leg.get("requested_date"))
    return (flight_date is not None and leg.get("date_matches_request") is True and flight_date == requested
            and leg.get("requested_date") == expected_date and leg.get("travelers") == trip["adults"])

def _round_trip_offer_is_eligible(offer, trip):
    """A round-trip offer must depart on the requested LOCAL dates, cover all adults and carry a provider price."""
    price = offer.get("price") or {}
    return_ok = offer.get("return_departure_at") is None if trip["trip_type"] == "one_way" else         utc_to_local_date(offer.get("return_departure_at"), offer.get("arrival_airport_code")) == trip["return_date"]
    return (utc_to_local_date(offer.get("outbound_departure_at"), offer.get("departure_airport_code")) == trip["start_date"]
            and return_ok
            and offer.get("adults") == trip["adults"] and price.get("kind") == "provider"
            and price.get("coverage") == "entire_trip_all_travelers")

def _eligible_selected_offers(trip, selected_offers, warnings):
    """
    Accepts {flight: {selected_outbound_flight, selected_return_flight} | null, hotel: HotelOffer | public offer | null}.
    Ineligible offers (alternative dates, inconsistent flags, wrong nights) are dropped before the AI call.
    """
    selected_offers = selected_offers if isinstance(selected_offers, dict) else {}
    flight = selected_offers.get("flight") if isinstance(selected_offers.get("flight"), dict) else None
    outbound = (flight or {}).get("selected_outbound_flight")
    returning = (flight or {}).get("selected_return_flight")
    clean_flight = None
    if flight is not None and "outbound_departure_at" in flight:  # v0.4 round-trip offer (live mode)
        if _round_trip_offer_is_eligible(flight, trip):
            clean_flight = flight
        else:
            warnings.append(build_warning("FLIGHT_DATE_MISMATCH_EXCLUDED", "Selected round-trip flight does not match "
                                          "the requested local dates or travelers and was not sent to the AI."))
    elif outbound is not None or returning is not None:
        one_way = trip["trip_type"] == "one_way"
        if (_flight_offer_is_eligible(outbound, trip, trip["start_date"])
                and (returning is None if one_way else _flight_offer_is_eligible(returning, trip, trip["return_date"]))
                and _schedule_matches_legs(flight.get("schedule"), outbound, returning)):
            clean_flight = {"selected_outbound_flight": outbound, "selected_return_flight": returning,
                            "schedule": flight.get("schedule")}
        else:
            warnings.append(build_warning("FLIGHT_DATE_MISMATCH_EXCLUDED", "Selected flights were not exact-date "
                                          "request-matched offers and were not sent to the AI."))
    hotel = selected_offers.get("hotel")
    clean_hotel = None
    if isinstance(hotel, dict):
        nights_ok = hotel.get("nights") == trip["nights"] if "nights" in hotel else \
            (hotel.get("check_in") == trip["start_date"] and hotel.get("check_out") == trip["return_date"])
        if nights_ok:
            clean_hotel = hotel
        else:
            warnings.append(build_warning("HOTEL_MISMATCH_EXCLUDED", "Selected hotel did not match the requested stay "
                                          "and was not sent to the AI."))
    return clean_flight, clean_hotel

def _schedule_matches_legs(schedule, outbound, returning):
    """A local schedule may only describe the legs it is sent with (same BE-04 leg ID and same provider total)."""
    if not schedule:
        return True  # No times: the AI only sees the legs themselves
    for leg, times in ((outbound, schedule.get("outbound")), (returning, schedule.get("return"))):
        if leg is None or times is None:
            if (leg is None) != (times is None):
                return False
            continue
        if times.get("be04_leg_id") != flight_leg_id(leg) or \
                round_money(times.get("original_amount") or 0) != round_money(leg["total_price_usd"]):
            return False
    return True

def build_ai_context(trip, flight, hotel, travel_availability):
    def leg_view(leg):
        return None if leg is None else {k: leg.get(k) for k in [
            "airline", "flight_date", "origin_airport", "destination_airport", "stops_label",
            "price_per_person_usd", "total_price_usd"]}

    hotel_view = None
    if hotel is not None:
        hotel_view = {k: hotel.get(k) for k in ["name", "star_rating", "review_score", "nights", "base_price_usd",
                                                 "taxes_and_fees_usd", "total_price_usd"] if k in hotel}
        if "price" in hotel:  # Public v0.4 hotel offer
            hotel_view.update(name=hotel.get("name"), area=hotel.get("area"),
                              base_price_usd=hotel["price"].get("amount_usd"), taxes=hotel.get("taxes"))
    if flight is not None and "outbound_departure_at" in flight:  # Live round-trip offer
        def local_time(utc_text, airport):
            try:
                moment = datetime.fromisoformat(utc_text.replace("Z", "+00:00")).astimezone(ZoneInfo(AIRPORT_TIMEZONES[airport]))
                return moment.strftime("%Y-%m-%d %H:%M") + f" local ({airport})"
            except (KeyError, ValueError, ZoneInfoNotFoundError):
                return None
        flights_view = {"airline": flight.get("airline"),
                        "outbound_departure_local": local_time(flight["outbound_departure_at"], flight["departure_airport_code"]),
                        "return_departure_local": local_time(flight["return_departure_at"], flight["arrival_airport_code"]),
                        "round_trip_total_usd": (flight.get("price") or {}).get("amount_usd"),
                        "price_note": "Live provider round-trip total for all travelers, taxes included."}
    elif flight is not None:
        schedule = flight.get("schedule") or {}
        flights_view = {"outbound": leg_view(flight["selected_outbound_flight"]),
                        "return": leg_view(flight["selected_return_flight"]),
                        "outbound_departure_local": (schedule.get("outbound") or {}).get("departure_local"),
                        "return_departure_local": (schedule.get("return") or {}).get("departure_local"),
                        "price_note": "Live provider totals for all travelers, taxes included." if schedule
                        else "Indicative cached quotes."}
    else:
        flights_view = None
    return {
        "trip": public_trip_request(trip) | {"nights": trip["nights"]},
        "selected_flights": flights_view,
        "selected_hotel": hotel_view,
        "travel_availability": travel_availability
    }

def build_itinerary_messages(trip, context, policy):
    expected_dates = [(parse_iso_date(trip["start_date"]) + timedelta(days=i)).isoformat()
                      for i in range(trip["nights"] + 1)]
    if policy:
        ancillary_rule = (f'8. Return "ancillary_estimates" with "food" and "local_transport" objects '
                          f'{{"amount_usd": number, "basis": string}} for the WHOLE trip and ALL {trip["adults"]} '
                          f'traveler(s), following this reviewed policy (id "{policy["id"]}"): '
                          f'food: {policy["food"] or "not covered (return null)"}; '
                          f'local_transport: {policy["local_transport"] or "not covered (return null)"}.')
    else:
        ancillary_rule = '8. Do NOT estimate food or local transport. Return "ancillary_estimates": null.'
    system_message = ("You are the TravelMate itinerary planner. You return ONLY one valid JSON object. "
                      "All prices in the context were calculated by the TravelMate backend and are authoritative.")
    user_message = f"""
TRIP CONTEXT (authoritative):
{json.dumps(context, indent=2, ensure_ascii=False)}

RULES:
1. "itinerary" must contain exactly {len(expected_dates)} day objects, one per date, in this exact order: {", ".join(expected_dates)}.
2. Every day between the first and the last must have 1-4 activities. The first and last day may have 0 activities ONLY if "empty_day_reason" explains the travel reason; otherwise "empty_day_reason" is null.
3. Each activity: {{"order": 1, "name": string, "area": string, "description": string (max 300 chars), "category": "sightseeing" | "culture" | "nature" | "shopping" | "leisure" | "meal" | "other", "cost": {{"amount_usd": number or null, "kind": "estimate" or "unknown"}}}}. "order" starts at 1 in every day and is contiguous. cost.kind must NEVER be "provider".
4. cost.amount_usd is the estimated cost for ALL {trip["adults"]} traveler(s) together. "estimate" ALWAYS needs a number; if you have no number, use {{"amount_usd": null, "kind": "unknown"}}. Use 0 only for activities that are genuinely free.
5. Meals belong to the food category, never to activities: do not create meal-only activities; if you include one, set "category": "meal" and cost {{"amount_usd": 0, "kind": "estimate"}}.
6. Never include flight or hotel prices in activities. Never change, recalculate or invent any flight, hotel or budget number. If a flight or hotel is null or unavailable, plan the days anyway without assuming its time, price or name.
7. "price_explanation": 2-5 English sentences describing the selected flight and hotel prices using ONLY numbers that appear in TRIP CONTEXT, written exactly as given with a $ sign. If travel prices are unavailable, say so. Do not compute totals or remaining budget.
{ancillary_rule}
9. Write everything in English.

OUTPUT FORMAT (JSON only):
{{"itinerary": [{{"date": "YYYY-MM-DD", "activities": [], "empty_day_reason": "..."}}], "ancillary_estimates": null, "price_explanation": "..."}}
"""
    return [{"role": "system", "content": system_message}, {"role": "user", "content": user_message.strip()}], expected_dates

def _parse_ai_json(content):
    text = str(content or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise TravelMateError("invalid_output", details={"problems": ["AI output is not valid JSON."]})
    if not isinstance(parsed, dict):
        raise TravelMateError("invalid_output", details={"problems": ["AI output must be a JSON object."]})
    return parsed

def _is_meal_activity(activity):
    text = f"{activity.get('name') or ''} {activity.get('category') or ''}"
    return activity.get("category") == "meal" or bool(MEAL_PATTERN.search(text))

def validate_itinerary_output(parsed, expected_dates, warnings):
    """
    Strict schema + semantic validation (v0.4 day / activity schema). Returns the normalized itinerary or raises
    invalid_output. Meal costs are reassigned to the food category (amount 0) so they are never counted twice.
    """
    problems = []
    days = parsed.get("itinerary")
    if not isinstance(days, list):
        raise TravelMateError("invalid_output", details={"problems": ["'itinerary' must be a list."]})
    if len(days) != len(expected_dates):
        problems.append(f"Expected {len(expected_dates)} days (nights + 1), got {len(days)}.")

    normalized, meals_reassigned, blank_items_removed = [], 0, [0, 0]  # [blank items, empty estimates]
    for index, (day, expected_date) in enumerate(zip(days, expected_dates)):
        where = f"Day {index + 1}"
        if not isinstance(day, dict):
            problems.append(f"{where} must be an object.")
            continue
        if day.get("date") != expected_date:
            problems.append(f"{where} date must be {expected_date}, got {day.get('date')!r}.")
        is_travel_day = index in (0, len(expected_dates) - 1)
        activities = day.get("activities")
        if not isinstance(activities, list):
            problems.append(f"{where} activities must be a list.")
            activities = []
        # JSON-mode artifact seen live (2026-10-21): empty strings between activity objects. Only blank strings are
        # dropped; every other non-object item still fails validation.
        blank_items = sum(1 for a in activities if isinstance(a, str) and not a.strip())
        if blank_items:
            activities = [a for a in activities if not (isinstance(a, str) and not a.strip())]
            blank_items_removed[0] += blank_items
        if len(activities) > 4:
            problems.append(f"{where} has more than 4 activities.")
        if not activities and not is_travel_day:
            problems.append(f"{where} is not a travel day and must contain at least one activity.")
        reason = day.get("empty_day_reason")
        if not activities and not (isinstance(reason, str) and reason.strip()):
            problems.append(f"{where} has no activities and no empty_day_reason.")

        clean_activities = []
        for a_index, activity in enumerate(activities, start=1):
            a_where = f"{where} activity {a_index}"
            if not isinstance(activity, dict):
                problems.append(f"{a_where} must be an object.")
                continue
            if activity.get("order") != a_index or isinstance(activity.get("order"), bool):
                problems.append(f"{a_where} order must be {a_index} (contiguous from 1).")
            for field, limit in (("name", 120), ("area", 120), ("description", 400)):
                value = activity.get(field)
                if not isinstance(value, str) or not (1 <= len(value.strip()) <= limit):
                    problems.append(f"{a_where} needs a non-empty {field} (max {limit} characters).")
            cost = activity.get("cost") if isinstance(activity.get("cost"), dict) else {}
            kind, amount = cost.get("kind"), cost.get("amount_usd")
            if kind == "estimate" and amount is None:
                # Seen live (2026-10-21): an "estimate" without any number means the cost is unknown. Downgrading
                # never invents a value; the reverse ("unknown" with an amount) and invalid numbers still fail.
                kind = "unknown"
                blank_items_removed[1] += 1
            if kind not in ALLOWED_ACTIVITY_KINDS:
                problems.append(f"{a_where} cost.kind must be 'estimate' or 'unknown' (got {kind!r}).")
            elif kind == "estimate" and valid_amount(amount, allow_zero=True) is None:
                problems.append(f"{a_where} estimate needs a non-negative finite amount_usd.")
            elif kind == "unknown" and amount is not None:
                problems.append(f"{a_where} with kind 'unknown' must have a null amount_usd.")

            if _is_meal_activity(activity) and kind in ALLOWED_ACTIVITY_KINDS:
                if not (kind == "estimate" and amount == 0):
                    meals_reassigned += 1
                public_cost = {"amount_usd": 0.0, "kind": "estimate", "coverage": "all_travelers"}
                basis = "Meal cost is covered by the food category (not counted as an activity)."
            elif kind == "estimate" and valid_amount(amount, allow_zero=True) is not None:
                public_cost = {"amount_usd": round_money(amount), "kind": "estimate", "coverage": "all_travelers"}
                basis = "AI estimate for all travelers (not a provider price)."
            else:
                public_cost = {"amount_usd": None, "kind": "unknown", "coverage": None}
                basis = "AI could not estimate this cost."
            clean_activities.append({
                "order": a_index,
                "name": str(activity.get("name") or "").strip(),
                "area": str(activity.get("area") or "").strip(),
                "description": str(activity.get("description") or "").strip(),
                "cost": public_cost,
                "_budget_basis": basis
            })
        normalized.append({"date": day.get("date"), "activities": clean_activities,
                           "empty_day_reason": reason.strip() if not activities and isinstance(reason, str) else None})

    if problems:
        raise TravelMateError("invalid_output", details={"problems": problems[:25]})
    if blank_items_removed[0]:
        warnings.append(build_warning("AI_OUTPUT_NORMALIZED", f"{blank_items_removed[0]} blank item(s) between AI "
                                      "activities were removed before validation."))
    if blank_items_removed[1]:
        warnings.append(build_warning("AI_OUTPUT_NORMALIZED", f"{blank_items_removed[1]} activity cost(s) marked "
                                      "'estimate' without an amount were treated as unknown."))
    if meals_reassigned:
        warnings.append(build_warning("MEAL_COST_REASSIGNED", f"{meals_reassigned} meal activity cost(s) were moved to "
                                      "the food category to avoid double counting."))
    return normalized

def build_budget_activities(itinerary):
    """BE-04 ActivityItem list: {label, kind (estimate|unknown), amount_usd, activity_ref {date, order}, basis}."""
    return [{"label": a["name"], "kind": a["cost"]["kind"], "amount_usd": a["cost"]["amount_usd"],
             "activity_ref": {"date": day["date"], "order": a["order"]}, "basis": a["_budget_basis"]}
            for day in itinerary for a in day["activities"]]

def strip_internal_fields(itinerary):
    return [{"date": d["date"], "empty_day_reason": d["empty_day_reason"],
             "activities": [{k: v for k, v in a.items() if not k.startswith("_")} for a in d["activities"]]}
            for d in itinerary]

def build_ancillary_estimates(parsed, policy, warnings):
    """Food / local transport estimate objects (adapter-contracts.md). Unknown unless an approved policy applies."""
    if not policy:
        return {"food": unknown_estimate("No approved estimation policy."),
                "local_transport": unknown_estimate("No approved estimation policy.")}
    raw = parsed.get("ancillary_estimates") if isinstance(parsed.get("ancillary_estimates"), dict) else {}
    result = {}
    for key in ("food", "local_transport"):
        item = raw.get(key) if isinstance(raw.get(key), dict) else {}
        amount = valid_amount(item.get("amount_usd"), allow_zero=True)
        basis = item.get("basis")
        if policy[key] is None:
            result[key] = unknown_estimate(f"Policy {policy['id']} does not cover {key}.")
        elif amount is None or not isinstance(basis, str) or not basis.strip():
            result[key] = unknown_estimate(f"AI did not return a valid {key} estimate under policy {policy['id']}.")
            warnings.append(build_warning("ESTIMATE_UNAVAILABLE", f"{key} estimate missing or invalid; kept unknown."))
        else:
            result[key] = {"amount_usd": round_money(amount), "kind": "estimate", "basis": basis.strip()[:300],
                           "policy_id": policy["id"]}
    return result

def _collect_numbers(value, found):
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)) and math.isfinite(value):
        found.add(round_money(value))
    elif isinstance(value, dict):
        for v in value.values():
            _collect_numbers(v, found)
    elif isinstance(value, list):
        for v in value:
            _collect_numbers(v, found)
    return found

MONEY_IN_TEXT_PATTERN = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:USD|US dollars|dollars)\b")

def check_price_explanation(text, context):
    """Returns (explanation, rejected_numbers). The text is dropped if it contains any money value not in the context."""
    if not isinstance(text, str) or not text.strip():
        return None, []
    allowed = _collect_numbers(context, set())
    rejected = []
    for match in MONEY_IN_TEXT_PATTERN.finditer(text):
        raw = (match.group(1) or match.group(2)).replace(",", "")
        try:
            if round_money(float(raw)) not in allowed:
                rejected.append(raw)
        except ValueError:
            rejected.append(raw)
    return (None, rejected) if rejected else (text.strip(), [])

def _get_groq_client(timeout):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key.lower().startswith("your_"):
        raise TravelMateError("unavailable", "The AI provider is not configured.", {"reason": "missing_GROQ_API_KEY"})
    # max_retries=0: chargeable AI generation is NEVER retried automatically
    return groq.Groq(api_key=api_key, max_retries=0, timeout=timeout)

def _map_groq_error(error):
    """Maps provider errors to the four AI adapter codes: timeout, rate_limited, unavailable, invalid_output."""
    if isinstance(error, groq.APITimeoutError):
        return TravelMateError("timeout", details={"reason": "ai_timeout"})
    if isinstance(error, groq.RateLimitError):
        return TravelMateError("rate_limited", details={"reason": "ai_rate_limited"})
    if isinstance(error, groq.BadRequestError) and "json_validate_failed" in str(error):
        return TravelMateError("invalid_output", details={"problems": ["Provider JSON mode validation failed."]})
    if isinstance(error, (groq.AuthenticationError, groq.PermissionDeniedError)):
        return TravelMateError("unavailable", details={"reason": "ai_auth_rejected"})
    return TravelMateError("unavailable", details={"reason": f"ai_provider_error_{type(error).__name__}"})

def _generate_itinerary_validated(trip, selected_offers, travel_availability, estimation_policy, deadline,
                                  request_id, evidence=None):
    warnings = []
    provenance = {"provider": "Groq", "integration_type": "direct_official_api", "model": GROQ_MODEL,
                  "temperature": AI_TEMPERATURE, "response_format": "json_object", "automatic_retries": 0,
                  "requested_at": None, "completed_at": None, "latency_ms": None, "rate_limit": {}, "usage": None}

    def failure(error):
        return {"request_id": request_id, "status": "error", "error": error.to_envelope(),
                "diagnostics": sanitize(error.details), "warnings": warnings, "provenance": provenance}

    policy = validate_estimation_policy(estimation_policy)
    if estimation_policy is not None and policy is None and (estimation_policy or {}).get("id") is not None:
        warnings.append(build_warning("POLICY_NOT_APPROVED", "estimation_policy is not an approved policy; food and "
                                      "local transport stay unknown."))
    flight, hotel = _eligible_selected_offers(trip, selected_offers, warnings)
    context = build_ai_context(trip, flight, hotel, travel_availability or {})
    messages, expected_dates = build_itinerary_messages(trip, context, policy)
    if isinstance(evidence, dict):
        evidence["ai_input"] = {"model": GROQ_MODEL, "temperature": AI_TEMPERATURE, "messages": messages}

    remaining = seconds_left(deadline)
    if remaining < AI_MIN_SECONDS_REQUIRED:
        return failure(TravelMateError("timeout", details={"reason": "not_enough_time_for_ai", "seconds_left": round(remaining, 1)}))

    try:
        client = _get_groq_client(timeout=min(AI_TIMEOUT_SECONDS, remaining))
        logger.info(f"[*] Requesting structured itinerary from Groq ({GROQ_MODEL}, single attempt)...")
        provenance["requested_at"] = utc_now_iso()
        started = time.monotonic()
        raw_response = client.chat.completions.with_raw_response.create(
            messages=messages,
            model=GROQ_MODEL,
            temperature=AI_TEMPERATURE,
            response_format={"type": "json_object"},
            max_completion_tokens=AI_MAX_COMPLETION_TOKENS
        )
        provenance["latency_ms"] = int((time.monotonic() - started) * 1000)
        provenance["completed_at"] = utc_now_iso()
        provenance["rate_limit"] = {k.lower(): v for k, v in raw_response.headers.items()
                                    if k.lower().startswith("x-ratelimit")}
        completion = raw_response.parse()
        usage = getattr(completion, "usage", None)
        provenance["usage"] = {"prompt_tokens": getattr(usage, "prompt_tokens", None),
                               "completion_tokens": getattr(usage, "completion_tokens", None)} if usage else None
        content = completion.choices[0].message.content
        logger.info(f"[+] Groq responded in {provenance['latency_ms']} ms.")
    except TravelMateError as error:
        return failure(error)
    except groq.APIError as error:
        mapped = _map_groq_error(error)
        logger.error(f"[-] AI call failed: {mapped.code} ({type(error).__name__}).")
        return failure(mapped)

    if isinstance(evidence, dict):
        evidence["ai_raw_output"] = content
    try:
        parsed = _parse_ai_json(content)
        itinerary = validate_itinerary_output(parsed, expected_dates, warnings)
    except TravelMateError as error:
        logger.error(f"[-] AI output rejected: {error.details.get('problems', [])[:3]}")
        return failure(error)

    explanation, rejected = check_price_explanation(parsed.get("price_explanation"), context)
    if rejected:
        warnings.append(build_warning("PRICE_EXPLANATION_DROPPED", "The AI price explanation contained numbers that "
                                      f"are not in the backend data and was dropped: {rejected[:5]}"))
    return {
        "request_id": request_id,
        "status": "ok",
        "itinerary": strip_internal_fields(itinerary),
        "ancillary_estimates": build_ancillary_estimates(parsed, policy, warnings),
        "budget_activities": build_budget_activities(itinerary),  # Ready for BE-04 BudgetInput.activities
        "price_explanation": explanation,
        "warnings": warnings,
        "provenance": provenance
    }

def generate_itinerary(trip_request, selected_offers, travel_availability, estimation_policy=None, deadline_at=None,
                       request_id=None, evidence=None):
    """
    AI itinerary adapter boundary (adapter-contracts.md). Success: {"status": "ok", "itinerary", "ancillary_estimates",
    "budget_activities", "price_explanation", ...}. Failure: {"status": "error", "error": {code, message}} with code
    timeout | rate_limited | unavailable | invalid_output (or invalid_input / internal_error at the boundary).
    The AI call is made at most once. Works without any flight or hotel offer (both may be null).
    """
    request_id = request_id or new_request_id()
    try:
        trip = validate_request(trip_request, require_budget=False)
        deadline = resolve_deadline(deadline_at)
        return _generate_itinerary_validated(trip, selected_offers, travel_availability, estimation_policy, deadline,
                                             request_id, evidence)
    except TravelMateError as error:
        return {"request_id": request_id, "status": "error", "error": error.to_envelope(),
                "diagnostics": sanitize(error.details), "warnings": [], "provenance": None}
    except Exception:
        logger.exception(f"[-] Unexpected generate_itinerary error (request_id={request_id}).")
        return {"request_id": request_id, "status": "error", "error": build_error("internal_error"),
                "diagnostics": {}, "warnings": [], "provenance": None}

# ==========================================
# 15. PROTOTYPE ORCHESTRATION (BE-03 ROLE, LOCAL TESTING & EVIDENCE ONLY)
# ==========================================
def save_final_report(result, file_path=None):
    file_path = file_path or REPORT_FILE
    try:
        atomic_write_json(file_path, result)
        logger.info(f"[+] Final report saved to '{file_path}'")
    except OSError as e:
        logger.error(f"[-] Could not save final report ({type(e).__name__}).")

def _empty_engine_response(request_id, error, diagnostics=None, trip_request=None):
    return {"status": "error", "request_id": request_id, "generated_at": utc_now_iso(), "error": error,
            "diagnostics": sanitize(diagnostics or {}), "warnings": [], "trip_request": trip_request or {},
            "live_integration_status": "no_price", "travel": None, "selected_offers": None, "ai_itinerary": None,
            "report_slice": None, "be04_budget_input": None}

def _run_engine_steps(request_data, deadline_at, request_id, estimation_policy, cache_mode, evidence):
    # Step 1: Validate the public request (before any external call)
    try:
        trip = validate_request(request_data)
        deadline = resolve_deadline(deadline_at)
    except TravelMateError as error:
        return _empty_engine_response(request_id, error.to_envelope(), error.details)
    if isinstance(evidence, dict):
        evidence["inputs"] = {"request_data": request_data, "validated_trip": trip, "deadline_at": deadline.isoformat(),
                              "estimation_policy": estimation_policy, "flight_mode": FLIGHT_MODE}
    logger.info(f"[!] Processing request {request_id}: {trip['departure_city']} -> {trip['destination_city']}...")

    # Step 2: Live travel adapter (flights + hotels in parallel). Travel failures never stop generation.
    # The travel phase gets its own earlier deadline so time is always left for the AI itinerary.
    travel_deadline = deadline - timedelta(seconds=AI_RESERVED_SECONDS) \
        if seconds_left(deadline) > AI_RESERVED_SECONDS + PER_ATTEMPT_TIMEOUT_SECONDS else deadline
    travel = _search_travel_validated(trip, travel_deadline, request_id, cache_mode=cache_mode, evidence=evidence)

    # Step 3: Prototype selection (BE-03 owns the final choice): exact-date flights + fee-aware hotel
    flights_data = travel["report_slice"]["flights_data"]
    selected_hotel, selected_hotel_offer_id = select_default_hotel(travel["hotels"]["offers"], travel["hotel_candidates"])
    outbound_leg, return_leg = flights_data["selected_outbound_flight"], flights_data["selected_return_flight"]
    one_way = trip["trip_type"] == "one_way"
    if outbound_leg and (return_leg or one_way):
        selected_flight_offer_id = (travel["flights"].get("selected_offer") or {}).get("id")
        # Legs (real per-leg totals) + local schedule so the AI can plan around real departure times
        selected_flight = {**flights_data, "schedule": travel["flights"].get("schedule")}
    else:
        selected_flight_offer_id, selected_flight = None, None
    be04_flight_offer_id = (round_trip_offer_id(outbound_leg, return_leg) if return_leg else flight_leg_id(outbound_leg)) \
        if selected_flight_offer_id else None
    if isinstance(evidence, dict):
        evidence["normalized_context"] = {"search_travel": travel, "selected_hotel_offer_id": selected_hotel_offer_id,
                                          "selected_flight_offer_id": selected_flight_offer_id}

    # Step 4: Structured AI itinerary (single attempt). Always runs, even without any travel offer.
    availability = {"flights": "live" if travel["flights"]["status"] == "available" else "unavailable",
                    "hotels": "live" if travel["hotels"]["status"] == "available" else "unavailable"}
    ai = _generate_itinerary_validated(trip, {"flight": selected_flight, "hotel": selected_hotel},
                                       availability, estimation_policy, deadline, request_id, evidence)
    if isinstance(evidence, dict):
        evidence["ai_validated_output"] = {k: ai.get(k) for k in
                                           ["status", "itinerary", "ancillary_estimates", "budget_activities",
                                            "price_explanation", "error"]}

    warnings = travel["warnings"] + ai["warnings"]
    ancillary = ai.get("ancillary_estimates") or {}
    report_slice = {"flights_data": flights_data, "hotels_data": travel["report_slice"]["hotels_data"],
                    "ai_recommendation_report": ai.get("price_explanation") or ""}
    be04_input = None
    if ai["status"] == "ok":
        be04_input = {"budget_usd": trip["budget_usd"], "flights_data": flights_data, "selected_hotel": selected_hotel,
                      "activities": ai["budget_activities"],
                      "food": (ancillary.get("food") or {}).get("amount_usd"),
                      "local_transport": (ancillary.get("local_transport") or {}).get("amount_usd")}
        if one_way and selected_flight_offer_id:
            # BE-04's legs path needs both legs; a one-way trip is priced through candidate mode instead
            be04_input["flights_data"] = {"selected_outbound_flight": None, "selected_return_flight": None}
            be04_input["flight_candidates"] = [c for c in travel["flight_candidates"] if c["id"] == selected_flight_offer_id]
    else:
        warnings.append(build_warning("AI_UNAVAILABLE", f"Itinerary generation failed ({ai['error']['code']})."))

    priced = travel["hotels"]["status"] == "available" or travel["flights"]["status"] == "available"
    return {
        "status": "success" if ai["status"] == "ok" else "error",
        "request_id": request_id,
        "generated_at": utc_now_iso(),
        "error": None if ai["status"] == "ok" else ai["error"],
        "diagnostics": ai.get("diagnostics", {}),
        "warnings": warnings,
        "trip_request": public_trip_request(trip),
        "live_integration_status": "price_received" if priced else "no_price",
        "travel": travel,
        "selected_offers": {"selected_flight_offer_id": selected_flight_offer_id,
                            "be04_flight_offer_id": be04_flight_offer_id,
                            "selected_hotel_offer_id": selected_hotel_offer_id,
                            "selection_basis": "prototype default (BE-03 owns the final selection)"},
        "ai_itinerary": ai,
        "report_slice": report_slice,
        "be04_budget_input": be04_input
    }

def run_travelmate_engine(request_data: dict, save_report: bool = False, deadline_at=None, request_id=None,
                          estimation_policy=None, cache_mode="default", evidence=None) -> dict:
    """
    Prototype end-to-end pipeline for local testing and evidence (BE-03 owns the real orchestration).
    Never raises. save_report=True writes travelmate_final_report.json; it does NOT affect the provider cache
    (use cache_mode "off" to disable cache reads and writes).
    """
    request_id = request_id or new_request_id()
    try:
        result = _run_engine_steps(request_data, deadline_at, request_id, estimation_policy, cache_mode, evidence)
    except Exception:
        logger.exception(f"[-] Unexpected engine error (request_id={request_id}).")
        result = _empty_engine_response(request_id, build_error("internal_error"))
    if save_report:
        save_final_report(result)
    return result

# ==========================================
# 16. CONSOLE DISPLAY HELPERS (LOCAL TESTING ONLY)
# ==========================================
# These helpers only format text for the terminal. They never change the data returned to the backend,
# so the database and the website still receive the original (UTF-8) hotel names.
CONSOLE_WIDTH = 110
RTL_SCRIPT_PATTERN = re.compile(r"[֐-ࣿיִ-﷿ﹰ-﻿]+(?:\s+[֐-ࣿיִ-﷿ﹰ-﻿]+)*")
BIDI_CONTROL_PATTERN = re.compile(r"[‎‏‪-‮⁦-⁩]")

def to_console_name(text, fallback="(Non-Latin name)"):
    """Removes right-to-left script and direction marks so text renders left-to-right in Windows CMD."""
    if text is None:
        return fallback
    cleaned = BIDI_CONTROL_PATTERN.sub("", str(text))
    cleaned = RTL_SCRIPT_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"^[\s\-|,:()]+|[\s\-|,:(]+$", "", cleaned)  # Drop separators left behind
    return cleaned or fallback

def sanitize_for_console(value):
    """Recursively cleans every string inside a dict / list before pretty-printing it as JSON."""
    if isinstance(value, dict):
        return {k: sanitize_for_console(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_console(v) for v in value]
    if isinstance(value, str):
        return to_console_name(value, fallback="")
    return value

def format_money(value):
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "unknown"

def fit_cell(value, width):
    text = str(value)
    return (text[:width - 3] + "...") if len(text) > width else text.ljust(width)

def print_section(title):
    print("\n" + "=" * CONSOLE_WIDTH)
    print(f"  {title}")
    print("=" * CONSOLE_WIDTH)

def print_table(headers, rows):
    """Prints a fixed-width table. headers = [(label, width), ...]"""
    print("  " + " | ".join(fit_cell(label, width) for label, width in headers))
    print("  " + "-+-".join("-" * width for _, width in headers))
    if not rows:
        print("  (no data)")
    for row in rows:
        print("  " + " | ".join(fit_cell(cell, width) for cell, (_, width) in zip(row, headers)))

def print_engine_result(result, show_full_json=False):
    """Prints the structured engine response in clearly separated, readable sections."""
    print_section(f"TRAVELMATE RESULT  |  STATUS: {result['status'].upper()}  |  {result['request_id']}")
    if result["error"]:
        print(f"  [-] {result['error']['code']}: {result['error']['message']}")
        for field in (result.get("diagnostics") or {}).get("fields", []):
            print(f"      - {field['field']}: {field['message']}")
    for warning in result["warnings"]:
        print(f"  [!] {warning['code']}: {to_console_name(warning['message'])}")
    if not result.get("travel"):
        return

    print_section("1. TRIP REQUEST & AVAILABILITY")
    print(json.dumps(result["trip_request"], indent=4))
    travel = result["travel"]
    print(f"  live_integration_status: {result['live_integration_status']}")
    for category in ("flights", "hotels"):
        print(f"  {category:8}: {travel[category]['status']} (reason_code: {travel[category]['reason_code']})")

    flights = travel["flights"]
    flights_data = result["report_slice"]["flights_data"]
    schedule = flights.get("schedule") or {}
    print_section(f"2. FLIGHTS  (report_slice.flights_data)  |  prices: {flights.get('price_authority') or 'n/a'}")
    headers = [("Leg", 8), ("Airline", 20), ("Flight", 13), ("Departs (local)", 16), ("Exact", 5), ("Stops", 14),
               ("Total (all)", 11)]
    rows = []
    for leg_name, key, leg in (("Outbound", "outbound", flights_data["selected_outbound_flight"]),
                               ("Return", "return", flights_data["selected_return_flight"])):
        if leg:
            leg_schedule = schedule.get(key) or {}
            rows.append([leg_name, to_console_name(leg["airline"]), " + ".join(leg_schedule.get("flight_numbers", [])) or "-",
                         leg_schedule.get("departure_local") or leg["flight_date"],
                         "Yes" if leg["date_matches_request"] else "No", leg["stops_label"],
                         format_money(leg["total_price_usd"])])
    print_table(headers, rows)
    if rows:
        total = sum(l["total_price_usd"] for l in (flights_data["selected_outbound_flight"],
                                                    flights_data["selected_return_flight"]) if l)
        print(f"  Flight total for {result['trip_request']['adults']} traveler(s): {format_money(round_money(total))} "
              f"(sum of the legs, each priced by the provider)")
    for alternative in sum((flights.get("nearby_airport_alternatives") or {}).values(), []):
        print(f"  [i] {alternative['label']} | {to_console_name(alternative['airline'])} "
              f"{alternative['departure_local']} | {format_money(alternative['total_price_usd'])} (alternative only)")
    others = [o for o in flights.get("offers") or [] if o["id"] != result["selected_offers"]["selected_flight_offer_id"]]
    if others:
        print("  Other cheapest combinations: " + " | ".join(
            f"{to_console_name(o['airline'])} {format_money(o['price']['amount_usd'])}" for o in others))
    quotes = travel["flights"].get("indicative_quotes")
    if quotes:
        count = sum(len(v) for group in ("exact_date", "alternative_dates") for v in quotes[group].values())
        print(f"  ({count} indicative Skyscanner quote(s) available for information only; never selected or budgeted)")

    print_section("3. HOTELS  (report_slice.hotels_data) - verified dates & occupancy")
    selected_id = result["selected_offers"]["selected_hotel_offer_id"]
    headers = [("Sel", 3), ("Hotel", 32), ("Stars", 5), ("Rating", 6), ("Base", 10), ("Taxes", 9), ("Total", 10)]
    rows = [["*" if str(h["hotel_id"]) == selected_id else "", to_console_name(h["name"], fallback=f"Hotel #{h['hotel_id']}"),
             h["star_rating"] or "-", h["review_score"] or "-", format_money(h["base_price_usd"]),
             format_money(h["taxes_and_fees_usd"]), format_money(h["total_price_usd"])]
            for h in result["report_slice"]["hotels_data"]]
    print_table(headers, rows)

    ai = result["ai_itinerary"]
    print_section(f"4. AI ITINERARY  |  STATUS: {ai['status'].upper()}")
    if ai["status"] != "ok":
        print(f"  [-] {ai['error']['code']}: {ai['error']['message']}")
        for problem in (ai.get("diagnostics") or {}).get("problems", [])[:10]:
            print(f"      - {problem}")
    for day in ai.get("itinerary") or []:
        print(f"\n  {day['date']}")
        if not day["activities"]:
            print(f"    (no activities: {to_console_name(day['empty_day_reason'])})")
        for a in day["activities"]:
            cost = format_money(a["cost"]["amount_usd"]) + " (estimate)" if a["cost"]["kind"] == "estimate" else "cost unknown"
            print(f"    {a['order']}. {to_console_name(a['name'])} [{to_console_name(a['area'])}] | {cost}")
    for key, item in (ai.get("ancillary_estimates") or {}).items():
        print(f"  {key:16}: {item['kind']:8} {format_money(item['amount_usd'])}  {item['basis']}")
    print(f"\n  Price explanation: {to_console_name(result['report_slice']['ai_recommendation_report']) or '(none)'}")

    if show_full_json:
        print_section("FULL STRUCTURED JSON RESPONSE (console-safe copy)")
        print(json.dumps(sanitize_for_console(result), indent=4, ensure_ascii=False))
    print("\n" + "=" * CONSOLE_WIDTH)
    print(f"  [+] Full report saved to '{REPORT_FILE}'")
    print("=" * CONSOLE_WIDTH)

# ==========================================
# 17. MAIN EXECUTION (LOCAL CLI TESTING ONLY)
# ==========================================
def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Prevent UnicodeEncodeError crashes on Windows consoles that use a legacy code page
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    def prompt_until_valid(prompt_text, validator):
        """Keeps asking until the validator accepts the value."""
        while True:
            value, error = validator(input(prompt_text))
            if error is None:
                return value
            print(f"[-] {error}")

    def parse_int_text(text):
        return validate_adults(int(text)) if re.fullmatch(r"\s*\d+\s*", text) else (None, "Enter a whole number 1-4.")

    def parse_number_text(text):
        try:
            return validate_budget(float(text.replace(",", "")))
        except ValueError:
            return None, "Enter a number, e.g. 1500."

    print("\n--- Welcome to TravelMate (Flight & Hotel Assistant) ---")
    print(f"Supported cities: {', '.join(sorted(SUPPORTED_CITIES))}  |  Flight mode: {FLIGHT_MODE}")
    request_data = {
        "departure_city": prompt_until_valid("Departure city (e.g., Istanbul): ", lambda v: validate_city_name(v, "departure_city")),
        "destination_city": prompt_until_valid("Destination city (e.g., Cairo): ", lambda v: validate_city_name(v, "destination_city")),
        "start_date": prompt_until_valid("Start date (YYYY-MM-DD): ", lambda v: validate_date(v, "start_date")).isoformat(),
        "return_date": prompt_until_valid("Return date (YYYY-MM-DD): ", lambda v: validate_date(v, "return_date")).isoformat()
    }
    request_data["adults"] = prompt_until_valid("Adults (1-4): ", parse_int_text)
    request_data["budget_usd"] = prompt_until_valid("Total budget in USD (e.g., 1500): ", parse_number_text)

    print_section("PROCESSING REQUEST")
    result = run_travelmate_engine(request_data, save_report=True)
    print_engine_result(result, show_full_json="--json" in sys.argv)

if __name__ == "__main__":
    main()
