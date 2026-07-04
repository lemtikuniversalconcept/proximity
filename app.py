from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import load_settings
from service import ProximityService
from storage import create_store

try:  # Optional dependency for local/offline development.
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover - optional import
    FastAPI = None  # type: ignore
    Header = None  # type: ignore
    HTTPException = None  # type: ignore
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore


def _json_response(status: int, payload: dict[str, Any]) -> tuple[int, list[tuple[str, str]], bytes]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    headers = [
        ("content-type", "application/json"),
        ("content-length", str(len(body))),
        ("access-control-allow-origin", "*"),
    ]
    return status, headers, body


def _error_response(status: int, message: str) -> tuple[int, list[tuple[str, str]], bytes]:
    return _json_response(status, {"status": "error", "message": message})


def _parse_query(query_string: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not query_string:
        return result
    for chunk in query_string.split("&"):
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
        else:
            key, value = chunk, ""
        result[key] = value
    return result


def _canonical_path(path: str) -> str:
    normalized = path.rstrip("/") or "/"
    if normalized.startswith("/api/v1/proximity"):
        remainder = normalized[len("/api/v1/proximity"):]
        return remainder or "/"
    if normalized.startswith("/api/v1"):
        remainder = normalized[len("/api/v1"):]
        return remainder or "/"
    return normalized


class ProximityASGIApp:
    def __init__(self) -> None:
        self.settings = load_settings(Path(__file__).resolve().parent)
        self.store = create_store(self.settings.database_url, self.settings.local_database_path)
        self.service = ProximityService(self.settings, self.store)

    async def _receive_body(self, receive) -> bytes:
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        return bytes(body)

    def _parse_json_bytes(self, raw: bytes) -> dict[str, Any]:
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    async def handle(
        self,
        method: str,
        path: str,
        query_string: str = "",
        body: bytes = b"",
        internal_key: str | None = None,
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        normalized_path = _canonical_path(path)
        try:
            if method == "GET" and normalized_path == "/health":
                return _json_response(200, self.service.health())
            if method == "GET" and normalized_path == "/queries":
                params = _parse_query(query_string)
                key = internal_key or params.get("x_internal_key")
                if key != self.settings.internal_api_key:
                    return _error_response(401, "invalid internal api key")
                limit = int(params.get("limit", "20") or "20")
                return _json_response(200, {"status": "success", "data": self.store.list_queries(limit)})
            if method == "POST" and normalized_path == "/find":
                payload = self._parse_json_bytes(body)
                if not isinstance(payload, dict):
                    return _error_response(400, "invalid JSON body")
                key = internal_key or _parse_query(query_string).get("x_internal_key")
                try:
                    result = await self.service.find(payload, key)
                    return _json_response(200, result)
                except PermissionError as exc:
                    return _error_response(401, str(exc))
                except ValueError as exc:
                    return _error_response(400, str(exc))
            if method == "GET" and normalized_path == "/":
                return _json_response(200, {"status": "ok", "service": "proximity", "endpoints": ["/health", "/find", "/queries"]})
            return _error_response(404, "endpoint not found")
        except json.JSONDecodeError:
            return _error_response(400, "invalid JSON body")
        except Exception as exc:
            return _error_response(500, f"internal server error: {exc}")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await send({"type": "http.response.start", "status": 500, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"Unsupported scope"})
            return

        body = await self._receive_body(receive)
        header_map = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
        status, response_headers, response_body = await self.handle(
            scope["method"].upper(),
            scope["path"],
            scope.get("query_string", b"").decode("utf-8"),
            body,
            header_map.get("x-internal-key"),
        )

        await send({"type": "http.response.start", "status": status, "headers": [(k.encode("latin1"), v.encode("latin1")) for k, v in response_headers]})
        await send({"type": "http.response.body", "body": response_body})


fallback_app = ProximityASGIApp()

if FastAPI is not None:
    api_app = FastAPI(title="Proximity & Officer Finder Service", version="1.0")

    @api_app.get("/health")
    @api_app.get("/api/v1/proximity/health")
    async def health() -> JSONResponse:  # type: ignore[valid-type]
        return JSONResponse(fallback_app.service.health())

    @api_app.get("/queries")
    @api_app.get("/api/v1/queries")
    async def queries(
        limit: int = 20,
        x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
    ) -> JSONResponse:  # type: ignore[valid-type]
        if x_internal_key != fallback_app.settings.internal_api_key:
            return JSONResponse({"status": "error", "message": "invalid internal api key"}, status_code=401)
        return JSONResponse({"status": "success", "data": fallback_app.store.list_queries(limit)})

    @api_app.post("/find")
    @api_app.post("/api/v1/find")
    async def find(
        request: Request,
        x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
    ) -> JSONResponse:  # type: ignore[valid-type]
        payload = await request.json()
        if not isinstance(payload, dict):
            return JSONResponse({"status": "error", "message": "invalid JSON body"}, status_code=400)
        try:
            result = await fallback_app.service.find(payload, x_internal_key)
            return JSONResponse(result)
        except PermissionError as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=401)
        except ValueError as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

    @api_app.get("/")
    @api_app.get("/api/v1")
    async def root() -> JSONResponse:  # type: ignore[valid-type]
        return JSONResponse({"status": "ok", "service": "proximity", "endpoints": ["/api/v1/find", "/api/v1/queries", "/api/v1/proximity/health"]})

    app = api_app
else:
    app = fallback_app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=fallback_app.settings.host, port=fallback_app.settings.port, reload=False)
