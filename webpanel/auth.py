"""Single-admin login for the web panel: WEBPANEL_USERNAME / WEBPANEL_PASSWORD_HASH
in .env, session cookie signed by WEBPANEL_SECRET_KEY (see README for how to
generate the hash). No user management — this panel controls infrastructure,
not a multi-tenant app.
"""

import base64
import hashlib
import os
import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="webpanel/templates")

_SESSION_KEY = "webpanel_authed"
_SCRYPT_PARAMS = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT_PARAMS)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, digest_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except Exception:
        return False
    actual = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT_PARAMS)
    return secrets.compare_digest(actual, expected)


def is_authed(request: Request) -> bool:
    return bool(request.session.get(_SESSION_KEY))


async def require_login(request: Request):
    """FastAPI dependency: 303-redirects to /login if there's no session.
    Attach at router-include time so every protected route is covered:
    app.include_router(some_router, dependencies=[Depends(require_login)]).
    """
    if not is_authed(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if is_authed(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    expected_user = os.getenv("WEBPANEL_USERNAME", "")
    expected_hash = os.getenv("WEBPANEL_PASSWORD_HASH", "")
    valid = bool(expected_user and expected_hash
                 and secrets.compare_digest(username, expected_user)
                 and verify_password(password, expected_hash))
    if valid:
        request.session[_SESSION_KEY] = True
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Invalid username or password"}, status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
