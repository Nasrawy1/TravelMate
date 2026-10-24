"""Flights adapter (API-05 #18): live Google Flights round trips through the shared travel adapter."""
from app.adapters.travelmate import search_travel


def search_flights(trip_request, **kwargs):
    """search_travel limited to flights; hotels is returned as unavailable / not_requested."""
    return search_travel(trip_request, categories=("flights",), **kwargs)


__all__ = ["search_flights", "search_travel"]
