import requests
import json
import os
import re
import sys
import math
import time
import uuid
import hashlib
import logging
import tempfile
import threading
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from datetime import datetime, date, timedelta, timezone

import groq

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; plain environment variables still work
    load_dotenv = None

# Engine log messages go through this logger (silent by default when imported by a backend).
# The __main__ block below turns it on so messages are printed during local testing.
logger = logging.getLogger("TravelMate")
logger.addHandler(logging.NullHandler())

# ==========================================
# 1. ENVIRONMENT CONFIGURATION & CREDENTIALS
# ==========================================
# Files are stored next to this script so the paths work no matter where it is called from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if load_dotenv:
    load_dotenv(os.path.join(BASE_DIR, ".env"))

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
CACHE_MAX_AGE_HOURS = 168           # Entries older than this are deleted (also the stale-fallback limit)
DESTINATION_ID_TTL_HOURS = 720      # Verified city -> provider ID lookups change rarely
FX_CACHE_TTL_HOURS = 12
FX_MAX_RATE_AGE_HOURS = 48          # Conversion policy: rates older than this are not used

MANDATORY_CATEGORY = os.getenv("TRAVELMATE_MANDATORY_CATEGORY", "hotels").strip().lower()
FLIGHTS_ENABLED = _env_flag("TRAVELMATE_FLIGHTS_ENABLED", True)
# Issue #18 forbids rotating keys to bypass limits, so quota rotation is OFF unless explicitly enabled
KEY_ROTATION_ON_QUOTA = _env_flag("TRAVELMATE_KEY_ROTATION_ON_QUOTA", False)
ALLOW_STALE_CACHE_FALLBACK = _env_flag("TRAVELMATE_ALLOW_STALE_CACHE_FALLBACK", False)

DEFAULT_DEADLINE_SECONDS = _env_number("TRAVELMATE_DEFAULT_DEADLINE_SECONDS", 90)
PER_ATTEMPT_TIMEOUT_SECONDS = 20
MAX_TRANSIENT_RETRIES = 1           # Extra attempts per key for timeouts / connection errors / HTTP 5xx
RETRY_BACKOFF_SECONDS = 1.0
MAX_RETRY_AFTER_SECONDS = 10        # Provider Retry-After guidance is honored only up to this value
AI_TIMEOUT_SECONDS = 60
AI_MIN_SECONDS_REQUIRED = 5         # The AI call is skipped (timeout) if less time than this is left
AI_MAX_COMPLETION_TOKENS = 8192

MAX_ADULTS = 30   # Booking.com search limit
MAX_ROOMS = 30    # Booking.com search limit
MAX_NIGHTS = 30   # Keeps the AI itinerary bounded
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

def load_key_pool(key_env_prefix):
    """
    Reads the keys of one service from the environment. Supported forms (merged, duplicates removed):
      <PREFIX>_RAPIDAPI_KEYS = "key1,key2"      and/or      <PREFIX>_RAPIDAPI_KEY_1 ... <PREFIX>_RAPIDAPI_KEY_10
    One key = single-key mode. Placeholder values from .env.example are ignored.
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
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),                       # Groq keys
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
# 3. STANDARDIZED ERROR ENVELOPE
# ==========================================
# code: (retryable, user-safe default message)
ERROR_CODES = {
    "invalid_input": (False, "The request is invalid. Please check the highlighted fields."),
    "no_results": (False, "No offers matching the requested dates, destination and travelers were found."),
    "unsupported_search": (False, "This search is outside the supported provider coverage."),
    "rate_limited": (True, "The provider rate limit was reached. Please try again later."),
    "timeout": (True, "The search did not finish before the deadline."),
    "auth_error": (False, "The provider rejected the configured credentials."),
    "invalid_response": (True, "The provider returned an unexpected response."),
    "provider_failure": (True, "The provider is currently failing. Please try again later."),
    "unavailable": (True, "This service is currently unavailable."),
    "invalid_output": (False, "The AI output failed validation and was not published."),
    "internal_error": (False, "An internal error occurred. Please try again later.")
}

class TravelMateError(Exception):
    """Typed adapter error. Its message and details are always user-safe (never raw exception text)."""
    def __init__(self, code, message=None, details=None, retryable=None, retry_after_seconds=None,
                 transient=False, quota_exhausted=False):
        if code not in ERROR_CODES:
            code = "internal_error"
        default_retryable, default_message = ERROR_CODES[code]
        super().__init__(message or default_message)
        self.code = code
        self.message = message or default_message
        self.details = details or {}
        self.retryable = default_retryable if retryable is None else retryable
        self.retry_after_seconds = retry_after_seconds
        self.transient = transient
        self.quota_exhausted = quota_exhausted

    def to_envelope(self, category=None):
        return build_error(self.code, self.message, self.details, category, self.retryable, self.retry_after_seconds)

def build_error(code, message=None, details=None, category=None, retryable=None, retry_after_seconds=None):
    default_retryable, default_message = ERROR_CODES.get(code, ERROR_CODES["internal_error"])
    return {
        "code": code if code in ERROR_CODES else "internal_error",
        "message": redact(message or default_message),
        "category": category,
        "retryable": default_retryable if retryable is None else retryable,
        "retry_after_seconds": retry_after_seconds,
        "details": sanitize(details or {})
    }

# ==========================================
# 4. DEADLINE & NUMBER HELPERS
# ==========================================
def utc_now():
    return datetime.now(timezone.utc)

def utc_now_iso():
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")

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

def _today():
    """Server-local current date (separate function so tests can freeze it)."""
    return date.today()

def new_request_id():
    return f"tm-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

# ==========================================
# 5. LOCAL CACHE (THREAD & PROCESS SAFE)
# ==========================================
_cache_thread_lock = threading.RLock()

class _CacheFileLock:
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
                    raise TimeoutError("Cache lock timeout")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            os.close(self.fd)
        try:
            os.remove(self.path)
        except OSError:
            pass

def atomic_write_json(path, data):
    """Writes JSON to a temp file in the same folder, then atomically replaces the target file."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=folder, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
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

def cache_get(cache_key, ttl_hours, allow_stale=False):
    """Returns (entry, freshness) where freshness is "fresh", "stale" or None (not found / unusable)."""
    try:
        with _cache_thread_lock, _CacheFileLock(CACHE_FILE + ".lock"):
            entry = _read_cache_unlocked().get(cache_key)
    except TimeoutError:
        logger.warning("[!] Cache is locked by another process. Skipping cache read...")
        return None, None
    if not isinstance(entry, dict) or "response" not in entry:
        return None, None
    age = _entry_age_hours(entry)
    if age is None:
        return None, None
    if age <= ttl_hours:
        return entry, "fresh"
    if allow_stale and age <= CACHE_MAX_AGE_HOURS:
        return entry, "stale"
    return None, None

def cache_put(cache_key, service_name, response):
    """Read-merge-write under a thread lock + process lock, with an atomic file replace (never a half-written file)."""
    try:
        with _cache_thread_lock, _CacheFileLock(CACHE_FILE + ".lock"):
            cache = _read_cache_unlocked()
            # Drop entries older than the maximum age so the cache file does not grow forever
            cache = {k: v for k, v in cache.items()
                     if isinstance(v, dict) and (_entry_age_hours(v) or CACHE_MAX_AGE_HOURS + 1) <= CACHE_MAX_AGE_HOURS}
            cache[cache_key] = {"service": service_name, "saved_at": utc_now_iso(), "response": response}
            atomic_write_json(CACHE_FILE, cache)
    except (TimeoutError, OSError) as e:
        logger.warning(f"[!] Could not write cache file ({type(e).__name__}). Continuing without caching...")

# ==========================================
# 6. PROVIDER REQUEST HANDLER (CLASSIFIED ERRORS & BOUNDED RETRIES)
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
    return "provider_failure"

def _is_quota_exhausted(message):
    text = str(message or "").lower()
    return "quota" in text and any(word in text for word in ["monthly", "daily", "plan", "exceeded"])

def _parse_retry_after(response):
    try:
        value = float(response.headers.get("Retry-After", ""))
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None

def _attempt_request(url, host, api_key, params, deadline):
    """One HTTP attempt. Returns (payload, meta) or raises a classified TravelMateError."""
    timeout = min(PER_ATTEMPT_TIMEOUT_SECONDS, seconds_left(deadline))
    if timeout <= 0.5:
        raise TravelMateError("timeout", details={"reason": "deadline_reached"})
    headers = {"x-rapidapi-host": host, "x-rapidapi-key": api_key, "accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.Timeout:
        raise TravelMateError("timeout", details={"reason": "provider_timeout"}, transient=True)
    except requests.RequestException:
        raise TravelMateError("provider_failure", details={"reason": "connection_error"}, transient=True)

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
            code = _classify_provider_message(message)
            raise TravelMateError(code, details={"reason": "provider_status_false",
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
        raise TravelMateError("provider_failure", details={"reason": f"http_{status}", **details}, transient=True)
    raise TravelMateError("invalid_response", details={"reason": f"unexpected_http_{status}", **details})

def provider_get(service_key, params, deadline, cache_ttl_hours=None, cache_mode="default", evidence=None):
    """
    Sends a GET request to a RapidAPI provider and returns (payload, provenance).
      1. Local cache first (cache_mode "default"). "refresh" skips the read but stores the result, "off" does neither.
      2. Explicit error classification: rate_limited / auth_error / timeout / provider_failure / invalid_response ...
      3. Bounded retries inside deadline_at: 1 retry for transient failures, Retry-After honored up to 10 s.
      4. Next key only after auth_error (misconfigured key) or, if explicitly enabled, an exhausted quota.
      5. Optional, explicitly labeled stale-cache fallback when every allowed attempt failed.
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
        "key_slot": None,
        "attempts": 0,
        "rate_limit": {}
    }

    if cache_mode == "default":
        entry, freshness = cache_get(cache_key, ttl)
        if freshness == "fresh":
            provenance.update(retrieved_at=entry["saved_at"], cache_status="hit")
            logger.info(f"[+] {info['label']} loaded from local cache (no API quota used).")
            _record_provider_call(evidence, service_key, provenance, entry["response"])
            return entry["response"], provenance

    keys = load_key_pool(info["key_env_prefix"])
    if not keys:
        raise TravelMateError("auth_error", f"No API key is configured for {info['label']}.",
                              {"reason": "missing_credentials", "env_variable": f"{info['key_env_prefix']}_RAPIDAPI_KEYS"})

    last_error = None
    for slot, api_key in enumerate(keys, start=1):
        transient_retries = 0
        retry_after_honored = False
        while True:
            provenance["attempts"] += 1
            try:
                payload, meta = _attempt_request(url, info["host"], api_key, params, deadline)
                provenance.update(meta, key_slot=slot, retrieved_at=utc_now_iso(),
                                  cache_status="refresh" if cache_mode == "refresh" else "miss")
                logger.info(f"[+] {info['label']} fetched successfully using key slot #{slot} (200 OK).")
                if cache_mode != "off":
                    cache_put(cache_key, service_key, payload)
                _record_provider_call(evidence, service_key, provenance, payload)
                return payload, provenance
            except TravelMateError as error:
                last_error = error
                provenance["http_status"] = error.details.get("http_status")
                provenance["rate_limit"] = error.details.get("rate_limit", {})
                wait = RETRY_BACKOFF_SECONDS * (transient_retries + 1)
                if error.transient and transient_retries < MAX_TRANSIENT_RETRIES and _has_time_for(deadline, wait + 1):
                    transient_retries += 1
                    logger.warning(f"[!] {info['label']} transient {error.code} on key slot #{slot}. Retrying in {wait:.0f}s...")
                    _sleep(wait)
                    continue
                if (error.code == "rate_limited" and not error.quota_exhausted and not retry_after_honored
                        and error.retry_after_seconds is not None
                        and error.retry_after_seconds <= MAX_RETRY_AFTER_SECONDS
                        and _has_time_for(deadline, error.retry_after_seconds + 1)):
                    retry_after_honored = True
                    logger.warning(f"[!] {info['label']} rate limited. Honoring Retry-After ({error.retry_after_seconds:.0f}s)...")
                    _sleep(error.retry_after_seconds)
                    continue
                break

        if slot < len(keys) and last_error.code == "auth_error":
            logger.warning(f"[!] {info['label']} key slot #{slot} was rejected (auth_error). Trying the next configured key...")
            continue
        if slot < len(keys) and last_error.code == "rate_limited" and last_error.quota_exhausted and KEY_ROTATION_ON_QUOTA:
            logger.warning(f"[!] {info['label']} key slot #{slot} quota exhausted. Key rotation is enabled; trying the next key...")
            continue
        break

    if ALLOW_STALE_CACHE_FALLBACK and cache_mode != "off" and last_error.code in ("rate_limited", "timeout", "provider_failure"):
        entry, freshness = cache_get(cache_key, ttl, allow_stale=True)
        if entry:
            provenance.update(retrieved_at=entry["saved_at"], cache_status="stale_fallback",
                              stale_fallback_reason=last_error.code)
            logger.warning(f"[!] {info['label']} failed ({last_error.code}). Serving a STALE cached response (labeled).")
            _record_provider_call(evidence, service_key, provenance, entry["response"])
            return entry["response"], provenance

    logger.error(f"[-] {info['label']} failed: {last_error.code} ({last_error.details.get('reason')}).")
    last_error.details.setdefault("service", info["label"])
    raise last_error

# ==========================================
# 7. CURRENCY CONVERSION POLICY (EVERYTHING TO USD)
# ==========================================
# Policy: USD amounts are used as-is. Other currencies are converted ONLY with live rates from
# open.er-api.com that are at most FX_MAX_RATE_AGE_HOURS old; every conversion records rate, source and time.
# If no valid rate exists, the quote is excluded and a warning is returned. There are no hardcoded fallback rates.
def fetch_usd_exchange_rates(deadline, cache_mode="default", evidence=None):
    cache_key = build_cache_key(EXCHANGE_RATE_URL, {})
    provenance = {
        "provider": "ExchangeRate-API open access (open.er-api.com)",
        "integration_type": "direct_public_api",
        "endpoint": "GET /v6/latest/USD",
        "query_parameters": {},
        "retrieved_at": None,
        "cache_status": "miss"
    }
    payload = None
    if cache_mode == "default":
        entry, freshness = cache_get(cache_key, FX_CACHE_TTL_HOURS)
        if freshness == "fresh":
            payload = entry["response"]
            provenance.update(retrieved_at=entry["saved_at"], cache_status="hit")

    if payload is None:
        timeout = min(10, seconds_left(deadline))
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
    return {
        "available": True,
        "rates": rates,
        "source": provenance["provider"],
        "rate_timestamp": payload.get("time_last_update_utc"),
        "retrieved_at": provenance["retrieved_at"],
        "provenance": provenance
    }

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
    """Returns (usd_amount, conversion_record). usd_amount is None when the conversion policy does not allow it."""
    currency = str(currency or "").strip().upper()
    if not currency:
        return None, {"status": "unknown_currency"}
    if currency == "USD":
        return round_money(amount), {"status": "not_required", "original_currency": "USD"}
    policy = fx()
    if not policy.get("available"):
        return None, {"status": "rates_unavailable", "original_currency": currency, "reason": policy.get("reason")}
    rate = policy["rates"].get(currency)
    if valid_amount(rate) is None:
        return None, {"status": "unsupported_currency", "original_currency": currency}
    return round_money(amount / rate), {
        "status": "converted",
        "original_amount": amount,
        "original_currency": currency,
        "rate_per_usd": rate,
        "rate_source": policy["source"],
        "rate_timestamp": policy["rate_timestamp"],
        "rate_retrieved_at": policy["retrieved_at"]
    }

# ==========================================
# 8. SUPPORTED CITIES, AIRPORTS & COVERAGE LIMITS
# ==========================================
# Canonical city records. "booking_dest_id" is either pinned (verified value) or resolved once through
# Booking.com searchDestination, verified (type = city, same country code and name) and cached.
# Cities that are not listed here return "unsupported_search".
SUPPORTED_CITIES = {
    "istanbul": {"name": "Istanbul", "country_code": "tr", "airports": ["IST", "SAW"], "timezone": "Europe/Istanbul",
                 "center": (41.0082, 28.9784), "booking_dest_id": None, "aliases": []},
    "cairo": {"name": "Cairo", "country_code": "eg", "airports": ["CAI"], "timezone": "Africa/Cairo",
              "center": (30.0444, 31.2357), "booking_dest_id": "-290692", "aliases": []},  # Verified 2026-10-17
    "riyadh": {"name": "Riyadh", "country_code": "sa", "airports": ["RUH"], "timezone": "Asia/Riyadh",
               "center": (24.7136, 46.6753), "booking_dest_id": None, "aliases": ["ar riyadh", "al riyadh"]},
    "jeddah": {"name": "Jeddah", "country_code": "sa", "airports": ["JED"], "timezone": "Asia/Riyadh",
               "center": (21.4858, 39.1925), "booking_dest_id": None, "aliases": ["jedda", "jiddah"]},
    "dubai": {"name": "Dubai", "country_code": "ae", "airports": ["DXB", "DWC"], "timezone": "Asia/Dubai",
              "center": (25.2048, 55.2708), "booking_dest_id": None, "aliases": []},
    "doha": {"name": "Doha", "country_code": "qa", "airports": ["DOH"], "timezone": "Asia/Qatar",
             "center": (25.2854, 51.5310), "booking_dest_id": None, "aliases": []},
    "amman": {"name": "Amman", "country_code": "jo", "airports": ["AMM"], "timezone": "Asia/Amman",
              "center": (31.9539, 35.9106), "booking_dest_id": None, "aliases": []},
    "baghdad": {"name": "Baghdad", "country_code": "iq", "airports": ["BGW"], "timezone": "Asia/Baghdad",
                "center": (33.3152, 44.3661), "booking_dest_id": None, "aliases": []},
    "erbil": {"name": "Erbil", "country_code": "iq", "airports": ["EBL"], "timezone": "Asia/Baghdad",
              "center": (36.1911, 44.0092), "booking_dest_id": None, "aliases": ["arbil", "hawler"]},
    "london": {"name": "London", "country_code": "gb", "airports": ["LHR", "LGW", "STN", "LTN", "LCY"],
               "timezone": "Europe/London", "center": (51.5074, -0.1278), "booking_dest_id": None, "aliases": []},
    "paris": {"name": "Paris", "country_code": "fr", "airports": ["CDG", "ORY"], "timezone": "Europe/Paris",
              "center": (48.8566, 2.3522), "booking_dest_id": None, "aliases": []}
}

# IANA time zones for flight dates (the flight provider returns local dates only, no departure times)
AIRPORT_TIMEZONES = {airport: city["timezone"] for city in SUPPORTED_CITIES.values() for airport in city["airports"]}
AIRPORT_TIMEZONES.update({
    "DMM": "Asia/Riyadh", "MED": "Asia/Riyadh", "BSR": "Asia/Baghdad", "NJF": "Asia/Baghdad", "ISU": "Asia/Baghdad",
    "KWI": "Asia/Kuwait", "BAH": "Asia/Bahrain", "MCT": "Asia/Muscat", "AUH": "Asia/Dubai", "SHJ": "Asia/Dubai",
    "BEY": "Asia/Beirut", "HRG": "Africa/Cairo", "SSH": "Africa/Cairo", "CMN": "Africa/Casablanca",
    "AYT": "Europe/Istanbul", "ADB": "Europe/Istanbul", "ESB": "Europe/Istanbul", "FRA": "Europe/Berlin",
    "MUC": "Europe/Berlin", "AMS": "Europe/Amsterdam", "FCO": "Europe/Rome", "MAD": "Europe/Madrid",
    "JFK": "America/New_York", "KUL": "Asia/Kuala_Lumpur"
})

def _normalize_city_text(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())

def resolve_supported_city(city_name):
    normalized = _normalize_city_text(city_name)
    for city_id, city in SUPPORTED_CITIES.items():
        if normalized == city_id or normalized == city["name"].lower() or normalized in city["aliases"]:
            return city_id, city
    return None, None

def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))

# ==========================================
# 9. INPUT VALIDATION (SHARED BY CLI & BACKEND)
# ==========================================
# Public request fields. "destination_airport" and "rooms" are OPTIONAL adapter-internal inputs:
# they are not part of the public contract until approved under PLAN-02 (#11).
PUBLIC_REQUEST_FIELDS = ["trip_type", "origin", "destination_city", "check_in_date", "check_out_date", "adults", "budget_usd"]
ADAPTER_OPTIONAL_FIELDS = ["destination_airport", "rooms"]

# Every validator returns (clean_value, error_message). error_message is None when the value is valid.
def validate_trip_type(value):
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in ["1", "one_way", "oneway"]:
        return "one_way", None
    if normalized in ["2", "round_trip", "roundtrip", "two_way"]:
        return "round_trip", None
    return None, "trip_type must be 'one_way' or 'round_trip'."

def validate_airport_code(value, field_label):
    code = str(value or "").strip() if isinstance(value, str) else ""
    if not re.fullmatch(r"[A-Za-z]{3}", code):
        return None, f"{field_label} must be exactly 3 letters (IATA code, e.g., IST)."
    return code.upper(), None

def validate_city_name(value, field_label="destination_city"):
    city = re.sub(r"\s+", " ", value.strip()) if isinstance(value, str) else ""
    if not (2 <= len(city) <= 80) or not re.fullmatch(r"[^\W\d_]+(?:[ \-'.][^\W\d_]+)*\.?", city):
        return None, f"{field_label} must be a city name made of letters (e.g., Cairo)."
    return city, None

def validate_date(value, field_label, min_date=None):
    text = value.strip() if isinstance(value, str) else ""
    parsed = parse_iso_date(text) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None
    if parsed is None:
        return None, f"{field_label} must be a valid date in YYYY-MM-DD format (e.g., 2026-11-01)."
    if min_date and parsed < min_date:
        return None, f"{field_label} must be on or after {min_date.isoformat()}."
    return parsed, None

def validate_positive_int(value, field_label, max_value=None):
    if isinstance(value, bool):
        return None, f"{field_label} must be a positive whole number."
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*\d+\s*", value):
        value = int(value)
    if not isinstance(value, int):
        return None, f"{field_label} must be a positive whole number."
    if value <= 0:
        return None, f"{field_label} must be greater than 0."
    if max_value and value > max_value:
        return None, f"{field_label} cannot be more than {max_value}."
    return value, None

def validate_budget(value, field_label="budget_usd"):
    """The budget must stay strictly positive after rounding to cents."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None, f"{field_label} must be a positive number."
    try:
        amount = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        return None, f"{field_label} must be a positive number."
    if not amount.is_finite():
        return None, f"{field_label} must be a finite number."
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        return None, f"{field_label} must be greater than 0.00 after rounding to cents."
    return float(amount), None

def validate_request(request_data):
    """
    Validates the request BEFORE any external call. Returns a clean trip dict or raises:
      invalid_input       -> one entry per invalid field in details["fields"]
      unsupported_search  -> valid input, but the destination is outside the supported coverage
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

    today = _today()
    trip_type = check("trip_type", validate_trip_type(request_data.get("trip_type")))
    origin = check("origin", validate_airport_code(request_data.get("origin"), "origin"))
    destination_city = check("destination_city", validate_city_name(request_data.get("destination_city")))
    check_in = check("check_in_date", validate_date(request_data.get("check_in_date"), "check_in_date", min_date=today))
    check_out = check("check_out_date", validate_date(request_data.get("check_out_date"), "check_out_date"))
    adults = check("adults", validate_positive_int(request_data.get("adults"), "adults", MAX_ADULTS))
    budget_usd = check("budget_usd", validate_budget(request_data.get("budget_usd")))

    destination_airport = None
    if request_data.get("destination_airport") not in (None, ""):
        destination_airport = check("destination_airport",
                                    validate_airport_code(request_data.get("destination_airport"), "destination_airport"))
    rooms = 1
    if request_data.get("rooms") not in (None, ""):
        rooms = check("rooms", validate_positive_int(request_data.get("rooms"), "rooms", MAX_ROOMS))

    # Cross-field checks
    if check_in and check_out:
        if check_out <= check_in:
            field_errors.append({"field": "check_out_date", "message": "check_out_date must be after check_in_date."})
        elif (check_out - check_in).days > MAX_NIGHTS:
            field_errors.append({"field": "check_out_date", "message": f"The stay cannot be longer than {MAX_NIGHTS} nights."})
    if adults and rooms and rooms > adults:
        field_errors.append({"field": "rooms", "message": "rooms cannot be more than adults."})

    if field_errors:
        raise TravelMateError("invalid_input", details={"fields": field_errors})

    city_id, city = resolve_supported_city(destination_city)
    if city is None:
        raise TravelMateError("unsupported_search", f"'{destination_city}' is not a supported destination yet.",
                              {"reason": "city_not_in_coverage",
                               "supported_cities": sorted(c["name"] for c in SUPPORTED_CITIES.values())})
    if destination_airport is None:
        destination_airport = city["airports"][0]
    elif destination_airport not in city["airports"]:
        raise TravelMateError("invalid_input", details={"fields": [{
            "field": "destination_airport",
            "message": f"destination_airport must be one of {', '.join(city['airports'])} for {city['name']}."}]})
    if origin == destination_airport or origin in city["airports"]:
        raise TravelMateError("invalid_input", details={"fields": [{
            "field": "origin", "message": "origin must be different from the destination city airports."}]})

    return {
        "trip_type": trip_type,
        "trip_type_label": "Round-Trip (2-Way)" if trip_type == "round_trip" else "One-Way",
        "origin": origin,
        "destination_city": city["name"],
        "check_in_date": check_in.isoformat(),
        "check_out_date": check_out.isoformat(),
        "nights": (check_out - check_in).days,
        "adults": adults,
        "budget_usd": budget_usd,
        "currency": "USD",
        # Adapter-internal values (kept separate from the public fields above)
        "adapter": {
            "city_id": city_id,
            "destination_airport": destination_airport,
            "rooms": rooms,
            "rooms_source": "request" if request_data.get("rooms") not in (None, "") else "default_1"
        }
    }

def public_search_parameters(trip):
    """Returns only the public fields (safe to store and display)."""
    return {k: v for k, v in trip.items() if k != "adapter"}

# ==========================================
# 10. FLIGHT PROVIDER (SKYSCANNER ROUTE QUOTES - INDICATIVE ONLY)
# ==========================================
# Documented provider behavior (verified with live responses on 2026-10-17):
#   - The /route endpoint returns Skyscanner's CACHED quotes for a city pair ("not a live search" per its usage_note).
#   - "date", "adults" and "currency" query parameters are NOT honored: dates spread over ~12 months, GBP prices.
#   - Deep links contain no adult count, so each quote is treated as a SINGLE-ADULT one-way fare.
# Therefore: only exact-date quotes are eligible, group totals are "single adult quote x adults" (unverified)
# and every flight price is labeled "indicative". Flight prices are never authoritative trip costs.
FLIGHT_PROVIDER_CAPABILITIES = {
    "supports_requested_date": False,
    "supports_adult_count": False,
    "supports_currency_parameter": False,
    "data_type": "cached_route_quotes",
    "price_basis": "single_adult_one_way_quote",
    "group_total_method": "price_per_adult_usd x adults (unverified for adults > 1)",
    "departure_times_available": False,
    "price_authority": "indicative"
}

def fetch_flight_quotes(origin, destination, travel_date, adults, deadline, label, cache_mode="default", evidence=None):
    # The requested scope is sent to the provider, then validated against what it actually returns
    params = {
        "origin": origin.lower(),
        "destination": destination.lower(),
        "date": travel_date,
        "adults": str(adults),
        "currency": "USD",
        "market": "US",
        "locale": "en-US"  # Request English airline and city names
    }
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

def normalize_flight_quotes(payload, direction, origin, destination, requested_date, adults, fx, provenance,
                            max_results=5):
    """
    Returns (eligible_offers, alternative_date_offers, coverage).
    Eligible = exact route AND exact requested date. Different dates go to the alternatives list only.
    """
    section = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(section, dict) or not isinstance(section.get("deals"), list):
        raise TravelMateError("invalid_response", details={"reason": "missing_deals_list", "direction": direction})

    deals = section["deals"]
    currency = section.get("currency")
    target_date = parse_iso_date(requested_date)
    excluded = {"route_mismatch": 0, "invalid_price": 0, "unconvertible_currency": 0, "malformed": 0}
    returned_dates = set()
    eligible, alternatives = [], []

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
        if flight_date is None:
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
        date_match = flight_date == target_date
        deep_link = d.get("deep_link_path")

        offer = {
            "offer_id": d.get("id"),
            "direction": direction,
            "airline": " + ".join(airline_names) or "Unknown Airline",
            "carrier_codes": carrier_codes,
            "origin_airport": leg_origin,
            "destination_airport": leg_destination,
            "origin_timezone": AIRPORT_TIMEZONES.get(leg_origin, "unknown"),
            "destination_timezone": AIRPORT_TIMEZONES.get(leg_destination, "unknown"),
            "flight_date": flight_date.isoformat(),
            "flight_date_basis": "local departure date at origin_timezone",
            "departure_time_local": None,
            "arrival_time_local": None,
            "requested_date": requested_date,
            "days_from_requested_date": abs((flight_date - target_date).days),
            "is_direct": is_direct,
            "stops": stops,
            "transit_airports": transit_airports,
            "stops_label": _build_stops_label(is_direct, stops, transit_airports),
            "price_per_adult_usd": price_usd,
            "adults": adults,
            "group_total_usd": round_money(price_usd * adults),
            "price_basis": FLIGHT_PROVIDER_CAPABILITIES["price_basis"],
            "group_price_verified": False,
            "price_authority": "indicative",
            "original_price": price,
            "original_currency": currency,
            "booking_link": f"https://www.skyscanner.net{deep_link}" if deep_link else None,
            "eligibility": {
                "eligible": date_match,
                "reason": None if date_match else "date_mismatch",
                "checks": {"route_match": True, "date_match": date_match, "adult_occupancy_verified": False}
            },
            "provenance": {
                "provider": provenance["provider"],
                "integration_type": provenance["integration_type"],
                "endpoint": provenance["endpoint"],
                "retrieved_at": provenance["retrieved_at"],
                "cache_status": provenance["cache_status"],
                "provider_offer_id": d.get("id"),
                "quoted_at": first_leg.get("quoted_at"),
                "currency_conversion": conversion
            }
        }
        (eligible if date_match else alternatives).append(offer)

    eligible.sort(key=lambda f: f["group_total_usd"])
    alternatives.sort(key=lambda f: (f["days_from_requested_date"], f["group_total_usd"]))
    coverage = {
        "deals_returned": len(deals),
        "eligible_exact_date": len(eligible),
        "alternative_dates": len(alternatives),
        "excluded": excluded,
        "requested_date": requested_date,
        "returned_date_range": [min(returned_dates), max(returned_dates)] if returned_dates else None,
        "date_parameter_honored": bool(returned_dates) and returned_dates == {requested_date},
        "requested_currency": "USD",
        "returned_currency": currency,
        "currency_parameter_honored": str(currency).upper() == "USD",
        "provider_usage_note": str(section.get("usage_note") or "")[:400] or None
    }
    return eligible[:max_results], alternatives[:max_results], coverage

# ==========================================
# 11. HOTEL PROVIDER (BOOKING.COM - LIVE, VERIFIED PER OFFER)
# ==========================================
OCCUPANCY_PATTERN = re.compile(r"Price for (\d+) nights?, (\d+) adults?", re.IGNORECASE)
# Unit configuration line, e.g. " 1 private suite • 1 hotel room : 2 beds." or " Hotel room : 4 beds."
UNIT_LINE_PATTERN = re.compile(r"^\s*([^\n:]+?)\s*:\s*\d+\s*beds?\b", re.IGNORECASE | re.MULTILINE)
UNIT_COUNT_PATTERN = re.compile(
    r"(\d+)\s+(?:[^\W\d_]+\s+)?(?:rooms?|suites?|apartments?|studios?|villas?|units?|bungalows?|chalets?)\b",
    re.IGNORECASE)

def _parse_booked_units(label):
    """Returns (unit_count, evidence_text) from the unit configuration line, or (None, None) if it is not stated."""
    line = UNIT_LINE_PATTERN.search(label or "")
    if not line:
        return None, None
    segment = line.group(1).strip()
    counts = [int(n) for n in UNIT_COUNT_PATTERN.findall(segment)]
    return (sum(counts) if counts else 1), segment  # No number means a single unit ("Hotel room", "Entire studio")
DISTANCE_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(km|m)\b\s*from", re.IGNORECASE)

def _parse_distance_km(text):
    match = DISTANCE_PATTERN.search(text or "")
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return round(value / 1000, 2) if match.group(2).lower() == "m" else round(value, 2)

def resolve_booking_destination(city, deadline, cache_mode="default", evidence=None):
    """Canonical city -> Booking.com destination ID (pinned, or looked up once and verified)."""
    if city.get("booking_dest_id"):
        return {"dest_id": city["booking_dest_id"], "search_type": "CITY", "source": "pinned_mapping"}

    params = {"query": city["name"], "languagecode": "en-us"}  # Request English destination names
    logger.info(f"[*] Resolving Booking.com destination ID for: {city['name']}...")
    payload, _ = provider_get("booking_destination", params, deadline, cache_ttl_hours=DESTINATION_ID_TTL_HOURS,
                              cache_mode=cache_mode, evidence=evidence)
    results = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise TravelMateError("invalid_response", details={"reason": "destination_list_missing"})
    for item in results:
        if (isinstance(item, dict) and str(item.get("dest_type", "")).lower() == "city"
                and str(item.get("cc1", "")).lower() == city["country_code"]
                and _normalize_city_text(item.get("name") or item.get("city_name")) == city["name"].lower()
                and item.get("dest_id")):
            logger.info(f"[+] Verified destination ID: {item['dest_id']} ({item.get('label')})")
            return {"dest_id": str(item["dest_id"]), "search_type": "CITY", "source": "verified_lookup",
                    "label": item.get("label")}
    raise TravelMateError("unsupported_search", f"Booking.com did not return a verified city match for {city['name']}.",
                          {"reason": "destination_not_verified"})

def fetch_hotel_offers(dest_id, search_type, trip, deadline, cache_mode="default", evidence=None):
    adapter = trip["adapter"]
    params = {
        "dest_id": dest_id,
        "search_type": search_type,
        "arrival_date": trip["check_in_date"],
        "departure_date": trip["check_out_date"],
        "adults": str(trip["adults"]),
        "room_qty": str(adapter["rooms"]),
        "page_number": "1",
        "units": "metric",
        "temperature_unit": "c",
        "languagecode": "en-us",  # Request English hotel names and labels
        "currency_code": "USD"
    }
    logger.info(f"[*] Fetching hotels {trip['check_in_date']} -> {trip['check_out_date']} "
                f"({trip['adults']} adult(s), {adapter['rooms']} room(s))...")
    return provider_get("booking_hotels", params, deadline, cache_mode=cache_mode, evidence=evidence)

def normalize_hotel_offers(payload, trip, city, fx, provenance):
    """
    Returns (eligible_offers, coverage). A hotel is eligible only if its dates, adult count (and room count when
    stated) and location match the request. Final price = grossPrice + excludedPrice; unknown taxes stay "unknown".
    """
    section = payload.get("data") if isinstance(payload, dict) else None
    hotel_list = section.get("hotels") if isinstance(section, dict) else None
    if not isinstance(hotel_list, list):
        raise TravelMateError("invalid_response", details={"reason": "missing_hotels_list"})

    adapter = trip["adapter"]
    excluded = {"date_mismatch": 0, "occupancy_mismatch": 0, "occupancy_unverified": 0, "destination_mismatch": 0,
                "destination_unverified": 0, "invalid_price": 0, "unconvertible_currency": 0, "malformed": 0}
    offers = []

    for h in hotel_list:
        prop = h.get("property") if isinstance(h, dict) else None
        if not isinstance(prop, dict):
            excluded["malformed"] += 1
            continue
        label = str(h.get("accessibilityLabel") or "")

        # 1. Dates must match exactly
        if prop.get("checkinDate") != trip["check_in_date"] or prop.get("checkoutDate") != trip["check_out_date"]:
            excluded["date_mismatch"] += 1
            continue

        # 2. Adult occupancy must be stated and match; room count must match when the provider states it
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
        if booked_units is not None and booked_units != adapter["rooms"]:
            excluded["occupancy_mismatch"] += 1
            continue
        rooms_verified = True if booked_units is not None else None  # None = provider did not state the unit count

        # 3. Location must be inside the canonical city coverage radius (or the city name must match)
        latitude, longitude = prop.get("latitude"), prop.get("longitude")
        if prop.get("countryCode") and str(prop["countryCode"]).lower() != city["country_code"]:
            excluded["destination_mismatch"] += 1
            continue
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            distance_to_city = haversine_km(latitude, longitude, *city["center"])
            if distance_to_city > HOTEL_COVERAGE_RADIUS_KM:
                excluded["destination_mismatch"] += 1
                continue
        elif _normalize_city_text(prop.get("wishlistName")) != city["name"].lower():
            excluded["destination_unverified"] += 1
            continue

        # 4. Prices: reject negative / NaN / Infinity, convert under the policy, never count fees twice
        breakdown = prop.get("priceBreakdown") or {}
        gross = breakdown.get("grossPrice") or {}
        base_price = valid_amount(gross.get("value"))
        if base_price is None:
            excluded["invalid_price"] += 1
            continue
        base_price_usd, base_conversion = convert_to_usd(base_price, gross.get("currency"), fx)
        if base_price_usd is None:
            excluded["unconvertible_currency"] += 1
            continue

        excluded_charges = breakdown.get("excludedPrice")
        taxes_usd, taxes_status, taxes_conversion = None, "unknown", None
        if isinstance(excluded_charges, dict) and "value" in excluded_charges:
            taxes_value = valid_amount(excluded_charges.get("value"), allow_zero=True)
            if taxes_value is None:
                excluded["invalid_price"] += 1
                continue
            taxes_usd, taxes_conversion = convert_to_usd(
                taxes_value, excluded_charges.get("currency") or gross.get("currency"), fx)
            taxes_status = "known" if taxes_usd is not None else "unknown"

        total_price_usd = round_money(base_price_usd + taxes_usd) if taxes_status == "known" else None
        if prop.get("accuratePropertyClass") or prop.get("propertyClass"):
            star_rating, star_source = prop.get("accuratePropertyClass") or prop.get("propertyClass"), "official_star_rating"
        elif prop.get("qualityClass"):
            star_rating, star_source = prop["qualityClass"], "booking_quality_rating"
        else:
            star_rating, star_source = None, None
        hotel_id = h.get("hotel_id") or prop.get("id")
        photo_urls = prop.get("photoUrls") or []

        offers.append({
            "offer_id": f"booking:{hotel_id}:{trip['check_in_date']}:{trip['check_out_date']}:{trip['adults']}a{adapter['rooms']}r",
            "hotel_id": hotel_id,
            "name": prop.get("name") or "Unknown Hotel",
            "star_rating": star_rating,
            "star_rating_source": star_source,
            "review_score": prop.get("reviewScore") or None,
            "review_word": prop.get("reviewScoreWord") or "",
            "review_count": prop.get("reviewCount") or 0,
            "distance_from_center_km": _parse_distance_km(label),
            "check_in_date": prop.get("checkinDate"),
            "check_out_date": prop.get("checkoutDate"),
            "nights": trip["nights"],
            "adults": trip["adults"],
            "rooms": adapter["rooms"],
            "base_price_usd": base_price_usd,
            "taxes_and_fees_usd": taxes_usd,
            "taxes_status": taxes_status,
            "total_price_usd": total_price_usd,
            "price_per_night_usd": round_money(total_price_usd / trip["nights"]) if total_price_usd is not None else None,
            "price_scope": "whole stay, all adults, all rooms",
            "price_authority": "live_provider_quote",
            "photo_url": photo_urls[0] if photo_urls else None,
            "latitude": latitude,
            "longitude": longitude,
            "eligibility": {
                "eligible": True,
                "reason": None,
                "checks": {"dates_match": True, "adults_verified": True, "rooms_verified": rooms_verified,
                           "destination_verified": True}
            },
            "provenance": {
                "provider": provenance["provider"],
                "integration_type": provenance["integration_type"],
                "endpoint": provenance["endpoint"],
                "retrieved_at": provenance["retrieved_at"],
                "cache_status": provenance["cache_status"],
                "provider_offer_id": hotel_id,
                "block_ids": prop.get("blockIds") or [],
                "occupancy_evidence": occupancy.group(0),
                "rooms_evidence": units_evidence,
                "currency_conversion": {"base": base_conversion, "taxes": taxes_conversion}
            }
        })

    coverage = {"hotels_returned": len(hotel_list), "eligible": len(offers), "excluded": excluded,
                "page_number": 1, "coverage_radius_km": HOTEL_COVERAGE_RADIUS_KM}
    return offers, coverage

# ==========================================
# 12. LIVE TRAVEL ADAPTER BOUNDARY (search_travel)
# ==========================================
def _category_result(category, status, reason=None, error=None, **extra):
    return {"category": category, "status": status, "reason": reason, "error": error, **extra}

def _search_flights(trip, deadline, fx, cache_mode, evidence, warnings):
    if not FLIGHTS_ENABLED:
        return _category_result("flights", "unavailable", "Optional category not enabled in this deployment.",
                                build_error("unavailable", "Flight search is not enabled.", category="flights"),
                                outbound_flights=[], return_flights=[],
                                alternative_date_flights={"outbound": [], "return": []})

    adapter = trip["adapter"]
    directions = [("outbound", trip["origin"], adapter["destination_airport"], trip["check_in_date"])]
    if trip["trip_type"] == "round_trip":
        directions.append(("return", adapter["destination_airport"], trip["origin"], trip["check_out_date"]))

    result = _category_result("flights", "available", price_authority="indicative",
                              capabilities=FLIGHT_PROVIDER_CAPABILITIES, outbound_flights=[], return_flights=[],
                              alternative_date_flights={"outbound": [], "return": []}, coverage={}, provenance={},
                              limitations=[
                                  "Cached quotes: the provider does not perform a live search for the requested date.",
                                  "Group totals multiply a single-adult quote by the adult count (unverified for adults > 1).",
                                  "No departure/arrival times are provided; only local departure dates.",
                                  "Adopting an alternative date requires a NEW request with fresh hotel search and calculations."
                              ])
    try:
        for direction, origin, destination, travel_date in directions:
            payload, provenance = fetch_flight_quotes(origin, destination, travel_date, trip["adults"], deadline,
                                                      f"{direction.title()} Flight", cache_mode, evidence)
            eligible, alternatives, coverage = normalize_flight_quotes(
                payload, direction, origin, destination, travel_date, trip["adults"], fx, provenance)
            result[f"{direction}_flights"] = eligible
            result["alternative_date_flights"][direction] = alternatives
            result["coverage"][direction] = coverage
            result["provenance"][direction] = provenance
            if coverage["excluded"]["unconvertible_currency"]:
                warnings.append(f"{coverage['excluded']['unconvertible_currency']} {direction} flight quote(s) were "
                                f"excluded because {coverage['returned_currency']} could not be converted to USD.")
    except TravelMateError as error:
        result.update(status="error", reason=error.details.get("reason"), error=error.to_envelope("flights"))
        return result

    missing = [d for d, *_ in directions if not result[f"{d}_flights"]]
    if missing:
        result.update(status="no_results", reason="no_exact_date_quote",
                      error=build_error("no_results", f"No {' / '.join(missing)} flight quote exists for the exact "
                                        "requested date. Alternative dates are listed separately and are not eligible.",
                                        {"directions": missing}, "flights"))
    return result

def _search_hotels(trip, deadline, fx, cache_mode, evidence, warnings):
    city = SUPPORTED_CITIES[trip["adapter"]["city_id"]]
    result = _category_result("hotels", "available", price_authority="live_provider_quote", offers=[],
                              coverage={}, provenance={}, destination_mapping=None)
    try:
        destination = resolve_booking_destination(city, deadline, cache_mode, evidence)
        result["destination_mapping"] = destination
        payload, provenance = fetch_hotel_offers(destination["dest_id"], destination["search_type"], trip, deadline,
                                                 cache_mode, evidence)
        offers, coverage = normalize_hotel_offers(payload, trip, city, fx, provenance)
        result.update(offers=offers, coverage=coverage, provenance=provenance)
    except TravelMateError as error:
        result.update(status="error", reason=error.details.get("reason"), error=error.to_envelope("hotels"))
        return result

    unknown_taxes = sum(1 for o in offers if o["taxes_status"] == "unknown")
    if unknown_taxes:
        warnings.append(f"{unknown_taxes} hotel(s) have unknown taxes/fees; their total price is reported as unknown.")
    if coverage["excluded"]["unconvertible_currency"]:
        warnings.append(f"{coverage['excluded']['unconvertible_currency']} hotel offer(s) were excluded because "
                        "their currency could not be converted to USD.")
    if not offers:
        result.update(status="no_results", reason="no_verified_offers",
                      error=build_error("no_results", details={"excluded": coverage["excluded"]}, category="hotels"))
    return result

def _data_mode(flights_provenance, hotels_provenance):
    """Summarizes where the data came from: live, includes_cached or stale_cache_fallback."""
    statuses = [p.get("cache_status") for p in (flights_provenance or {}).values() if isinstance(p, dict)]
    if isinstance(hotels_provenance, dict) and hotels_provenance.get("cache_status"):
        statuses.append(hotels_provenance["cache_status"])
    if "stale_fallback" in statuses:
        return "stale_cache_fallback"
    if "hit" in statuses:
        return "includes_cached"
    return "live"

def _search_travel_validated(trip, deadline, request_id, cache_mode="default", evidence=None):
    warnings = []
    fx = LazyExchangeRates(deadline, cache_mode, evidence)
    flights = _search_flights(trip, deadline, fx, cache_mode, evidence, warnings)
    hotels = _search_hotels(trip, deadline, fx, cache_mode, evidence, warnings)
    fx_policy = fx.policy
    if fx_policy and not fx_policy.get("available"):
        warnings.append(f"Exchange rates unavailable ({fx_policy.get('reason')}); non-USD quotes were excluded.")

    mandatory = hotels if MANDATORY_CATEGORY == "hotels" else flights
    return {
        "request_id": request_id,
        "status": "success" if mandatory["status"] == "available" else "error",
        "error": None if mandatory["status"] == "available" else mandatory["error"],
        "mandatory_category": MANDATORY_CATEGORY,
        "search_parameters": public_search_parameters(trip),
        "flights": flights,
        "hotels": hotels,
        "exchange_rates": None if fx_policy is None else {k: v for k, v in fx_policy.items() if k != "rates"},
        "data_mode": _data_mode(flights.get("provenance"), hotels.get("provenance")),
        "warnings": warnings
    }

def search_travel(trip_request, deadline_at=None, request_id=None, cache_mode="default", evidence=None):
    """
    Live travel adapter boundary. Returns BOTH category objects ("flights" and "hotels"), each with
    status available | no_results | unavailable | error, normalized offers, coverage and sanitized provenance.
    Never raises: invalid input and unexpected errors are returned in the error envelope.
    """
    request_id = request_id or new_request_id()
    try:
        trip = validate_request(trip_request)
        deadline = resolve_deadline(deadline_at)
        return _search_travel_validated(trip, deadline, request_id, cache_mode, evidence)
    except TravelMateError as error:
        return {"request_id": request_id, "status": "error", "error": error.to_envelope("request"),
                "flights": None, "hotels": None, "warnings": []}
    except Exception:
        logger.exception(f"[-] Unexpected search_travel error (request_id={request_id}).")
        return {"request_id": request_id, "status": "error", "error": build_error("internal_error", category="request"),
                "flights": None, "hotels": None, "warnings": []}

# ==========================================
# 13. HOTEL TIERS & FLIGHT-PLUS-HOTEL SUBTOTALS (PROTOTYPE)
# ==========================================
# Adel owns the authoritative trip budget under BE-04 (#19). These values are ONLY a flight-plus-hotel
# subtotal and the balance remaining after those two categories - not the complete trip cost.
HOTEL_TIERS = [
    {"code": "D", "name": "Class D - Economy (Best Value)"},
    {"code": "C", "name": "Class C - Comfort"},
    {"code": "B", "name": "Class B - Premium"},
    {"code": "A", "name": "Class A - Luxury"}
]
SUBTOTAL_SCOPE_NOTE = ("Flight-plus-hotel subtotal only. Excludes food, activities, local transport and every other "
                       "expense. The authoritative trip budget is calculated by the backend (BE-04 #19).")

def assign_hotel_tiers(hotels):
    """
    Tiers are based on PRICE ORDERING only: hotels are sorted by total price (base price when taxes are unknown)
    and split into 4 equal bands: Class D (cheapest) -> C -> B -> A (most expensive).
    """
    hotels.sort(key=lambda h: h["total_price_usd"] if h["total_price_usd"] is not None else h["base_price_usd"])
    count = len(hotels)
    for index, hotel in enumerate(hotels):
        band = min(index * len(HOTEL_TIERS) // count, len(HOTEL_TIERS) - 1)
        hotel.update(tier_code=HOTEL_TIERS[band]["code"], tier_name=HOTEL_TIERS[band]["name"], tier_basis="price_ordering")
    return hotels

def pick_tier_representative(tier_code, candidates):
    """Chooses the best hotel inside a tier according to what that tier is meant to offer."""
    if tier_code == "D":
        # Best value = highest guest rating per dollar
        return max(candidates, key=lambda h: (h["review_score"] or 0) / max(h["total_price_usd"], 1))
    if tier_code == "A":
        # Luxury = highest star rating, then highest guest rating
        return max(candidates, key=lambda h: (h["star_rating"] or 0, h["review_score"] or 0))
    # Comfort / Premium = highest guest rating, then most reviews
    return max(candidates, key=lambda h: (h["review_score"] or 0, h["review_count"] or 0))

def build_flight_hotel_subtotals(hotels, outbound_flight, return_flight, trip):
    """
    Returns (budget_summary, tiers_within_limit, tiers_excluded).
    When no eligible exact-date flight exists, the flight part is null and only the hotel is checked against the budget.
    """
    budget = trip["budget_usd"]
    flights_known = outbound_flight is not None and (trip["trip_type"] == "one_way" or return_flight is not None)
    flight_subtotal = None
    if flights_known:
        flight_subtotal = round_money(outbound_flight["group_total_usd"] +
                                      (return_flight["group_total_usd"] if trip["trip_type"] == "round_trip" else 0))
    hotel_allowance = round_money(budget - flight_subtotal) if flights_known else budget
    basis = "flight_plus_hotel" if flights_known else "hotel_only_flight_price_unavailable"

    for hotel in hotels:
        hotel["fits_budget"] = (hotel["total_price_usd"] <= hotel_allowance) if hotel["total_price_usd"] is not None else None

    tiers_within_limit, tiers_excluded = [], []
    for tier in HOTEL_TIERS:
        tier_hotels = [h for h in hotels if h.get("tier_code") == tier["code"]]
        known = [h for h in tier_hotels if h["total_price_usd"] is not None]
        affordable = [h for h in known if h["fits_budget"]]
        if not tier_hotels or not known:
            tiers_excluded.append({"tier_code": tier["code"], "tier_name": tier["name"],
                                   "reason": "no_hotels_in_tier" if not tier_hotels else "only_unknown_tax_hotels"})
            continue
        if not affordable:
            cheapest = min(known, key=lambda h: h["total_price_usd"])
            cheapest_subtotal = round_money((flight_subtotal or 0) + cheapest["total_price_usd"])
            tiers_excluded.append({"tier_code": tier["code"], "tier_name": tier["name"], "reason": "exceeds_budget",
                                   "cheapest_subtotal_usd": cheapest_subtotal,
                                   "over_budget_by_usd": round_money(cheapest_subtotal - budget)})
            continue

        chosen = pick_tier_representative(tier["code"], affordable)
        subtotal = round_money(flight_subtotal + chosen["total_price_usd"]) if flights_known else None
        tiers_within_limit.append({
            "tier_code": tier["code"],
            "tier_name": tier["name"],
            "tier_basis": "price_ordering",
            "hotel_offer_id": chosen["offer_id"],
            "hotel_id": chosen["hotel_id"],
            "hotel_name": chosen["name"],
            "star_rating": chosen["star_rating"],
            "review_score": chosen["review_score"],
            "distance_from_center_km": chosen["distance_from_center_km"],
            "outbound_flight_offer_id": outbound_flight["offer_id"] if flights_known else None,
            "return_flight_offer_id": return_flight["offer_id"] if flights_known and return_flight else None,
            "flight_subtotal_usd": flight_subtotal,
            "hotel_total_usd": chosen["total_price_usd"],
            "flight_hotel_subtotal_usd": subtotal,
            "budget_usd": budget,
            "remaining_after_flight_hotel_usd": round_money(budget - subtotal) if flights_known else None,
            "remaining_after_hotel_only_usd": None if flights_known else round_money(budget - chosen["total_price_usd"]),
            "subtotal_basis": basis,
            "subtotal_is_indicative": flights_known,  # Flight prices are indicative cached quotes
            "affordable_hotels_in_tier": len(affordable)
        })

    budget_summary = {
        "basis": basis,
        "budget_usd": budget,
        "flight_subtotal_usd": flight_subtotal,
        "flight_price_authority": "indicative" if flights_known else "unavailable",
        "hotel_price_authority": "live_provider_quote",
        "scope_note": SUBTOTAL_SCOPE_NOTE,
        "recalculation_note": "Changing the selected flight or hotel requires the backend to recalculate these subtotals."
    }
    return budget_summary, tiers_within_limit, tiers_excluded

def select_default_offers(travel, tiers_within_limit, hotels):
    """
    Prototype default selection (backend orchestration owns the final choice):
    cheapest eligible flight per direction + the within-budget tier hotel with the best guest rating.
    """
    flights = travel["flights"] or {}
    hotel = None
    if tiers_within_limit:
        best_tier = max(tiers_within_limit, key=lambda t: (t["review_score"] or 0, -(t["hotel_total_usd"] or 0)))
        hotel = next((h for h in hotels if h["offer_id"] == best_tier["hotel_offer_id"]), None)
    return {
        "outbound_flight": (flights.get("outbound_flights") or [None])[0],
        "return_flight": (flights.get("return_flights") or [None])[0],
        "hotel": hotel,
        "selection_basis": "prototype_default (backend owns final selection)"
    }

# ==========================================
# 14. STRUCTURED AI ITINERARY ADAPTER (generate_itinerary)
# ==========================================
ALLOWED_TIMES_OF_DAY = {"morning", "afternoon", "evening", "night"}

def _approved_policy_ids():
    return {p.strip() for p in os.getenv("TRAVELMATE_APPROVED_POLICY_IDS", "").split(",") if p.strip()}

def validate_estimation_policy(policy):
    """Returns the policy if it is well-formed AND its policy_id is in the reviewed list, else None."""
    if not isinstance(policy, dict):
        return None
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or policy_id.strip() not in _approved_policy_ids():
        return None
    return policy

def compute_ancillary_estimates(trip, policy, itinerary):
    """Deterministic ancillary estimates. Food / local transport need an approved policy; otherwise "unknown"."""
    days = trip["nights"] + 1
    adults = trip["adults"]

    def policy_estimate(rate_key, label):
        rate = valid_amount(policy.get(rate_key), allow_zero=True) if policy else None
        if rate is None:
            reason = "no_approved_estimation_policy" if not policy else f"policy_has_no_{rate_key}"
            return {"status": "unknown", "amount_usd": None, "policy_id": policy.get("policy_id") if policy else None,
                    "reason": reason}
        return {"status": "estimate", "amount_usd": round_money(rate * adults * days), "policy_id": policy["policy_id"],
                "basis": f"{rate} USD per person per day x {adults} adult(s) x {days} day(s) ({label})"}

    activity_costs = [a["estimated_cost_usd_per_person"] for day in itinerary for a in day["activities"]
                      if a["cost_status"] == "estimate"]
    unknown_activities = sum(1 for day in itinerary for a in day["activities"] if a["cost_status"] == "unknown")
    activities = {"status": "unknown", "amount_usd": None, "reason": "no_activity_cost_estimates"}
    if activity_costs:
        activities = {"status": "estimate", "amount_usd": round_money(sum(activity_costs) * adults),
                      "basis": f"Sum of AI per-person activity estimates x {adults} adult(s)",
                      "includes_unknown_items": unknown_activities > 0, "unknown_items": unknown_activities}

    return {
        "activities": activities,
        "food": policy_estimate("food_usd_per_person_per_day", "food"),
        "local_transport": policy_estimate("local_transport_usd_per_person_per_day", "local transport"),
        "authority": "estimate_only (never part of authoritative totals)"
    }

def _eligible_selected_offers(trip, selected_offers, warnings):
    """Drops any selected offer that is not an eligible, request-matched offer."""
    selected_offers = selected_offers if isinstance(selected_offers, dict) else {}
    clean = {}
    expected_dates = {"outbound_flight": trip["check_in_date"], "return_flight": trip["check_out_date"]}
    for key in ["outbound_flight", "return_flight"]:
        offer = selected_offers.get(key)
        ok = (isinstance(offer, dict) and (offer.get("eligibility") or {}).get("eligible") is True
              and offer.get("flight_date") == expected_dates[key])
        if offer is not None and not ok:
            warnings.append(f"Selected {key} was not an eligible request-matched offer and was not sent to the AI.")
        clean[key] = offer if ok else None
    hotel = selected_offers.get("hotel")
    hotel_ok = (isinstance(hotel, dict) and (hotel.get("eligibility") or {}).get("eligible") is True
                and hotel.get("check_in_date") == trip["check_in_date"]
                and hotel.get("check_out_date") == trip["check_out_date"] and hotel.get("adults") == trip["adults"])
    if hotel is not None and not hotel_ok:
        warnings.append("Selected hotel was not an eligible request-matched offer and was not sent to the AI.")
    clean["hotel"] = hotel if hotel_ok else None
    return clean

def build_ai_context(trip, offers, travel_availability, budget_summary):
    def flight_view(f):
        return None if f is None else {k: f.get(k) for k in [
            "airline", "flight_date", "origin_airport", "destination_airport", "stops_label",
            "price_per_adult_usd", "group_total_usd", "price_authority"]}

    hotel = offers.get("hotel")
    return {
        "trip": public_search_parameters(trip),
        "selected_outbound_flight": flight_view(offers.get("outbound_flight")),
        "selected_return_flight": flight_view(offers.get("return_flight")) if trip["trip_type"] == "round_trip" else "not_applicable",
        "selected_hotel": None if hotel is None else {k: hotel.get(k) for k in [
            "name", "star_rating", "review_score", "distance_from_center_km", "check_in_date", "check_out_date",
            "base_price_usd", "taxes_and_fees_usd", "taxes_status", "total_price_usd"]},
        "travel_availability": travel_availability,
        "flight_hotel_budget": budget_summary
    }

def build_itinerary_messages(trip, context):
    expected_dates = [(parse_iso_date(trip["check_in_date"]) + timedelta(days=i)).isoformat()
                      for i in range(trip["nights"] + 1)]
    system_message = ("You are the TravelMate itinerary planner. You return ONLY one valid JSON object. "
                      "All prices in the context were calculated by the TravelMate backend and are authoritative.")
    user_message = f"""
TRIP CONTEXT (authoritative):
{json.dumps(context, indent=2, ensure_ascii=False)}

RULES:
1. "itinerary" must contain exactly {len(expected_dates)} day objects, one per date, in this exact order: {", ".join(expected_dates)}.
2. day_type must be "arrival" for the first date, "departure" for the last date and "full_day" for every other date.
3. Every "full_day" must have 1-4 activities. "arrival" and "departure" days may have 0-3 activities; if a day has 0 activities, "empty_day_reason" must explain why (for example travel time). Otherwise empty_day_reason is null.
4. Each activity: {{"time_of_day": "morning|afternoon|evening|night", "title": string, "description": string (max 300 chars), "location": string, "cost_status": "estimate" or "unknown", "estimated_cost_usd_per_person": number or null}}. Use "unknown" with null whenever you are not confident about the cost.
5. Never include flight or hotel prices inside activities. Never change, recalculate or invent any flight, hotel or budget number. If a flight or hotel is null or unavailable, do not assume its time, price or name.
6. "price_explanation": 3-6 English sentences explaining the selected flight and hotel costs and the flight-plus-hotel budget using ONLY numbers that appear in TRIP CONTEXT, written exactly as given with a $ sign. Say clearly that flight prices are indicative and that the subtotal is not the complete trip cost. If a value is null, say it is unavailable.
7. Write everything in English.

OUTPUT FORMAT (JSON only):
{{"itinerary": [{{"date": "YYYY-MM-DD", "day_type": "arrival", "activities": [], "empty_day_reason": "..."}}], "price_explanation": "..."}}
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

def validate_itinerary_output(parsed, expected_dates):
    """Strict schema + semantic validation. Returns the normalized itinerary or raises invalid_output."""
    problems = []
    days = parsed.get("itinerary")
    if not isinstance(days, list):
        raise TravelMateError("invalid_output", details={"problems": ["'itinerary' must be a list."]})
    if len(days) != len(expected_dates):
        problems.append(f"Expected {len(expected_dates)} days (nights + 1), got {len(days)}.")

    normalized = []
    for index, (day, expected_date) in enumerate(zip(days, expected_dates)):
        where = f"Day {index + 1}"
        if not isinstance(day, dict):
            problems.append(f"{where} must be an object.")
            continue
        if day.get("date") != expected_date:
            problems.append(f"{where} date must be {expected_date}, got {day.get('date')!r}.")
        expected_type = "arrival" if index == 0 else ("departure" if index == len(expected_dates) - 1 else "full_day")
        if day.get("day_type") != expected_type:
            problems.append(f"{where} day_type must be '{expected_type}'.")
        activities = day.get("activities")
        if not isinstance(activities, list):
            problems.append(f"{where} activities must be a list.")
            activities = []
        max_activities = 4 if expected_type == "full_day" else 3
        if len(activities) > max_activities:
            problems.append(f"{where} has more than {max_activities} activities.")
        if expected_type == "full_day" and not activities:
            problems.append(f"{where} is a full day and must contain at least one activity.")
        reason = day.get("empty_day_reason")
        if not activities and not (isinstance(reason, str) and reason.strip()):
            problems.append(f"{where} has no activities and no empty_day_reason.")

        clean_activities = []
        for a_index, activity in enumerate(activities, start=1):
            a_where = f"{where} activity {a_index}"
            if not isinstance(activity, dict):
                problems.append(f"{a_where} must be an object.")
                continue
            title, description = activity.get("title"), activity.get("description")
            if not isinstance(title, str) or not (1 <= len(title.strip()) <= 120):
                problems.append(f"{a_where} needs a title (1-120 characters).")
            if not isinstance(description, str) or len(description) > 400:
                problems.append(f"{a_where} needs a description (max 400 characters).")
            if activity.get("time_of_day") not in ALLOWED_TIMES_OF_DAY:
                problems.append(f"{a_where} time_of_day must be one of {sorted(ALLOWED_TIMES_OF_DAY)}.")
            cost_status, cost = activity.get("cost_status"), activity.get("estimated_cost_usd_per_person")
            if cost_status == "estimate":
                if valid_amount(cost, allow_zero=True) is None:
                    problems.append(f"{a_where} estimate needs a non-negative finite cost.")
            elif cost_status == "unknown":
                if cost is not None:
                    problems.append(f"{a_where} with cost_status 'unknown' must have a null cost.")
            else:
                problems.append(f"{a_where} cost_status must be 'estimate' or 'unknown'.")
            clean_activities.append({
                "time_of_day": activity.get("time_of_day"),
                "title": str(title or "").strip(),
                "description": str(description or "").strip(),
                "location": str(activity.get("location") or "").strip() or None,
                "cost_status": cost_status,
                "estimated_cost_usd_per_person": round_money(cost) if cost_status == "estimate" and valid_amount(cost, True) is not None else None
            })
        normalized.append({"day_number": index + 1, "date": day.get("date"), "day_type": day.get("day_type"),
                           "activities": clean_activities,
                           "empty_day_reason": reason.strip() if not activities and isinstance(reason, str) else None})

    if problems:
        raise TravelMateError("invalid_output", details={"problems": problems[:25]})
    return normalized

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
    if isinstance(error, groq.APITimeoutError):
        return TravelMateError("timeout", details={"reason": "ai_timeout"})
    if isinstance(error, groq.RateLimitError):
        return TravelMateError("rate_limited", details={"reason": "ai_rate_limited"})
    if isinstance(error, (groq.AuthenticationError, groq.PermissionDeniedError)):
        return TravelMateError("auth_error", details={"reason": "ai_auth_rejected"})
    if isinstance(error, groq.BadRequestError) and "json_validate_failed" in str(error):
        return TravelMateError("invalid_output", details={"problems": ["Provider JSON mode validation failed."]})
    if isinstance(error, (groq.APIConnectionError, groq.InternalServerError)):
        return TravelMateError("unavailable", details={"reason": "ai_provider_unreachable"})
    return TravelMateError("unavailable", details={"reason": f"ai_provider_error_{type(error).__name__}"})

def _generate_itinerary_validated(trip, selected_offers, travel_availability, estimation_policy, deadline,
                                  request_id, budget_summary=None, evidence=None):
    warnings = []
    provenance = {"provider": "Groq", "integration_type": "direct_official_api", "model": GROQ_MODEL,
                  "temperature": AI_TEMPERATURE, "response_format": "json_object", "automatic_retries": 0,
                  "requested_at": None, "completed_at": None, "latency_ms": None, "rate_limit": {}, "usage": None}

    def failure(error):
        return {"request_id": request_id, "status": "error", "itinerary": None, "ancillary_estimates": None,
                "price_explanation": None, "error": error.to_envelope("ai"), "warnings": warnings,
                "provenance": provenance}

    offers = _eligible_selected_offers(trip, selected_offers, warnings)
    context = build_ai_context(trip, offers, travel_availability, budget_summary)
    messages, expected_dates = build_itinerary_messages(trip, context)
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
        itinerary = validate_itinerary_output(parsed, expected_dates)
    except TravelMateError as error:
        logger.error(f"[-] AI output rejected: {error.details.get('problems', [])[:3]}")
        return failure(error)

    policy = validate_estimation_policy(estimation_policy)
    if estimation_policy is not None and policy is None:
        warnings.append("estimation_policy is not an approved policy; food and local transport stay unknown.")
    explanation, rejected = check_price_explanation(parsed.get("price_explanation"), context)
    if rejected:
        warnings.append(f"AI price explanation was dropped because it contained numbers not in the backend data: {rejected[:5]}")

    return {
        "request_id": request_id,
        "status": "success",
        "itinerary": itinerary,
        "ancillary_estimates": compute_ancillary_estimates(trip, policy, itinerary),
        "price_explanation": explanation,
        "error": None,
        "warnings": warnings,
        "provenance": provenance
    }

def generate_itinerary(trip_request, selected_offers, travel_availability, estimation_policy=None, deadline_at=None,
                       request_id=None, evidence=None):
    """
    AI itinerary adapter boundary. Returns {"status": "success", "itinerary", "ancillary_estimates", ...}
    or {"status": "error", "error": {...}} with code invalid_input | timeout | rate_limited | auth_error |
    unavailable | invalid_output | internal_error. The AI call is made at most once (no automatic retry).
    """
    request_id = request_id or new_request_id()
    try:
        trip = validate_request(trip_request)
        deadline = resolve_deadline(deadline_at)
        return _generate_itinerary_validated(trip, selected_offers, travel_availability, estimation_policy, deadline,
                                             request_id, evidence=evidence)
    except TravelMateError as error:
        return {"request_id": request_id, "status": "error", "itinerary": None, "ancillary_estimates": None,
                "price_explanation": None, "error": error.to_envelope("ai"), "warnings": [], "provenance": None}
    except Exception:
        logger.exception(f"[-] Unexpected generate_itinerary error (request_id={request_id}).")
        return {"request_id": request_id, "status": "error", "itinerary": None, "ancillary_estimates": None,
                "price_explanation": None, "error": build_error("internal_error", category="ai"), "warnings": [],
                "provenance": None}

# ==========================================
# 15. MAIN ENGINE (CALLABLE FROM BACKEND / WEBSITE)
# ==========================================
def build_engine_response(status, request_id, message="", error=None, warnings=None, data_mode=None,
                          search_parameters=None, travel=None, hotels_data=None, budget_summary=None,
                          tiers_within_limit=None, tiers_excluded=None, selected_offers=None, ai_result=None):
    """Builds the structured JSON output. Every key is always present so the UI and database never break."""
    travel = travel or {}
    flights = travel.get("flights") or {}
    hotels = travel.get("hotels") or {}

    def availability(category):
        if not category:
            return None
        return {k: category.get(k) for k in ["status", "reason", "price_authority", "error"]}

    ai_result = ai_result or {}
    return {
        "status": status,
        "request_id": request_id,
        "message": message,
        "error": error,
        "warnings": warnings or [],
        "generated_at": utc_now_iso(),
        "data_mode": data_mode,
        "search_parameters": search_parameters or {},
        "travel_availability": {"mandatory_category": MANDATORY_CATEGORY,
                                "flights": availability(flights), "hotels": availability(hotels)},
        "flights_data": {
            "outbound_flights": flights.get("outbound_flights", []),
            "return_flights": flights.get("return_flights", []),
            "alternative_date_flights": flights.get("alternative_date_flights", {"outbound": [], "return": []}),
            "capabilities": flights.get("capabilities"),
            "limitations": flights.get("limitations", []),
            "coverage": flights.get("coverage", {})
        },
        "hotels_data": hotels_data or [],
        "hotels_coverage": hotels.get("coverage", {}),
        "budget_summary": budget_summary or {},
        "budget_tiers_within_limit": tiers_within_limit or [],
        "budget_tiers_excluded": tiers_excluded or [],
        "selected_offers": selected_offers or {},
        "ai_itinerary": {
            "status": ai_result.get("status", "not_run"),
            "itinerary": ai_result.get("itinerary"),
            "ancillary_estimates": ai_result.get("ancillary_estimates"),
            "error": ai_result.get("error"),
            "provenance": ai_result.get("provenance")
        },
        "ai_recommendation_report": ai_result.get("price_explanation") or "",
        "provenance": {
            "flights": flights.get("provenance", {}),
            "hotels": hotels.get("provenance", {}),
            "hotel_destination_mapping": hotels.get("destination_mapping"),
            "exchange_rates": travel.get("exchange_rates")
        }
    }

def save_final_report(result, file_path=None):
    file_path = file_path or REPORT_FILE
    try:
        atomic_write_json(file_path, result)
        logger.info(f"[+] Final report saved to '{file_path}'")
    except OSError as e:
        logger.error(f"[-] Could not save final report ({type(e).__name__}).")

def _run_engine_steps(request_data, deadline_at, request_id, estimation_policy, cache_mode, evidence):
    # Step 1: Validate and clean the user input (before any external call)
    try:
        trip = validate_request(request_data)
        deadline = resolve_deadline(deadline_at)
    except TravelMateError as error:
        return build_engine_response("error", request_id, "Invalid or unsupported request.", error.to_envelope("request"))
    if isinstance(evidence, dict):
        evidence["inputs"] = {"request_data": request_data, "validated_trip": trip, "deadline_at": deadline.isoformat(),
                              "estimation_policy": estimation_policy}

    logger.info(f"[!] Processing {trip['trip_type_label']} request {request_id}...")

    # Step 2: Live travel adapter (flights + hotels, verified and normalized)
    travel = _search_travel_validated(trip, deadline, request_id, cache_mode, evidence)
    warnings = list(travel["warnings"])
    hotels = travel["hotels"]["offers"] if travel["hotels"] else []
    search_parameters = public_search_parameters(trip)

    if travel["status"] != "success":
        return build_engine_response("error", request_id, f"The mandatory {MANDATORY_CATEGORY} search did not succeed.",
                                     travel["error"], warnings, travel["data_mode"], search_parameters, travel, hotels)

    # Step 3: Hotel tiers and flight-plus-hotel subtotals (prototype, not the authoritative budget)
    flights = travel["flights"]
    outbound = (flights.get("outbound_flights") or [None])[0]
    return_flight = (flights.get("return_flights") or [None])[0]
    assign_hotel_tiers(hotels)
    budget_summary, tiers_within_limit, tiers_excluded = build_flight_hotel_subtotals(hotels, outbound, return_flight, trip)
    if flights["status"] != "available":
        warnings.append("No eligible exact-date flight quote: budget tiers were checked against the hotel price only.")
    if not tiers_within_limit:
        warnings.append("No hotel tier fits the budget.")
    selected_offers = select_default_offers(travel, tiers_within_limit, hotels)
    if isinstance(evidence, dict):
        evidence["normalized_context"] = {"search_travel": travel, "budget_summary": budget_summary,
                                          "budget_tiers_within_limit": tiers_within_limit,
                                          "budget_tiers_excluded": tiers_excluded, "selected_offers": selected_offers}

    # Step 4: Structured AI itinerary (single attempt, validated)
    availability = {"flights": {k: flights.get(k) for k in ["status", "reason", "price_authority"]},
                    "hotels": {k: travel["hotels"].get(k) for k in ["status", "reason", "price_authority"]}}
    # The AI receives the pre-calculated subtotal of the selected hotel so it never has to add numbers itself
    selected_hotel = selected_offers["hotel"]
    selected_tier = next((t for t in tiers_within_limit
                          if selected_hotel and t["hotel_offer_id"] == selected_hotel["offer_id"]), None)
    budget_for_ai = dict(budget_summary, selected_tier_subtotal=None if selected_tier is None else {
        k: selected_tier[k] for k in ["tier_name", "flight_subtotal_usd", "hotel_total_usd", "flight_hotel_subtotal_usd",
                                      "remaining_after_flight_hotel_usd", "remaining_after_hotel_only_usd", "subtotal_basis"]})
    ai_result = _generate_itinerary_validated(trip, selected_offers, availability, estimation_policy, deadline,
                                              request_id, budget_for_ai, evidence)
    warnings += ai_result["warnings"]
    if ai_result["status"] != "success":
        warnings.append(f"AI itinerary unavailable ({ai_result['error']['code']}); travel data is still valid.")
    if isinstance(evidence, dict):
        evidence["ai_validated_output"] = {k: ai_result.get(k) for k in
                                           ["status", "itinerary", "ancillary_estimates", "price_explanation", "error"]}

    return build_engine_response("success", request_id, "Trip plan generated.", None, warnings, travel["data_mode"],
                                 search_parameters, travel, hotels, budget_summary, tiers_within_limit,
                                 tiers_excluded, selected_offers, ai_result)

def run_travelmate_engine(request_data: dict, save_report: bool = False, deadline_at=None, request_id=None,
                          estimation_policy=None, cache_mode="default", evidence=None) -> dict:
    """
    Main entry point for the website backend. Receives the request as a dict (JSON) and returns the structured
    result as a dict (JSON). Never raises. save_report=True writes travelmate_final_report.json; it does NOT
    affect the local provider cache (use cache_mode "off" to disable cache reads and writes).
    """
    request_id = request_id or new_request_id()
    try:
        result = _run_engine_steps(request_data, deadline_at, request_id, estimation_policy, cache_mode, evidence)
    except Exception:
        logger.exception(f"[-] Unexpected engine error (request_id={request_id}).")
        result = build_engine_response("error", request_id, "Unexpected engine error.", build_error("internal_error"))
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
    """
    Removes right-to-left script (e.g., Arabic) and direction marks from a single-line value,
    so it renders left-to-right in Windows CMD without breaking table alignment.
    """
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

def print_flight_table(title, flights):
    print(f"\n  >> {title}")
    headers = [("#", 2), ("Airline", 20), ("Date", 10), ("Route", 9), ("Stops / Transit", 24),
               ("Per Adult", 10), ("Group Total", 11), ("Authority", 10)]
    rows = [[i, to_console_name(f["airline"]), f["flight_date"], f"{f['origin_airport']}-{f['destination_airport']}",
             f["stops_label"], format_money(f["price_per_adult_usd"]), format_money(f["group_total_usd"]),
             f["price_authority"]] for i, f in enumerate(flights, start=1)]
    print_table(headers, rows)

def print_engine_result(result, show_full_json=False):
    """Prints the structured engine response in clearly separated, readable sections."""
    print_section(f"TRAVELMATE RESULT  |  STATUS: {result['status'].upper()}  |  {result['request_id']}")
    print(f"  {result['message']}  (data mode: {result['data_mode']})")
    if result["error"]:
        print(f"  [-] {result['error']['code']}: {result['error']['message']}")
        for field in result["error"]["details"].get("fields", []):
            print(f"      - {field['field']}: {field['message']}")
    for warning in result["warnings"]:
        print(f"  [!] {to_console_name(warning)}")

    print_section("1. SEARCH PARAMETERS & AVAILABILITY")
    print(json.dumps(sanitize_for_console(result["search_parameters"]), indent=4, ensure_ascii=False))
    for category in ["flights", "hotels"]:
        info = result["travel_availability"].get(category)
        if info:
            print(f"  {category.title():8}: {info['status']} (reason: {info['reason']}, prices: {info['price_authority']})")

    flights_data = result["flights_data"]
    print_section("2. FLIGHTS  (flights_data) - indicative cached quotes")
    print_flight_table("Outbound (exact requested date - eligible)", flights_data["outbound_flights"])
    if result["search_parameters"].get("trip_type") == "round_trip":
        print_flight_table("Return (exact requested date - eligible)", flights_data["return_flights"])
    for direction, offers in flights_data["alternative_date_flights"].items():
        if offers:
            print_flight_table(f"{direction.title()} ALTERNATIVE DATES (NOT eligible, needs a new search)", offers)

    print_section("3. HOTELS  (hotels_data) - verified dates & occupancy, prices include known taxes")
    headers = [("#", 2), ("Hotel", 30), ("Tier", 4), ("Stars", 5), ("Rating", 6), ("Km", 5),
               ("Base", 10), ("Taxes", 9), ("Total", 10), ("In Budget", 9)]
    rows = [[i, to_console_name(h["name"], fallback=f"Hotel #{h['hotel_id']}"), h.get("tier_code", "-"),
             h["star_rating"] or "-", h["review_score"] or "-", h["distance_from_center_km"] or "-",
             format_money(h["base_price_usd"]), format_money(h["taxes_and_fees_usd"]),
             format_money(h["total_price_usd"]), {True: "Yes", False: "No"}.get(h.get("fits_budget"), "unknown")]
            for i, h in enumerate(result["hotels_data"], start=1)]
    print_table(headers, rows)

    print_section("4. FLIGHT + HOTEL SUBTOTALS WITHIN BUDGET  (budget_tiers_within_limit)")
    summary = result["budget_summary"]
    if summary:
        print(f"  Basis: {summary['basis']} | Flights: {format_money(summary['flight_subtotal_usd'])} "
              f"({summary['flight_price_authority']}) | Budget: {format_money(summary['budget_usd'])}")
        print(f"  Note: {summary['scope_note']}")
    headers = [("Tier", 30), ("Hotel", 26), ("Flights", 10), ("Hotel", 10), ("Subtotal", 10), ("Remaining", 10)]
    rows = [[t["tier_name"], to_console_name(t["hotel_name"], fallback=f"Hotel #{t['hotel_id']}"),
             format_money(t["flight_subtotal_usd"]), format_money(t["hotel_total_usd"]),
             format_money(t["flight_hotel_subtotal_usd"]),
             format_money(t["remaining_after_flight_hotel_usd"] if t["remaining_after_flight_hotel_usd"] is not None
                          else t["remaining_after_hotel_only_usd"])]
            for t in result["budget_tiers_within_limit"]]
    print_table(headers, rows)
    for tier in result["budget_tiers_excluded"]:
        extra = f" (over by {format_money(tier['over_budget_by_usd'])})" if "over_budget_by_usd" in tier else ""
        print(f"  [x] Excluded: {tier['tier_name']} - {tier['reason']}{extra}")

    ai = result["ai_itinerary"]
    print_section(f"5. AI ITINERARY  (ai_itinerary)  |  STATUS: {ai['status'].upper()}")
    if ai["error"]:
        print(f"  [-] {ai['error']['code']}: {ai['error']['message']}")
        for problem in ai["error"]["details"].get("problems", [])[:10]:
            print(f"      - {problem}")
    for day in ai["itinerary"] or []:
        print(f"\n  Day {day['day_number']} | {day['date']} | {day['day_type']}")
        if not day["activities"]:
            print(f"    (no activities: {to_console_name(day['empty_day_reason'])})")
        for activity in day["activities"]:
            cost = format_money(activity["estimated_cost_usd_per_person"]) + " pp (estimate)" \
                if activity["cost_status"] == "estimate" else "cost unknown"
            print(f"    - [{activity['time_of_day']:9}] {to_console_name(activity['title'])} | {cost}")
    if ai["ancillary_estimates"]:
        print("\n  Ancillary estimates (never authoritative):")
        for key in ["activities", "food", "local_transport"]:
            item = ai["ancillary_estimates"][key]
            print(f"    {key:16}: {item['status']:8} {format_money(item['amount_usd'])}  {item.get('reason') or item.get('basis', '')}")

    print_section("6. AI PRICE EXPLANATION  (ai_recommendation_report)")
    print("  " + (to_console_name(result["ai_recommendation_report"]) or "[-] Not available."))

    if show_full_json:
        print_section("FULL STRUCTURED JSON RESPONSE (console-safe copy)")
        print(json.dumps(sanitize_for_console(result), indent=4, ensure_ascii=False))

    print("\n" + "=" * CONSOLE_WIDTH)
    print(f"  [+] Full report saved to '{REPORT_FILE}'")
    if not show_full_json:
        print("  [i] Run with --json to also print the full structured JSON response.")
    print("=" * CONSOLE_WIDTH)

# ==========================================
# 17. MAIN EXECUTION (LOCAL CLI TESTING ONLY)
# ==========================================
if __name__ == "__main__":
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

    print("\n--- Welcome to TravelMate (Flight & Hotel Assistant) ---")
    print(f"Supported destinations: {', '.join(sorted(c['name'] for c in SUPPORTED_CITIES.values()))}")

    trip_type = prompt_until_valid(
        "Select trip type - Enter '1' for One-Way or '2' for Two-Way (Round-Trip): ", validate_trip_type)
    is_round_trip = (trip_type == "round_trip")

    origin = prompt_until_valid(
        "Enter origin airport code (e.g., IST): ", lambda v: validate_airport_code(v, "origin"))
    destination_city = prompt_until_valid(
        "Enter destination city (e.g., Cairo): ", validate_city_name)
    destination_airport = input("Enter destination airport code (press Enter for the city's main airport): ").strip()

    arrival_date = prompt_until_valid(
        "Enter departure / hotel check-in date (YYYY-MM-DD): ",
        lambda v: validate_date(v, "check_in_date", min_date=date.today()))
    checkout_prompt = "Enter return flight / hotel check-out date (YYYY-MM-DD): " if is_round_trip \
        else "Enter hotel check-out date (YYYY-MM-DD): "
    departure_date = prompt_until_valid(
        checkout_prompt, lambda v: validate_date(v, "check_out_date", min_date=arrival_date + timedelta(days=1)))

    adults = prompt_until_valid(
        "Enter number of adult travelers: ", lambda v: validate_positive_int(v, "adults", MAX_ADULTS))
    rooms_text = input("Enter number of rooms (press Enter for 1): ").strip()
    budget_usd = prompt_until_valid(
        "Enter your total budget in USD (e.g., 2500): ", validate_budget)

    request_data = {
        "trip_type": trip_type,
        "origin": origin,
        "destination_city": destination_city,
        "check_in_date": arrival_date.isoformat(),
        "check_out_date": departure_date.isoformat(),
        "adults": adults,
        "budget_usd": budget_usd,
        "destination_airport": destination_airport or None,
        "rooms": rooms_text or None
    }

    print_section("PROCESSING REQUEST")
    result = run_travelmate_engine(request_data, save_report=True)
    print_engine_result(result, show_full_json="--json" in sys.argv)
