import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("routeproof")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def NotFound(what: str = "Resource") -> AppError:
    return AppError(404, "not_found", f"{what} not found")


def Forbidden(msg: str = "You do not have access to this resource") -> AppError:
    return AppError(403, "forbidden", msg)


def Conflict(code: str, msg: str, details: dict | None = None) -> AppError:
    return AppError(409, code, msg, details)


def BadRequest(code: str, msg: str, details: dict | None = None) -> AppError:
    return AppError(400, code, msg, details)


def _body(code, message, details=None):
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_handlers(app: FastAPI):
    @app.exception_handler(AppError)
    async def _app(_: Request, e: AppError):
        return JSONResponse(_body(e.code, e.message, e.details), status_code=e.status)

    @app.exception_handler(HTTPException)
    async def _http(_: Request, e: HTTPException):
        return JSONResponse(_body("http_error", str(e.detail)), status_code=e.status_code, headers=e.headers)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, e: RequestValidationError):
        errs = [{"loc": [str(x) for x in er["loc"]], "msg": er["msg"]} for er in e.errors()]
        return JSONResponse(_body("validation_error", "Request validation failed", {"errors": errs}), status_code=422)

    @app.exception_handler(Exception)
    async def _any(_: Request, e: Exception):
        log.exception("unhandled error")
        return JSONResponse(_body("internal_error", "Something went wrong"), status_code=500)
