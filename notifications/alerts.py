"""
alert manager — telegram + discord notifications for insta_dossier
sends: dossier complete, phase updates, errors, pool warnings
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class Alert:
    level: AlertLevel
    title: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().strftime("%H:%M:%S UTC"))
    metadata: Optional[dict] = None

    def format_telegram(self) -> str:
        emoji_map = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.SUCCESS: "✅",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "🚨",
            AlertLevel.DEBUG: "🔍",
        }
        emoji = emoji_map.get(self.level, "📢")
        text = f"{emoji} <b>{self.title}</b>\n<i>{self.timestamp}</i>\n\n{self.message}"
        if self.metadata:
            text += "\n\n<pre>"
            for key, value in self.metadata.items():
                text += f"{key}: {value}\n"
            text += "</pre>"
        return text

    def format_discord(self) -> dict:
        color_map = {
            AlertLevel.INFO: 3447003,
            AlertLevel.SUCCESS: 5763719,
            AlertLevel.WARNING: 16705372,
            AlertLevel.ERROR: 15548997,
            AlertLevel.DEBUG: 10197915,
        }
        embed = {
            "title": self.title,
            "description": self.message,
            "color": color_map.get(self.level, 3447003),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"insta_dossier • {self.timestamp}"},
        }
        if self.metadata:
            embed["fields"] = [
                {"name": k, "value": str(v), "inline": True}
                for k, v in list(self.metadata.items())[:6]
            ]
        return {"embeds": [embed]}


class AlertManager:
    """
    dispatches alerts to telegram and/or discord

    usage:
        alerts = AlertManager(
            telegram_bot_token="123:abc",
            telegram_chat_id="-100xxx",
            discord_webhook_url="https://discord.com/api/webhooks/...",
        )
        await alerts.start()
        await alerts.dossier_complete("john_doe_", "output/dossiers/john_doe_.json")
    """

    TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(
        self,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        discord_webhook_url: Optional[str] = None,
        debug_mode: bool = False,
        max_queue_size: int = 100,
    ):
        self.telegram_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.discord_url = discord_webhook_url
        self.debug_mode = debug_mode

        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._telegram_last_sent: float = 0.0
        self._telegram_lock = asyncio.Lock()
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self._running = True
        self._worker_task = asyncio.create_task(self._dispatch_loop())
        logger.info("[alerts] started — telegram:%s discord:%s", bool(self.telegram_token), bool(self.discord_url))

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        while not self._queue.empty():
            try:
                await self._dispatch_alert(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    async def send(self, alert: Alert):
        if not self._running:
            return
        if alert.level == AlertLevel.DEBUG and not self.debug_mode:
            return
        try:
            self._queue.put_nowait(alert)
        except asyncio.QueueFull:
            logger.warning("[alerts] queue full — dropping alert: %s", alert.title)

    # ─── convenience methods ────────────────────────────────────────

    async def dossier_complete(self, target: str, filepath: str, summary: dict = None):
        """notify that a dossier has been completed"""
        await self.send(Alert(
            level=AlertLevel.SUCCESS,
            title=f"📄 Dossier Complete: @{target}",
            message=f"Dossier for <b>@{target}</b> has been generated.\nSaved to: <code>{filepath}</code>",
            metadata=summary or {},
        ))

    async def phase_started(self, target: str, phase: str, phase_num: int, total_phases: int):
        """notify that a phase has started (debug only)"""
        await self.send(Alert(
            level=AlertLevel.DEBUG,
            title=f"Phase {phase_num}/{total_phases}: {phase}",
            message=f"Starting <b>{phase}</b> for @{target}...",
            metadata={"target": target, "phase": phase},
        ))

    async def extraction_complete(self, target: str, data_points: int, risk_level: str):
        """notify extraction summary"""
        emoji = "🟢" if risk_level == "LOW" else "🟡" if risk_level == "MEDIUM" else "🔴"
        await self.send(Alert(
            level=AlertLevel.INFO,
            title=f"{emoji} Extraction: @{target}",
            message=(
                f"Extracted <b>{data_points}</b> data points from @{target}.\n"
                f"Privacy risk: <b>{risk_level}</b>"
            ),
            metadata={"data_points": str(data_points), "risk": risk_level},
        ))

    async def business_email_found(self, target: str, email: str):
        """alert when business email is discovered"""
        await self.send(Alert(
            level=AlertLevel.SUCCESS,
            title=f"📧 Business Email Found: @{target}",
            message=f"Unmasked business email discovered:\n<code>{email}</code>",
            metadata={"target": target, "email": email},
        ))

    async def linked_platforms_found(self, target: str, count: int, platforms: list[str]):
        """alert when cross-platform links are mapped"""
        await self.send(Alert(
            level=AlertLevel.INFO,
            title=f"🔗 Platforms Mapped: @{target}",
            message=f"Found <b>{count}</b> linked platforms: {', '.join(platforms[:8])}",
            metadata={"count": str(count), "platforms": ", ".join(platforms)},
        ))

    async def identity_reconstructed(self, target: str, best_email: str, confidence: float):
        """alert when identity is successfully reconstructed"""
        await self.send(Alert(
            level=AlertLevel.SUCCESS if confidence >= 0.7 else AlertLevel.INFO,
            title=f"🔓 Identity Reconstructed: @{target}",
            message=(
                f"Best email candidate: <code>{best_email}</code>\n"
                f"Confidence: <b>{confidence:.0%}</b>"
            ),
            metadata={"email": best_email, "confidence": f"{confidence:.0%}"},
        ))

    async def proxy_pool_health(self, stats: dict):
        """send proxy pool health report"""
        is_healthy = stats.get("healthy", True)
        level = AlertLevel.INFO if is_healthy else AlertLevel.WARNING
        await self.send(Alert(
            level=level,
            title=f"Proxy Pool: {'Healthy' if is_healthy else 'LOW'}",
            message=(
                f"Available: <b>{stats.get('available', 0)}</b> / {stats.get('total', 0)}\n"
                f"Active: {stats.get('active', 0)} | Cooldown: {stats.get('cooldown', 0)} | Dead: {stats.get('dead', 0)}\n"
                f"Residential: {stats.get('residential', 0)}"
            ),
            metadata=stats,
        ))

    async def error_alert(self, title: str, message: str, metadata: dict = None):
        """send critical error alert"""
        await self.send(Alert(
            level=AlertLevel.ERROR,
            title=title,
            message=message,
            metadata=metadata,
        ))

    async def batch_summary(self, total: int, completed: int, failed: int, duration: float):
        """summary after batch processing"""
        await self.send(Alert(
            level=AlertLevel.INFO,
            title=f"Batch Complete: {completed}/{total}",
            message=(
                f"Processed <b>{total}</b> targets in {duration:.1f}s\n"
                f"✅ {completed} completed | ❌ {failed} failed"
            ),
            metadata={"total": str(total), "completed": str(completed), "failed": str(failed), "duration": f"{duration:.1f}s"},
        ))

    # ─── internal dispatch ──────────────────────────────────────────

    async def _dispatch_loop(self):
        while self._running:
            try:
                alert = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._dispatch_alert(alert)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[alerts] dispatch error: %s", e)

    async def _dispatch_alert(self, alert: Alert):
        tasks = []
        if self.telegram_token and self.telegram_chat_id:
            tasks.append(self._send_telegram(alert))
        if self.discord_url:
            tasks.append(self._send_discord(alert))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_telegram(self, alert: Alert):
        async with self._telegram_lock:
            now = asyncio.get_event_loop().time()
            time_since = now - self._telegram_last_sent
            if time_since < 3.0:
                await asyncio.sleep(3.0 - time_since)

            url = self.TELEGRAM_API.format(token=self.telegram_token)
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": alert.format_telegram(),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            try:
                async with self._http_session.post(url, json=payload) as resp:
                    self._telegram_last_sent = asyncio.get_event_loop().time()
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("[alerts] telegram failed (%d): %s", resp.status, body[:200])
            except Exception as e:
                logger.error("[alerts] telegram error: %s", e)

    async def _send_discord(self, alert: Alert):
        try:
            async with self._http_session.post(
                self.discord_url,
                json=alert.format_discord(),
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status not in (200, 204):
                    body = await resp.text()
                    logger.error("[alerts] discord failed (%d): %s", resp.status, body[:200])
        except Exception as e:
            logger.error("[alerts] discord error: %s", e)