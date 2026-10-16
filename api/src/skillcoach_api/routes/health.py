"""Liveness endpoint — unauthenticated (contracts/api.md)."""

from fastapi import APIRouter

from skillcoach_api.config import get_settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": get_settings().git_sha}
