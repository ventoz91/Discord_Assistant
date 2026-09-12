"""FastAPI app for the game-server web panel. Runs inside the same process as
the Discord bot (see main.py) so it can share gamefunc/ control classes and
post directly to Discord channels — no separate service, no duplicated config.
"""

import os

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from webpanel import auth
from webpanel.routes_deploy import router as deploy_router
from webpanel.routes_servers import router as servers_router


def create_app(bot=None) -> FastAPI:
    app = FastAPI(title="Game Server Panel", docs_url=None, redoc_url=None)
    app.state.bot = bot  # used by routes to post action notifications to Discord

    secret = os.getenv("WEBPANEL_SECRET_KEY", "")
    if not secret:
        raise RuntimeError(
            "WEBPANEL_SECRET_KEY not set in .env — required to sign panel sessions. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    app.add_middleware(
        SessionMiddleware, secret_key=secret, same_site="lax", max_age=60 * 60 * 24 * 14,
    )

    app.mount("/static", StaticFiles(directory="webpanel/static"), name="static")

    app.include_router(auth.router)
    app.include_router(servers_router, dependencies=[Depends(auth.require_login)])
    app.include_router(deploy_router, dependencies=[Depends(auth.require_login)])

    return app
