"""Public facade of the matching module."""
from .models import MatchScore
from .service import score_jobs_for_user

__all__ = ["MatchScore", "score_jobs_for_user"]
