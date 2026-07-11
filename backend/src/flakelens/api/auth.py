import secrets

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from flakelens.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

COOKIE_NAME = "fl_session"


def is_authenticated(request: Request) -> bool:
    """True if the request carries the shared token via cookie or Bearer header."""
    token = settings.access_token
    if not token:
        return True  # open mode
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and secrets.compare_digest(cookie, token):
        return True
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return secrets.compare_digest(auth[7:].strip(), token)
    return False


class LoginRequest(BaseModel):
    token: str


@router.get("/status")
def auth_status(request: Request):
    return {
        "required": bool(settings.access_token),
        "authenticated": is_authenticated(request),
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    if not settings.access_token:
        return {"required": False, "authenticated": True}
    if not secrets.compare_digest(payload.token, settings.access_token):
        response.status_code = 401
        return {"authenticated": False, "detail": "Invalid access token"}
    response.set_cookie(
        COOKIE_NAME,
        settings.access_token,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        max_age=60 * 60 * 24 * 30,
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"authenticated": False}
