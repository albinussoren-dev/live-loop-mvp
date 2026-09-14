import secrets
from fastapi import APIRouter, Request, Response

router = APIRouter()

@router.get("/api/auth/csrf")
def csrf_token(request: Request, response: Response):
    token = request.cookies.get("looplive_csrf") or secrets.token_urlsafe(32)
    # Frontend JavaScript needs the token in the response body; the cookie is only the comparison value.
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie("looplive_csrf", token, httponly=False, secure=secure, samesite="none" if secure else "lax", path="/")
    return {"token": token}
