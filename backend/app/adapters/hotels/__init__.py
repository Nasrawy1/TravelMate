"""Hotels adapter (API-05 #18): live Booking.com hotels through the shared travel adapter."""
from app.adapters.travelmate import search_travel


def search_hotels(trip_request, **kwargs):
    """search_travel limited to hotels; flights is returned as unavailable / not_requested."""
    return search_travel(trip_request, categories=("hotels",), **kwargs)


__all__ = ["search_hotels", "search_travel"]
