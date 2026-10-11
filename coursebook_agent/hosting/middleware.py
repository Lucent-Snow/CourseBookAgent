"""Materialize only the authenticated guest's workspace for each request."""
import asyncio
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from coursebook_agent.config import _base_config
from coursebook_agent.hosting.blob_store import BlobWorkspace, PrivateBlobStore, WriteConflict
from coursebook_agent.hosting.workspaces import (
    COOKIE, MAX_AGE, enabled, issue_cookie, request_workspace, verify_cookie, workspace_scope,
)


class GuestWorkspaceMiddleware(BaseHTTPMiddleware):
    async def __call__(self, scope, receive, send):
        if not enabled():
            return await self.app(scope, receive, send)
        return await super().__call__(scope, receive, send)

    async def dispatch(self, request, call_next):
        if not enabled() or not request.url.path.startswith('/api/'):
            return await call_next(request)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and urlparse(origin).netloc != request.headers.get('host')):
                return JSONResponse({'detail': '请从本站页面操作'}, status_code=403)
        cookie = request.cookies.get(COOKIE)
        owner = verify_cookie(cookie)
        new = owner is None
        if new:
            cookie = issue_cookie()
            owner = verify_cookie(cookie)
        cloud = os.getenv('COURSEBOOK_CLOUD') == '1'
        temporary = tempfile.TemporaryDirectory(prefix='coursebook-') if cloud else None
        root = Path(temporary.name) if temporary else _base_config.data_dir / 'guests' / owner
        store = PrivateBlobStore() if cloud else None
        workspace = BlobWorkspace(store, owner, root) if cloud else None
        token = request_workspace.set(workspace)
        try:
            if workspace:
                await asyncio.to_thread(workspace.checkout)
            from coursebook_agent.hosting.preset import install_preset
            await asyncio.to_thread(install_preset, root)
            with workspace_scope(owner, root):
                response = await call_next(request)
                if workspace and response.status_code < 400:
                    await asyncio.to_thread(workspace.flush)
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['Vary'] = 'Cookie'
            if new:
                response.set_cookie(COOKIE, cookie, max_age=MAX_AGE, httponly=True,
                                    secure=cloud, samesite='lax', path='/')
            return response
        except WriteConflict:
            return JSONResponse({'detail': '资料刚刚发生变化，请刷新后重试'}, status_code=409)
        except httpx.HTTPError:
            return JSONResponse({'detail': '云端存档暂时不可用，请稍后重试'}, status_code=503)
        finally:
            request_workspace.reset(token)
            if store:
                store.close()
            if temporary:
                temporary.cleanup()


import httpx
