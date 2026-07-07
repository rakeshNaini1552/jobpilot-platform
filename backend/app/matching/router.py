"""matches endpoints — populated in its implementation phase."""
from fastapi import APIRouter

router = APIRouter(prefix="/matches", tags=["matches"])
