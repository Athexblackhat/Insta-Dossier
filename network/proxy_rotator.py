"""
proxy rotator — socks4/socks5 proxy pool manager
instagram-optimized: stricter health checks, faster rotation, residential preference
handles: loading, rotation, dead proxy detection, cooldown, auto-revival
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ProxyStatus(Enum):
    FRESH = "fresh"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    DEAD = "dead"
    TESTING = "testing"


@dataclass
class ProxyInfo:
    address: str
    protocol: str = "socks5"
    status: ProxyStatus = ProxyStatus.FRESH
    fail_count: int = 0
    success_count: int = 0
    last_used_at: float = 0.0
    last_checked_at: float = 0.0
    cooldown_until: float = 0.0
    response_time_ms: float = 0.0
    region: Optional[str] = None
    is_residential: bool = False
    added_at: float = field(default_factory=time.time)
    instagram_blocked: bool = False

    @property
    def is_available(self) -> bool:
        return self.status in (ProxyStatus.FRESH, ProxyStatus.ACTIVE) and not self.instagram_blocked

    @property
    def formatted(self) -> str:
        addr = self.address
        if "://" in addr:
            return addr
        return f"{self.protocol}://{addr}"


class ProxyRotator:
    """
    async proxy pool manager — instagram optimized

    defaults differ from tiktok version:
    - cooldown: 600s (10 min, instagram is stricter)
    - max_failures: 2 (faster dead detection)
    - health check: more frequent
    - residential preference: weighted mode favors residential IPs
    """

    def __init__(
        self,
        proxy_file: Optional[str] = None,
        proxy_list: Optional[list[str]] = None,
        rotation_mode: str = "weighted",
        max_failures: int = 2,
        cooldown_seconds: int = 600,
        health_check_timeout: float = 5.0,
        min_proxies_required: int = 10,
        auto_health_check: bool = True,
        health_check_interval: int = 300,
        prefer_residential: bool = True,
    ):
        self.proxy_file = proxy_file
        self.proxy_list = proxy_list or []
        self.rotation_mode = rotation_mode
        self.max_failures = max_failures
        self.cooldown_seconds = cooldown_seconds
        self.health_check_timeout = health_check_timeout
        self.min_proxies_required = min_proxies_required
        self.auto_health_check = auto_health_check
        self.health_check_interval = health_check_interval
        self.prefer_residential = prefer_residential

        self._proxies: dict[str, ProxyInfo] = {}
        self._available: list[str] = []
        self._round_robin_index: int = 0
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None

    async def load_proxies(self) -> int:
        raw_proxies = []

        if self.proxy_file:
            try:
                with open(self.proxy_file, "r") as f:
                    raw_proxies = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]
                logger.info("[proxy] loaded %d proxies from %s", len(raw_proxies), self.proxy_file)
            except FileNotFoundError:
                logger.error("[proxy] file not found: %s", self.proxy_file)
                return 0

        if self.proxy_list:
            raw_proxies.extend(self.proxy_list)

        async with self._lock:
            for raw in raw_proxies:
                parsed = self._parse_proxy_string(raw)
                if parsed:
                    self._proxies[parsed.address] = parsed

            self._rebuild_available_list()
            logger.info("[proxy] pool ready — %d total, %d available", len(self._proxies), len(self._available))

            if self.auto_health_check:
                self._health_check_task = asyncio.create_task(self._health_check_loop())

        return len(self._proxies)

    async def get_proxy(self, prefer_fresh: bool = False) -> Optional[str]:
        async with self._lock:
            if not self._available:
                logger.warning("[proxy] pool exhausted")
                return None

            if self.rotation_mode == "round_robin":
                selected = self._get_round_robin()
            elif self.rotation_mode == "weighted":
                selected = self._get_weighted(prefer_fresh)
            else:
                selected = random.choice(self._available)

            if selected:
                info = self._proxies[selected]
                info.last_used_at = time.time()
                return info.formatted

            return None

    async def get_proxy_batch(self, count: int) -> list[str]:
        proxies = []
        for _ in range(count):
            proxy = await self.get_proxy()
            if proxy:
                proxies.append(proxy)
            else:
                break
        return proxies

    async def report_success(self, proxy_str: str):
        async with self._lock:
            info = self._find_proxy(proxy_str)
            if info:
                info.success_count += 1
                info.fail_count = 0
                info.status = ProxyStatus.ACTIVE
                info.instagram_blocked = False
                if info.address not in self._available:
                    self._available.append(info.address)

    async def report_failure(self, proxy_str: str, rate_limited: bool = False, instagram_blocked: bool = False):
        async with self._lock:
            info = self._find_proxy(proxy_str)
            if not info:
                return

            if rate_limited:
                info.status = ProxyStatus.COOLDOWN
                info.cooldown_until = time.time() + self.cooldown_seconds
                if info.address in self._available:
                    self._available.remove(info.address)
                logger.debug("[proxy] %s rate limited — cooldown %ds", _mask_addr(info.address), self.cooldown_seconds)
                return

            if instagram_blocked:
                info.instagram_blocked = True
                if info.address in self._available:
                    self._available.remove(info.address)
                logger.debug("[proxy] %s instagram blocked", _mask_addr(info.address))
                return

            info.fail_count += 1
            if info.fail_count >= self.max_failures:
                info.status = ProxyStatus.DEAD
                if info.address in self._available:
                    self._available.remove(info.address)
                logger.warning("[proxy] %s marked DEAD", _mask_addr(info.address))

    async def get_pool_stats(self) -> dict:
        async with self._lock:
            total = len(self._proxies)
            active = sum(1 for p in self._proxies.values() if p.status == ProxyStatus.ACTIVE)
            fresh = sum(1 for p in self._proxies.values() if p.status == ProxyStatus.FRESH)
            cooldown = sum(1 for p in self._proxies.values() if p.status == ProxyStatus.COOLDOWN)
            dead = sum(1 for p in self._proxies.values() if p.status == ProxyStatus.DEAD)
            available = len(self._available)
            residential = sum(1 for p in self._proxies.values() if p.is_residential)

            return {
                "total": total,
                "available": available,
                "active": active,
                "fresh": fresh,
                "cooldown": cooldown,
                "dead": dead,
                "residential": residential,
                "rotation_mode": self.rotation_mode,
                "healthy": available >= self.min_proxies_required,
            }

    async def refresh_cooldowns(self):
        now = time.time()
        async with self._lock:
            for addr, info in self._proxies.items():
                if info.status == ProxyStatus.COOLDOWN and info.cooldown_until <= now:
                    info.status = ProxyStatus.ACTIVE
                    info.fail_count = 0
                    if addr not in self._available:
                        self._available.append(addr)

    # ─── internal ───────────────────────────────────────────────────

    def _get_round_robin(self) -> Optional[str]:
        if not self._available:
            return None
        self._round_robin_index = self._round_robin_index % len(self._available)
        selected = self._available[self._round_robin_index]
        self._round_robin_index += 1
        return selected

    def _get_weighted(self, prefer_fresh: bool = False) -> Optional[str]:
        if not self._available:
            return None

        weights = []
        for addr in self._available:
            info = self._proxies.get(addr)
            if not info:
                weights.append(1)
                continue

            w = max(1, info.success_count + 1)
            if self.prefer_residential and info.is_residential:
                w *= 3
            if prefer_fresh and info.status == ProxyStatus.FRESH:
                w *= 2
            if info.instagram_blocked:
                w = 0
            weights.append(w)

        total = sum(weights)
        if total == 0:
            return random.choice(self._available) if self._available else None

        return random.choices(self._available, weights=weights, k=1)[0]

    def _find_proxy(self, proxy_str: str) -> Optional[ProxyInfo]:
        clean = proxy_str
        if "://" in clean:
            clean = clean.split("://", 1)[1]
        if clean in self._proxies:
            return self._proxies[clean]
        for addr, info in self._proxies.items():
            if clean in addr or addr in clean:
                return info
        return None

    def _parse_proxy_string(self, raw: str) -> Optional[ProxyInfo]:
        raw = raw.strip()
        if not raw:
            return None
        protocol = "socks5"
        address = raw
        if "://" in raw:
            protocol, address = raw.split("://", 1)
        if ":" not in address:
            return None
        return ProxyInfo(address=address, protocol=protocol)

    def _rebuild_available_list(self):
        self._available = [
            addr for addr, info in self._proxies.items()
            if info.is_available
        ]
        if self._available:
            random.shuffle(self._available)

    async def _health_check_loop(self):
        while True:
            await asyncio.sleep(self.health_check_interval)
            await self.refresh_cooldowns()
            await self._test_dead_proxies()

    async def _test_dead_proxies(self):
        dead = [(a, i) for a, i in self._proxies.items() if i.status == ProxyStatus.DEAD]
        if not dead:
            return
        logger.debug("[proxy] testing %d dead proxies...", len(dead))
        for addr, info in dead:
            if await self._tcp_ping(info):
                async with self._lock:
                    info.status = ProxyStatus.ACTIVE
                    info.fail_count = 0
                    info.instagram_blocked = False
                    if addr not in self._available:
                        self._available.append(addr)
                logger.info("[proxy] %s resurrected", _mask_addr(addr))

    async def _tcp_ping(self, info: ProxyInfo) -> bool:
        try:
            host, port_str = info.address.rsplit(":", 1)
            port = int(port_str)
            if "@" in host:
                host = host.split("@", 1)[1]
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.health_check_timeout,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    @property
    def available_count(self) -> int:
        return len(self._available)

    @property
    def total_count(self) -> int:
        return len(self._proxies)


def _mask_addr(address: str) -> str:
    if "@" in address:
        return address.split("@")[-1]
    return address