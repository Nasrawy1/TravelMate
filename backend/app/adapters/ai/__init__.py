"""AI itinerary adapter (API-04 #17): Groq structured itinerary with validation and a single attempt."""
from app.adapters.travelmate import GROQ_MODEL, generate_itinerary

__all__ = ["GROQ_MODEL", "generate_itinerary"]
