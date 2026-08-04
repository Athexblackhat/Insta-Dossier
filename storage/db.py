"""
database — async sqlite3 wrapper for insta_dossier
tables: targets, dossiers, extraction_log
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Database:
    """
    async sqlite3 database for instagram OSINT persistence

    usage:
        db = Database("output/insta_dossier.db")
        await db.initialize()
        await db.save_target(username, profile_data)
        await db.save_dossier(dossier)
    """

    SCHEMA = """
    -- targets (unique instagram accounts investigated)
    CREATE TABLE IF NOT EXISTS targets (
        username TEXT PRIMARY KEY,
        user_id TEXT,
        full_name TEXT,
        is_business INTEGER DEFAULT 0,
        is_verified INTEGER DEFAULT 0,
        follower_count INTEGER DEFAULT 0,
        following_count INTEGER DEFAULT 0,
        media_count INTEGER DEFAULT 0,
        business_email TEXT,
        business_phone TEXT,
        masked_email TEXT,
        masked_phone TEXT,
        linked_platforms_count INTEGER DEFAULT 0,
        privacy_risk TEXT,
        osint_value TEXT,
        data_points_collected INTEGER DEFAULT 0,
        first_seen_at TEXT,
        last_scraped_at TEXT,
        times_scraped INTEGER DEFAULT 1
    );

    -- dossiers (full extraction outputs)
    CREATE TABLE IF NOT EXISTS dossiers (
        dossier_id TEXT PRIMARY KEY,
        username TEXT,
        filepath TEXT,
        file_size_bytes INTEGER,
        risk_level TEXT,
        emails_found INTEGER DEFAULT 0,
        phones_found INTEGER DEFAULT 0,
        platforms_found INTEGER DEFAULT 0,
        identity_reconstructed INTEGER DEFAULT 0,
        generated_at TEXT,
        FOREIGN KEY (username) REFERENCES targets(username)
    );

    -- extraction log (individual phase results)
    CREATE TABLE IF NOT EXISTS extraction_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        dossier_id TEXT,
        phase TEXT,
        status TEXT,
        data_found TEXT,
        duration_ms REAL,
        error TEXT,
        proxy_used TEXT,
        logged_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (username) REFERENCES targets(username)
    );

    -- indexes
    CREATE INDEX IF NOT EXISTS idx_targets_username ON targets(username);
    CREATE INDEX IF NOT EXISTS idx_targets_risk ON targets(privacy_risk);
    CREATE INDEX IF NOT EXISTS idx_dossiers_username ON dossiers(username);
    CREATE INDEX IF NOT EXISTS idx_dossiers_generated ON dossiers(generated_at);
    CREATE INDEX IF NOT EXISTS idx_extraction_log_username ON extraction_log(username);
    """

    def __init__(self, db_path: str = "output/insta_dossier.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        async with self._lock:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.executescript(self.SCHEMA)
            self._conn.commit()
            logger.info("[db] initialized at %s", self.db_path)

    async def close(self):
        async with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ─── targets ───────────────────────────────────────────────────

    async def save_target(self, username: str, profile_data: dict = None) -> bool:
        """insert or update a target record"""
        async with self._lock:
            existing = self._conn.execute(
                "SELECT times_scraped FROM targets WHERE username = ?", (username,)
            ).fetchone()

            now = datetime.utcnow().isoformat()

            if existing:
                times = existing[0] + 1
                self._conn.execute(
                    """UPDATE targets SET
                       full_name = COALESCE(?, full_name),
                       follower_count = COALESCE(?, follower_count),
                       last_scraped_at = ?,
                       times_scraped = ?
                       WHERE username = ?""",
                    (
                        profile_data.get("full_name") if profile_data else None,
                        profile_data.get("follower_count") if profile_data else None,
                        now,
                        times,
                        username,
                    ),
                )
            else:
                p = profile_data or {}
                self._conn.execute(
                    """INSERT INTO targets
                       (username, user_id, full_name, is_business, is_verified,
                        follower_count, following_count, media_count,
                        business_email, business_phone, first_seen_at, last_scraped_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        username,
                        p.get("user_id", ""),
                        p.get("full_name", ""),
                        1 if p.get("is_business") else 0,
                        1 if p.get("is_verified") else 0,
                        p.get("follower_count", 0),
                        p.get("following_count", 0),
                        p.get("media_count", 0),
                        p.get("business_email", ""),
                        p.get("business_phone", ""),
                        now, now,
                    ),
                )
            self._conn.commit()
            return True

    async def update_target_osint(self, username: str, **kwargs):
        """update OSINT-specific fields after extraction"""
        if not kwargs:
            return
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [username]
        async with self._lock:
            self._conn.execute(
                f"UPDATE targets SET {set_clause}, last_scraped_at = ? WHERE username = ?",
                values[:-1] + [datetime.utcnow().isoformat(), username],
            )
            self._conn.commit()

    async def get_target(self, username: str) -> Optional[dict]:
        """get a single target record"""
        async with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM targets WHERE username = ?", (username,)
            )
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
        return None

    async def get_all_targets(self, limit: int = 50) -> list[dict]:
        """get recent targets"""
        async with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM targets ORDER BY last_scraped_at DESC LIMIT ?", (limit,)
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    async def search_targets(self, query: str) -> list[dict]:
        """search targets by username or full_name"""
        async with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM targets WHERE username LIKE ? OR full_name LIKE ? LIMIT 20",
                (f"%{query}%", f"%{query}%"),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ─── dossiers ──────────────────────────────────────────────────

    async def save_dossier(self, dossier_id: str, username: str, filepath: str,
                           file_size: int = 0, risk_level: str = "",
                           emails: int = 0, phones: int = 0, platforms: int = 0,
                           identity_reconstructed: bool = False):
        """record a generated dossier"""
        async with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO dossiers
                   (dossier_id, username, filepath, file_size_bytes, risk_level,
                    emails_found, phones_found, platforms_found, identity_reconstructed, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dossier_id, username, filepath, file_size, risk_level,
                    emails, phones, platforms, 1 if identity_reconstructed else 0,
                    datetime.utcnow().isoformat(),
                ),
            )
            self._conn.commit()

    async def get_dossiers_for_target(self, username: str) -> list[dict]:
        """get all dossiers for a target"""
        async with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM dossiers WHERE username = ? ORDER BY generated_at DESC",
                (username,),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    async def get_recent_dossiers(self, limit: int = 10) -> list[dict]:
        """get most recent dossiers"""
        async with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM dossiers ORDER BY generated_at DESC LIMIT ?", (limit,)
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ─── extraction log ────────────────────────────────────────────

    async def log_extraction(self, username: str, dossier_id: str, phase: str,
                             status: str, data_found: str = "", duration_ms: float = 0,
                             error: str = "", proxy_used: str = ""):
        """log an extraction phase"""
        async with self._lock:
            self._conn.execute(
                """INSERT INTO extraction_log
                   (username, dossier_id, phase, status, data_found, duration_ms, error, proxy_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (username, dossier_id, phase, status, data_found, duration_ms, error, proxy_used),
            )
            self._conn.commit()

    async def get_extraction_log(self, username: str, limit: int = 20) -> list[dict]:
        """get extraction history for a target"""
        async with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM extraction_log WHERE username = ? ORDER BY logged_at DESC LIMIT ?",
                (username, limit),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ─── stats ─────────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        """get overall tool statistics"""
        async with self._lock:
            total_targets = self._conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
            total_dossiers = self._conn.execute("SELECT COUNT(*) FROM dossiers").fetchone()[0]
            total_extractions = self._conn.execute("SELECT COUNT(*) FROM extraction_log").fetchone()[0]

            high_risk = self._conn.execute(
                "SELECT COUNT(*) FROM targets WHERE privacy_risk IN ('HIGH', 'CRITICAL')"
            ).fetchone()[0]

            business = self._conn.execute(
                "SELECT COUNT(*) FROM targets WHERE is_business = 1"
            ).fetchone()[0]

            emails_found = self._conn.execute(
                "SELECT SUM(emails_found) FROM dossiers"
            ).fetchone()[0] or 0

            platforms_mapped = self._conn.execute(
                "SELECT SUM(platforms_found) FROM dossiers"
            ).fetchone()[0] or 0

            return {
                "total_targets": total_targets,
                "total_dossiers": total_dossiers,
                "total_extractions": total_extractions,
                "high_risk_targets": high_risk,
                "business_accounts": business,
                "total_emails_discovered": emails_found,
                "total_platforms_mapped": platforms_mapped,
            }