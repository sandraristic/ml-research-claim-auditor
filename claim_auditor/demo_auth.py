import os
import secrets
from base64 import b64decode
from binascii import Error as Base64Error

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def install_demo_auth(app: FastAPI) -> None:
    """Protect all routes except the public health check in production mode."""
    enabled = os.environ.get("APP_ENV", "development").lower() == "production"
    username = os.environ.get("DEMO_USERNAME", "")
    password = os.environ.get("DEMO_PASSWORD", "")

    if enabled and (not username or not password):
        raise RuntimeError(
            "Production demo authentication requires DEMO_USERNAME and DEMO_PASSWORD."
        )

    def unauthorized() -> JSONResponse:
        return JSONResponse(
            {"detail": "Demo credentials required."},
            status_code=401,
            headers={
                "WWW-Authenticate": 'Basic realm="Research Claim Auditor Demo"',
                "Cache-Control": "no-store",
            },
        )

    @app.middleware("http")
    async def require_demo_auth(request: Request, call_next):
        if not enabled or request.url.path == "/api/v1/health":
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, separator, value = header.partition(" ")
        if not separator or scheme.lower() != "basic":
            return unauthorized()

        try:
            decoded = b64decode(value.strip(), validate=True).decode("utf-8")
            supplied_user, delim, supplied_password = decoded.partition(":")
        except (Base64Error, UnicodeDecodeError, ValueError):
            return unauthorized()

        if not delim:
            return unauthorized()

        user_ok = secrets.compare_digest(
            supplied_user.encode("utf-8"), username.encode("utf-8")
        )
        password_ok = secrets.compare_digest(
            supplied_password.encode("utf-8"), password.encode("utf-8")
        )
        if not (user_ok and password_ok):
            return unauthorized()

        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
