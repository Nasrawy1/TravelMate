"""
Local entry point for the TravelMate adapters (CLI, offline tests, evidence scripts).

The adapter code lives in backend/app/adapters/travelmate.py (PR #25 review, item 3), so BE-03 imports it directly.
This file keeps `import travalmate` and `python travalmate.py` working from this folder, with this folder's
.env, cache and reports (TRAVELMATE_HOME).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("TRAVELMATE_HOME", _HERE)
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.adapters import travelmate as _adapter  # noqa: E402

if __name__ == "__main__":
    _adapter.main()
else:
    sys.modules[__name__] = _adapter  # `import travalmate` returns the backend module itself (one source of truth)
