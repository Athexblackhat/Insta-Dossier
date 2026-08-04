"""
session manager — aiohttp session pool for instagram
handles: session creation, cookie persistence, instagram-specific headers,
         session rotation, expiry detection
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ManagedSession:
    account_id: str
    session: aiohttp.ClientSession
    cookie_jar: dict = field(default_factory=dict)
    csrf_token: str = ""
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    request_count: int = 0
    is_active: bool = True
    proxy_bound: Optional[str] = None


class SessionManager:
    """
    manages aiohttp sessions with instagram-specific defaults

    usage:
        manager = SessionManager(max_sessions=50, session_ttl=1200)
        session = await manager.get_session("scraper_01")
    """

    INSTAGRAM_BASE_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(
        self,
        max_sessions: int = 50,
        session_ttl: int = 1200,
        max_requests_per_session: int = 200,
        cleanup_interval: int = 180,
    ):
        self.max_sessions = max_sessions
        self.session_ttl = session_ttl
        self.max_requests_per_session = max_requests_per_session
        self.cleanup_interval = cleanup_interval

        self._sessions: dict[str, ManagedSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        async with self._lock:
            for managed in self._sessions.values():
                await self._close_session(managed)
            self._sessions.clear()

    async def get_session(self, account_id: str) -> aiohttp.ClientSession:
        async with self._lock:
            if account_id in self._sessions:
                managed = self._sessions[account_id]
                if self._is_session_valid(managed):
                    managed.last_used_at = time.time()
                    managed.request_count += 1
                    return managed.session
                await self._close_session(managed)
                del self._sessions[account_id]

            if len(self._sessions) >= self.max_sessions:
                await self._evict_oldest()

            headers = self.INSTAGRAM_BASE_HEADERS.copy()
            headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            )

            session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers,
            )

            managed = ManagedSession(account_id=account_id, session=session)
            self._sessions[account_id] = managed
            logger.debug("[session] created: %s (total: %d)", account_id, len(self._sessions))
            return session

    async def invalidate_session(self, account_id: str):
        async with self._lock:
            if account_id in self._sessions:
                await self._close_session(self._sessions[account_id])
                del self._sessions[account_id]

    def _is_session_valid(self, managed: ManagedSession) -> bool:
        if not managed.is_active or managed.session.closed:
            return False
        if time.time() - managed.created_at > self.session_ttl:
            return False
        if managed.request_count >= self.max_requests_per_session:
            return False
        return True

    async def _close_session(self, managed: ManagedSession):
        managed.is_active = False
        try:
            if not managed.session.closed:
                await managed.session.close()
        except Exception:
            pass

    async def _evict_oldest(self):
        if not self._sessions:
            return
        oldest_id = min(self._sessions.keys(), key=lambda k: self._sessions[k].last_used_at)
        await self._close_session(self._sessions[oldest_id])
        del self._sessions[oldest_id]

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(self.cleanup_interval)
            async with self._lock:
                to_remove = [
                    aid for aid, m in self._sessions.items()
                    if not self._is_session_valid(m)
                ]
                for aid in to_remove:
                    await self._close_session(self._sessions[aid])
                    del self._sessions[aid]

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)