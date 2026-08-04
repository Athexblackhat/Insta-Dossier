"""
profile scraper — instagram public data extraction
endpoints: ?__a=1 JSON, mobile API fallback, web scraping fallback
extracts: full_name, bio, followers, following, posts, business info,
          profile pic, external url, verification status, account age
"""

import asyncio
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ProfileData:
    """complete instagram profile data extracted from public sources"""

    # identity
    username: str
    user_id: str = ""
    full_name: str = ""
    biography: str = ""
    bio_links: list[str] = field(default_factory=list)

    # stats
    follower_count: int = 0
    following_count: int = 0
    media_count: int = 0
    igtv_count: int = 0
    highlight_count: int = 0

    # account type
    is_private: bool = False
    is_verified: bool = False
    is_business: bool = False
    is_professional: bool = False
    business_category: str = ""
    account_type: str = ""  # 1=personal, 2=business, 3=creator

    # business contact (goldmine if available)
    business_email: str = ""
    business_phone: str = ""
    business_address: str = ""
    business_contact_method: str = ""  # EMAIL, PHONE, CALL, TEXT

    # linked
    external_url: str = ""
    connected_fb_page: str = ""
    connected_fb_page_id: str = ""

    # profile picture
    profile_pic_url: str = ""
    profile_pic_url_hd: str = ""
    profile_pic_hash: str = ""
    profile_pic_downloaded: bool = False
    profile_pic_path: str = ""

    # metadata
    category: str = ""
    pronouns: list[str] = field(default_factory=list)
    location_tag: str = ""  # from bio or tagged location
    account_created_approx: str = ""  # estimated from first post
    last_post_date: str = ""
    region: str = ""  # detected from language / phone prefix hints

    # raw
    raw_json: dict = field(default_factory=dict)
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source_endpoint: str = ""


class ProfileScraper:
    """
    instagram profile scraper — extracts public profile data

    usage:
        scraper = ProfileScraper(proxy_rotator=rotator, session_manager=sessions)
        profile = await scraper.scrape("john_doe_")
        # profile.business_email -> "john@company.com" (if business account)
        # profile.full_name -> "John Doe"
    """

    # primary endpoint — most data, but increasingly login-walled
    PRIMARY_ENDPOINT = "https://www.instagram.com/{username}/?__a=1&__d=1"

    # fallback — mobile API, different structure, often works when primary is walled
    MOBILE_API_ENDPOINT = "https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"

    # graphql fallback — requires specific headers
    GRAPHQL_ENDPOINT = "https://www.instagram.com/api/graphql"

    # csrf token needed for some endpoints
    CSRF_ENDPOINT = "https://www.instagram.com/accounts/login/"

    def __init__(
        self,
        proxy_rotator=None,       # ProxyRotator instance
        session_manager=None,     # SessionManager instance
        fingerprint_engine=None,  # FingerprintEngine instance
        output_dir: str = "output",
        download_images: bool = True,
        max_retries: int = 3,
        timeout: int = 15,
        use_mobile_api_fallback: bool = True,
        use_web_scrape_fallback: bool = False,  # expensive, use as last resort
    ):
        self.proxy_rotator = proxy_rotator
        self.session_manager = session_manager
        self.fingerprint_engine = fingerprint_engine
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.download_images = download_images
        self.max_retries = max_retries
        self.timeout = timeout
        self.use_mobile_api_fallback = use_mobile_api_fallback
        self.use_web_scrape_fallback = use_web_scrape_fallback

        self._http_session: Optional[aiohttp.ClientSession] = None
        self._csrf_token: Optional[str] = None
        self._csrf_token_ts: float = 0.0

        # ensure dirs exist
        if self.download_images:
            self.images_dir.mkdir(parents=True, exist_ok=True)

    async def _get_http(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers=self._build_default_headers(),
            )
        return self._http_session

    async def close(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    # ─── main scraping methods ─────────────────────────────────────

    async def scrape(self, username: str) -> ProfileData:
        """
        scrape all available public data for an instagram profile
        tries multiple endpoints in order until successful
        """
        username = self._clean_username(username)

        logger.info("[scraper] target: @%s — starting extraction", username)

        # try primary endpoint first
        for attempt in range(1, self.max_retries + 1):
            try:
                data = await self._try_primary_endpoint(username)
                if data:
                    profile = self._parse_primary_response(username, data)
                    profile.scraped_at = datetime.utcnow().isoformat()
                    profile.source_endpoint = "primary_json"

                    # download profile picture
                    if self.download_images and profile.profile_pic_url_hd:
                        profile.profile_pic_path = await self._download_image(
                            profile.profile_pic_url_hd,
                            username,
                        )
                        if profile.profile_pic_path:
                            profile.profile_pic_downloaded = True

                    logger.info(
                        "[scraper] @%s — extracted | name:%s followers:%s business:%s email:%s",
                        username,
                        profile.full_name,
                        profile.follower_count,
                        profile.is_business,
                        bool(profile.business_email),
                    )
                    return profile

            except asyncio.TimeoutError:
                logger.warning("[scraper] timeout on primary endpoint — attempt %d", attempt)
            except aiohttp.ClientError as e:
                logger.warning("[scraper] network error: %s — attempt %d", e, attempt)
            except Exception as e:
                logger.error("[scraper] unexpected error: %s", e)

            if attempt < self.max_retries:
                await asyncio.sleep(1.5 ** attempt)

        # primary failed — try mobile API
        if self.use_mobile_api_fallback:
            logger.info("[scraper] primary failed — trying mobile API")
            try:
                data = await self._try_mobile_api(username)
                if data:
                    profile = self._parse_mobile_response(username, data)
                    profile.scraped_at = datetime.utcnow().isoformat()
                    profile.source_endpoint = "mobile_api"

                    if self.download_images and profile.profile_pic_url_hd:
                        profile.profile_pic_path = await self._download_image(
                            profile.profile_pic_url_hd,
                            username,
                        )
                        if profile.profile_pic_path:
                            profile.profile_pic_downloaded = True

                    logger.info("[scraper] @%s — extracted via mobile API", username)
                    return profile
            except Exception as e:
                logger.error("[scraper] mobile API failed: %s", e)

        # web scrape fallback — expensive, last resort
        if self.use_web_scrape_fallback:
            logger.info("[scraper] trying web scrape fallback...")
            try:
                profile = await self._try_web_scrape(username)
                if profile:
                    return profile
            except Exception as e:
                logger.error("[scraper] web scrape failed: %s", e)

        # absolute failure — return minimal profile
        logger.error("[scraper] all endpoints failed for @%s", username)
        return ProfileData(username=username, scraped_at=datetime.utcnow().isoformat())

    async def scrape_batch(self, usernames: list[str], max_concurrent: int = 5) -> list[ProfileData]:
        """scrape multiple profiles concurrently"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _scrape_one(user: str) -> ProfileData:
            async with semaphore:
                return await self.scrape(user)

        tasks = [_scrape_one(u) for u in usernames]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        profiles = []
        for i, result in enumerate(results):
            if isinstance(result, ProfileData):
                profiles.append(result)
            else:
                logger.error("[scraper] batch [%d] %s failed: %s", i, usernames[i], result)
                profiles.append(ProfileData(username=usernames[i]))

        return profiles

    # ─── endpoint implementations ──────────────────────────────────

    async def _try_primary_endpoint(self, username: str) -> Optional[dict]:
        """try the public ?__a=1 JSON endpoint"""
        proxy = await self._get_proxy()
        proxy_url = self._format_proxy(proxy) if proxy else None

        headers = self._build_browser_headers()
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["X-IG-App-ID"] = "936619743392459"  # instagram web app ID
        headers["X-ASBD-ID"] = "198387"
        headers["X-IG-WWW-Claim"] = "0"

        http = await self._get_http()
        url = self.PRIMARY_ENDPOINT.format(username=username)

        async with http.get(
            url,
            proxy=proxy_url,
            headers=headers,
            allow_redirects=True,
        ) as resp:
            if resp.status == 200:
                raw = await resp.json()
                if raw and isinstance(raw, dict) and "graphql" in raw:
                    return raw["graphql"].get("user")
                if raw and isinstance(raw, dict) and "logging_page_id" in raw:
                    # sometimes the response is wrapped differently
                    return raw

            if resp.status == 429:
                if self.proxy_rotator and proxy:
                    await self.proxy_rotator.report_failure(proxy, rate_limited=True)
                logger.warning("[scraper] rate limited on primary endpoint")
                return None

            if resp.status in (302, 303, 401, 403):
                # login wall — instagram is blocking unauthenticated access
                logger.warning("[scraper] login wall — status %d", resp.status)
                return None

            logger.debug("[scraper] primary endpoint returned %d", resp.status)
            return None

    async def _try_mobile_api(self, username: str) -> Optional[dict]:
        """try instagram's mobile API endpoint — often bypasses login wall"""
        proxy = await self._get_proxy()
        proxy_url = self._format_proxy(proxy) if proxy else None

        headers = self._build_mobile_headers()

        http = await self._get_http()
        url = self.MOBILE_API_ENDPOINT.format(username=username)

        # mobile API sometimes needs a csrf token
        csrf = await self._get_csrf_token()

        async with http.get(
            url,
            proxy=proxy_url,
            headers=headers,
            allow_redirects=True,
        ) as resp:
            if resp.status == 200:
                raw = await resp.json()
                if raw and isinstance(raw, dict):
                    user_data = raw.get("data", {}).get("user")
                    if user_data:
                        return user_data

            if resp.status == 429:
                if self.proxy_rotator and proxy:
                    await self.proxy_rotator.report_failure(proxy, rate_limited=True)
                return None

            logger.debug("[scraper] mobile API returned %d", resp.status)
            return None

    async def _try_web_scrape(self, username: str) -> Optional[ProfileData]:
        """
        last resort — scrape the HTML profile page directly
        instagram embeds JSON-LD and meta tags with profile data
        """
        proxy = await self._get_proxy()
        proxy_url = self._format_proxy(proxy) if proxy else None

        headers = self._build_browser_headers()
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

        http = await self._get_http()
        url = f"https://www.instagram.com/{username}/"

        async with http.get(url, proxy=proxy_url, headers=headers) as resp:
            if resp.status != 200:
                return None

            html = await resp.text()

            # extract JSON-LD embedded data
            json_ld = re.search(
                r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
                html,
                re.DOTALL,
            )
            if json_ld:
                try:
                    ld_data = json.loads(json_ld.group(1))
                    profile = ProfileData(username=username)
                    profile.full_name = ld_data.get("name", "")
                    profile.biography = ld_data.get("description", "")
                    profile.profile_pic_url = ld_data.get("image", "")
                    profile.source_endpoint = "web_scrape_jsonld"
                    profile.scraped_at = datetime.utcnow().isoformat()
                    return profile
                except json.JSONDecodeError:
                    pass

            # extract from meta tags
            followers_match = re.search(r'"edge_followed_by"\s*:\s*\{[^}]*"count"\s*:\s*(\d+)', html)
            if followers_match:
                profile = ProfileData(username=username)
                profile.follower_count = int(followers_match.group(1))
                profile.source_endpoint = "web_scrape_meta"
                profile.scraped_at = datetime.utcnow().isoformat()

                full_name_match = re.search(r'"full_name"\s*:\s*"([^"]*)"', html)
                if full_name_match:
                    profile.full_name = full_name_match.group(1)

                bio_match = re.search(r'"biography"\s*:\s*"([^"]*)"', html)
                if bio_match:
                    profile.biography = bio_match.group(1)

                return profile

        return None

    # ─── response parsers ──────────────────────────────────────────

    def _parse_primary_response(self, username: str, data: dict) -> ProfileData:
        """parse the primary ?__a=1 JSON response"""
        profile = ProfileData(username=username)
        profile.raw_json = data

        # basic identity
        profile.user_id = str(data.get("id", ""))
        profile.full_name = data.get("full_name", "")
        profile.biography = data.get("biography", "")
        profile.is_private = data.get("is_private", False)
        profile.is_verified = data.get("is_verified", False)
        profile.is_business = data.get("is_business_account", False)
        profile.is_professional = data.get("is_professional_account", False)
        profile.business_category = data.get("business_category_name", "")
        profile.account_type = str(data.get("account_type", ""))

        # stats
        profile.follower_count = data.get("edge_followed_by", {}).get("count", 0)
        profile.following_count = data.get("edge_follow", {}).get("count", 0)
        profile.media_count = data.get("edge_owner_to_timeline_media", {}).get("count", 0)

        # business contact — the goldmine
        profile.business_email = data.get("business_email", "")
        profile.business_phone = data.get("business_phone_number", "")
        profile.business_contact_method = data.get("business_contact_method", "")

        business_address = data.get("business_address_json", "")
        if business_address:
            try:
                addr = json.loads(business_address)
                profile.business_address = addr.get("street_address", "")
            except (json.JSONDecodeError, TypeError):
                profile.business_address = str(business_address)

        # linked fb
        fb_data = data.get("connected_fb_page")
        if fb_data:
            profile.connected_fb_page = fb_data.get("name", "")
            profile.connected_fb_page_id = str(fb_data.get("id", ""))

        # external link
        profile.external_url = data.get("external_url", "")

        # bio links (multiple links in bio)
        bio_links_data = data.get("bio_links", [])
        for link in bio_links_data:
            if isinstance(link, dict):
                profile.bio_links.append(link.get("url", ""))
            elif isinstance(link, str):
                profile.bio_links.append(link)

        # profile picture
        profile.profile_pic_url = data.get("profile_pic_url", "")
        profile.profile_pic_url_hd = data.get("profile_pic_url_hd", "")

        if profile.profile_pic_url_hd:
            profile.profile_pic_hash = hashlib.md5(
                profile.profile_pic_url_hd.encode()
            ).hexdigest()[:16]

        # category
        profile.category = data.get("category_name", data.get("category", ""))

        # pronouns
        pronouns_data = data.get("pronouns", [])
        if isinstance(pronouns_data, list):
            profile.pronouns = pronouns_data
        elif isinstance(pronouns_data, str):
            profile.pronouns = [pronouns_data]

        # approximate account age from first media
        media_nodes = (
            data.get("edge_owner_to_timeline_media", {})
            .get("edges", [])
        )
        if media_nodes:
            last_post_node = media_nodes[0].get("node", {})
            profile.last_post_date = self._parse_timestamp(
                last_post_node.get("taken_at_timestamp", 0)
            )

            # first post gives approximate creation date
            if len(media_nodes) > 10:
                first_post_node = media_nodes[-1].get("node", {})
                profile.account_created_approx = self._parse_timestamp(
                    first_post_node.get("taken_at_timestamp", 0)
                )

        return profile

    def _parse_mobile_response(self, username: str, data: dict) -> ProfileData:
        """parse the mobile API response"""
        profile = ProfileData(username=username)
        profile.raw_json = data

        profile.user_id = str(data.get("pk", data.get("id", "")))
        profile.full_name = data.get("full_name", "")
        profile.biography = data.get("biography", "")
        profile.is_private = data.get("is_private", False)
        profile.is_verified = data.get("is_verified", False)
        profile.is_business = data.get("is_business", False)
        profile.is_professional = data.get("is_professional_account", False)
        profile.business_category = data.get("category", "")
        profile.account_type = str(data.get("account_type", ""))

        profile.follower_count = data.get("follower_count", 0)
        profile.following_count = data.get("following_count", 0)
        profile.media_count = data.get("media_count", 0)

        profile.business_email = data.get("business_email", "")
        profile.business_phone = data.get("business_contact_number", "")
        profile.business_contact_method = data.get("contact_phone_number", "")

        profile.external_url = data.get("external_url", "")
        profile.connected_fb_page = data.get("connected_fb_page", "")

        profile.profile_pic_url = data.get("profile_pic_url", "")
        profile.profile_pic_url_hd = data.get("hd_profile_pic_url_info", {}).get("url", "")
        if not profile.profile_pic_url_hd:
            profile.profile_pic_url_hd = data.get("hd_profile_pic_versions", [{}])[0].get("url", "")

        profile.source_endpoint = "mobile_api"

        return profile

    # ─── helpers ───────────────────────────────────────────────────

    async def _download_image(self, url: str, username: str) -> str:
        """download profile picture and return local path"""
        if not url:
            return ""

        safe_username = re.sub(r'[^a-zA-Z0-9_-]', '_', username)
        filename = f"{safe_username}_profile_pic.jpg"
        filepath = self.images_dir / filename

        try:
            http = await self._get_http()
            async with http.get(url) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    with open(filepath, "wb") as f:
                        f.write(content)
                    logger.debug("[scraper] image downloaded: %s (%d bytes)", filename, len(content))
                    return str(filepath)
        except Exception as e:
            logger.debug("[scraper] image download failed: %s", e)

        return ""

    async def _get_csrf_token(self) -> Optional[str]:
        """fetch a fresh CSRF token from instagram"""
        now = time.time()
        if self._csrf_token and (now - self._csrf_token_ts) < 300:
            return self._csrf_token

        try:
            http = await self._get_http()
            async with http.get(self.CSRF_ENDPOINT) as resp:
                cookies = resp.cookies
                for cookie in cookies.values():
                    if cookie.key == "csrftoken":
                        self._csrf_token = cookie.value
                        self._csrf_token_ts = now
                        return self._csrf_token

                # fallback — extract from set-cookie header
                for header in resp.headers.getall("Set-Cookie", []):
                    match = re.search(r"csrftoken=([^;]+)", header)
                    if match:
                        self._csrf_token = match.group(1)
                        self._csrf_token_ts = now
                        return self._csrf_token
        except Exception:
            pass

        return None

    async def _get_proxy(self) -> Optional[str]:
        if self.proxy_rotator:
            return await self.proxy_rotator.get_proxy()
        return None

    def _format_proxy(self, proxy: str) -> Optional[str]:
        if not proxy:
            return None
        if proxy.startswith(("http://", "socks5://", "socks4://")):
            return proxy
        return f"socks5://{proxy}"

    def _build_default_headers(self) -> dict:
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def _build_browser_headers(self) -> dict:
        """headers that mimic a real chrome browser"""
        headers = self._build_default_headers()
        headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )
        headers["Referer"] = "https://www.instagram.com/"
        headers["Origin"] = "https://www.instagram.com"
        return headers

    def _build_mobile_headers(self) -> dict:
        """headers that mimic the instagram mobile app"""
        return {
            "User-Agent": (
                "Instagram 275.0.0.26.98 Android "
                "(30/11; 420dpi; 1080x2340; samsung; SM-G998B; "
                "x1s; exynos2100; en_US; 375763484)"
            ),
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "X-IG-App-ID": "567067343352427",
            "X-IG-Device-ID": self._generate_device_id(),
            "X-IG-Android-ID": self._generate_android_id(),
            "X-IG-Connection-Type": "WIFI",
            "X-IG-Capabilities": "3brTvwE=",
            "X-IG-App-Locale": "en_US",
            "X-IG-Bandwidth-Speed-KBPS": f"{random.randint(5000, 15000)}.{random.randint(100, 999)}",
        }

    def _generate_device_id(self) -> str:
        """generate a random android device ID"""
        return f"android-{''.join(random.choices('0123456789abcdef', k=16))}"

    def _generate_android_id(self) -> str:
        """generate a random android advertising ID"""
        return f"{''.join(random.choices('0123456789abcdef', k=8))}-{''.join(random.choices('0123456789abcdef', k=4))}-{''.join(random.choices('0123456789abcdef', k=4))}-{''.join(random.choices('0123456789abcdef', k=4))}-{''.join(random.choices('0123456789abcdef', k=12))}"

    def _parse_timestamp(self, ts: int) -> str:
        """convert unix timestamp to ISO date string"""
        if ts and ts > 0:
            return datetime.utcfromtimestamp(ts).isoformat()
        return ""

    @staticmethod
    def _clean_username(username: str) -> str:
        """strip @ and URL parts from username"""
        username = username.strip()
        if username.startswith("@"):
            username = username[1:]
        if "instagram.com/" in username:
            parsed = urlparse(username if "://" in username else f"https://{username}")
            path_parts = parsed.path.strip("/").split("/")
            if path_parts:
                username = path_parts[0]
        return username.strip("/").strip()

    @property
    def images_downloaded(self) -> int:
        """count of downloaded images"""
        if self.images_dir.exists():
            return len(list(self.images_dir.glob("*.jpg")))
        return 0