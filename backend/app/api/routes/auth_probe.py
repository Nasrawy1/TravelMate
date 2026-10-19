from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user_id

router = APIRouter()


@router.get("/auth/probe")
async def auth_probe(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    return {"status": "ok", "user_id": user_id}
