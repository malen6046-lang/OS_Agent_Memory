"""Synchronous test facade backed by HTTPX's ASGI transport."""

from __future__ import annotations

from functools import partial
from typing import Any

import httpx
from anyio.from_thread import start_blocking_portal


class ASGITestClient:
    def __init__(self, app: Any, *, raise_app_exceptions: bool = True) -> None:
        self._app = app
        self._raise_app_exceptions = raise_app_exceptions

    def __enter__(self) -> "ASGITestClient":
        self._portal_context = start_blocking_portal(backend="asyncio")
        self._portal = self._portal_context.__enter__()
        self._portal.call(self._startup)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            self._portal.call(self._shutdown)
        finally:
            self._portal_context.__exit__(exc_type, exc, traceback)

    async def _startup(self) -> None:
        self._lifespan = self._app.router.lifespan_context(self._app)
        await self._lifespan.__aenter__()
        transport = httpx.ASGITransport(
            app=self._app,
            raise_app_exceptions=self._raise_app_exceptions,
        )
        self._client = httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        )
        await self._client.__aenter__()

    async def _shutdown(self) -> None:
        await self._client.__aexit__(None, None, None)
        await self._lifespan.__aexit__(None, None, None)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return self._portal.call(partial(self._client.request, method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)
