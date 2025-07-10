from fastapi import HTTPException, Request

from ..config import ADMIN_TOKEN


async def check_token(request: Request) -> None:
    token = request.query_params.get("token")
    if ADMIN_TOKEN and token == ADMIN_TOKEN:
        return
    raise HTTPException(status_code=403, detail="Forbidden")
