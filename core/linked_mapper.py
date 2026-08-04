"""
linked mapper — cross-platform account discovery & verification
maps connections between instagram and 20+ other platforms
expands link aggregators (linktree, beacons, campsite, etc)
correlates identities across platforms
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class PlatformLink:
    """a single linked platform account"""
    platform: str                      # "twitter", "github", etc
    handle: str                        # "@johndoe" or "johndoe"
    url: str = ""                      # full profile URL
    confidence: float = 1.0            # 0.0 — 1.0 how confident we are
    source: str = ""                   # where we found it: "bio", "external_url", "linktree", etc
    verified: bool = False             # did we confirm the account exists?
    metadata: dict = field(default_factory=dict)  # extra platform-specific data


@dataclass
class LinkedAccounts:
    """complete cross-platform account mapping"""

    username: str
    platforms: list[PlatformLink] = field(default_factory=list)
    link_aggregators: list[dict] = field(default_factory=list)  # linktree, etc — with expanded links
    total_platforms_found: int = 0
    total_links_expanded: int = 0
    mapped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def get_by_platform(self, platform: str) -> list[PlatformLink]:
        return [p for p in self.platforms if p.platform == platform]

    def get_verified(self) -> list[PlatformLink]:
        return [p for p in self.platforms if p.verified]

    def to_flat_dict(self) -> dict:
        """export as flat dict for dossier"""
        result = {}
        for p in self.platforms:
            key = p.platform
            count = sum(1 for x in self.platforms if x.platform == p.platform and x != p)
            if count > 0:
                key = f"{p.platform}_{count}"
            result[key] = {
                "handle": p.handle,
                "url": p.url,
                "confidence": p.confidence,
                "verified": p.verified,
            }
        return result


class LinkedMapper:
    """
    cross-platform account discovery engine

    usage:
        mapper = LinkedMapper(proxy_rotator=rotator)
        linked = await mapper.map(
            username="john_doe_",
            bio_extracts=bio_parser_result,
            external_url="linktr.ee/johndoe",
            profile_data=profile_scraper_result,
        )
        # linked.platforms → [PlatformLink(platform="twitter", handle="@johndoe"), ...]
    """

    # known link aggregator domains
    LINK_AGGREGATORS = [
        "linktr.ee", "linktree.com", "linktr.ee",
        "beacons.ai", "beacons.page",
        "campsite.bio", "campsite.to",
        "bio.site", "bento.me",
        "lnk.bio", "lnk.to",
        "allmylinks.com", "allmylinks.co",
        "solo.to", "msha.ke",
        "hoo.be", "bio.link",
        "zaap.ai", "taplink.at",
        "direct.me", "linkin.bio",
        "flow.page", "snipfeed.co",
        "carrd.co", "about.me",
    ]

    # platform URL patterns for verification
    PLATFORM_URLS = {
        "twitter": "https://twitter.com/{handle}",
        "x": "https://x.com/{handle}",
        "facebook": "https://facebook.com/{handle}",
        "tiktok": "https://tiktok.com/@{handle}",
        "youtube": "https://youtube.com/@{handle}",
        "github": "https://github.com/{handle}",
        "linkedin": "https://linkedin.com/in/{handle}",
        "twitch": "https://twitch.tv/{handle}",
        "snapchat": "https://snapchat.com/add/{handle}",
        "telegram": "https://t.me/{handle}",
        "reddit": "https://reddit.com/user/{handle}",
        "pinterest": "https://pinterest.com/{handle}",
        "spotify": "https://open.spotify.com/user/{handle}",
        "medium": "https://medium.com/@{handle}",
    }

    def __init__(
        self,
        proxy_rotator=None,
        session_manager=None,
        verify_links: bool = True,
        expand_aggregators: bool = True,
        timeout: int = 10,
        max_concurrent_verifications: int = 5,
    ):
        self.proxy_rotator = proxy_rotator
        self.session_manager = session_manager
        self.verify_links = verify_links
        self.expand_aggregators = expand_aggregators
        self.timeout = timeout
        self.max_concurrent_verifications = max_concurrent_verifications

        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _get_http(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._http_session

    async def close(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    # ─── main mapping method ───────────────────────────────────────

    async def map(
        self,
        username: str,
        bio_extracts=None,        # BioExtracts from BioParser
        external_url: str = "",
        bio_links: list[str] = None,
        profile_data=None,        # ProfileData from ProfileScraper
    ) -> LinkedAccounts:
        """
        map all linked accounts from available data sources
        """
        result = LinkedAccounts(username=username)
        found_platforms: dict[str, PlatformLink] = {}  # platform:handle → link

        logger.info("[mapper] mapping linked accounts for @%s", username)

        # source 1: bio extracts (social handles found in bio text)
        if bio_extracts:
            self._merge_social_extracts(found_platforms, bio_extracts, "bio_text")

        # source 2: external URL — may be direct link or aggregator
        all_external_urls = []
        if external_url:
            all_external_urls.append(external_url)
        if bio_links:
            all_external_urls.extend(bio_links)
        if profile_data and profile_data.external_url:
            if profile_data.external_url not in all_external_urls:
                all_external_urls.append(profile_data.external_url)

        for url in all_external_urls:
            if self._is_link_aggregator(url):
                if self.expand_aggregators:
                    expanded = await self._expand_aggregator(url)
                    if expanded:
                        result.link_aggregators.append({
                            "url": url,
                            "expanded_links": expanded,
                        })
                        result.total_links_expanded += len(expanded)
                        for exp_url in expanded:
                            platform_link = self._classify_url(exp_url)
                            if platform_link:
                                key = f"{platform_link.platform}:{platform_link.handle}"
                                if key not in found_platforms:
                                    found_platforms[key] = platform_link
                                    platform_link.source = f"aggregator:{url}"
            else:
                # direct URL — classify it
                platform_link = self._classify_url(url)
                if platform_link:
                    key = f"{platform_link.platform}:{platform_link.handle}"
                    if key not in found_platforms:
                        found_platforms[key] = platform_link
                        platform_link.source = "external_url"

        # source 3: connected facebook page (from profile data)
        if profile_data and profile_data.connected_fb_page:
            fb_link = PlatformLink(
                platform="facebook",
                handle=profile_data.connected_fb_page,
                url=f"https://facebook.com/{profile_data.connected_fb_page_id or profile_data.connected_fb_page}",
                confidence=1.0,
                source="profile_api",
                verified=True,  # instagram confirmed this
            )
            key = f"facebook:{profile_data.connected_fb_page}"
            if key not in found_platforms:
                found_platforms[key] = fb_link

        # source 4: username correlation — same username likely on other platforms
        if username and len(username) >= 4:
            # generate candidate links based on username
            candidates = self._generate_username_candidates(username)
            for candidate in candidates:
                key = f"{candidate.platform}:{candidate.handle}"
                if key not in found_platforms:
                    candidate.confidence = 0.3  # low confidence — just username match
                    candidate.source = "username_correlation"
                    found_platforms[key] = candidate

        # verify links if enabled
        if self.verify_links:
            await self._verify_batch(found_platforms)

        # build result
        result.platforms = list(found_platforms.values())
        result.total_platforms_found = len(result.platforms)

        logger.info(
            "[mapper] @%s — %d platforms found, %d verified",
            username,
            result.total_platforms_found,
            len(result.get_verified()),
        )

        return result

    # ─── social extract merger ─────────────────────────────────────

    def _merge_social_extracts(
        self,
        found: dict,
        extracts,
        source: str,
    ):
        """merge bio_parser extracts into platform links"""
        extract_map = {
            "twitter": extracts.twitter,
            "tiktok": extracts.tiktok,
            "youtube": extracts.youtube,
            "facebook": extracts.facebook,
            "linkedin": extracts.linkedin,
            "github": extracts.github,
            "twitch": extracts.twitch,
            "snapchat": extracts.snapchat,
            "telegram": extracts.telegram,
            "discord": extracts.discord,
            "signal": extracts.signal,
            "spotify": extracts.spotify,
            "pinterest": extracts.pinterest,
            "reddit": extracts.reddit,
        }

        for platform, handles in extract_map.items():
            for handle in handles:
                clean_handle = handle.lstrip("@").strip()
                if clean_handle:
                    url = self._build_platform_url(platform, clean_handle)
                    link = PlatformLink(
                        platform=platform,
                        handle=clean_handle,
                        url=url,
                        confidence=0.8,  # high — found in bio
                        source=source,
                    )
                    key = f"{platform}:{clean_handle}"
                    if key not in found:
                        found[key] = link

    # ─── URL classification ────────────────────────────────────────

    def _classify_url(self, url: str) -> Optional[PlatformLink]:
        """classify a URL into a platform + handle"""
        url = url.strip().rstrip("/")

        if not url.startswith("http"):
            url = f"https://{url}"

        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.strip("/")

        # known platform patterns
        patterns = [
            # (platform, domain_pattern, handle_extractor)
            ("twitter", ["twitter.com", "x.com"], lambda p: p.split("/")[0] if "/" in p else p),
            ("tiktok", ["tiktok.com", "vm.tiktok.com"], lambda p: p.lstrip("@").split("/")[0]),
            ("youtube", ["youtube.com", "youtu.be"], lambda p: p.lstrip("@").split("/")[0] if p.startswith("@") else p.split("/")[-1]),
            ("facebook", ["facebook.com", "fb.com"], lambda p: p.split("/")[0] if "/" in p else p),
            ("linkedin", ["linkedin.com"], lambda p: p.split("/")[-1] if "in/" in p else p.split("/")[0]),
            ("github", ["github.com"], lambda p: p.split("/")[0]),
            ("twitch", ["twitch.tv"], lambda p: p.split("/")[0]),
            ("reddit", ["reddit.com"], lambda p: p.split("/")[-1] if "user/" in p or "u/" in p else p.split("/")[0]),
            ("snapchat", ["snapchat.com"], lambda p: p.split("/")[-1] if "add/" in p else p.split("/")[0]),
            ("telegram", ["t.me", "telegram.me"], lambda p: p.split("/")[0]),
            ("discord", ["discord.gg", "discord.com"], lambda p: p.split("/")[-1] if "invite/" in p else p.split("/")[0]),
            ("pinterest", ["pinterest.com", "pin.it"], lambda p: p.split("/")[0]),
            ("medium", ["medium.com"], lambda p: p.lstrip("@").split("/")[0]),
            ("spotify", ["open.spotify.com"], lambda p: p.split("/")[-1] if "user/" in p else p),
            ("onlyfans", ["onlyfans.com"], lambda p: p.split("/")[0]),
            ("behance", ["behance.net"], lambda p: p.split("/")[0]),
            ("dribbble", ["dribbble.com"], lambda p: p.split("/")[0]),
            ("soundcloud", ["soundcloud.com"], lambda p: p.split("/")[0]),
            ("vimeo", ["vimeo.com"], lambda p: p.split("/")[0]),
            ("substack", ["substack.com"], lambda p: p.lstrip("@").split("/")[0]),
        ]

        for platform, domains, extractor in patterns:
            if any(d in domain for d in domains):
                try:
                    handle = extractor(path)
                    handle = handle.split("?")[0].split("#")[0]  # strip query/fragment
                    if handle and len(handle) >= 2:
                        return PlatformLink(
                            platform=platform,
                            handle=handle,
                            url=url,
                            confidence=0.9,
                            source="url_classification",
                        )
                except Exception:
                    pass

        # generic website — not a social platform
        if "." in domain and len(path) < 5:
            return PlatformLink(
                platform="website",
                handle=domain,
                url=url,
                confidence=0.7,
                source="url_classification",
            )

        return None

    # ─── link aggregator expansion ─────────────────────────────────

    def _is_link_aggregator(self, url: str) -> bool:
        """check if URL is a link aggregator"""
        if not url.startswith("http"):
            url = f"https://{url}"
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return any(agg in domain for agg in self.LINK_AGGREGATORS)

    async def _expand_aggregator(self, url: str) -> list[str]:
        """
        expand a link aggregator URL to extract all underlying links
        linktree, beacons, etc. have predictable HTML structures
        """
        if not url.startswith("http"):
            url = f"https://{url}"

        proxy = None
        if self.proxy_rotator:
            proxy = await self.proxy_rotator.get_proxy()

        proxy_url = self._format_proxy(proxy) if proxy else None

        try:
            http = await self._get_http()
            async with http.get(url, proxy=proxy_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return []

                html = await resp.text()
                links = set()

                # common patterns in link aggregator HTML
                # linktree: data-url attribute or <a> tags with specific classes
                linktree_patterns = [
                    r'data-url=["\']([^"\']+)["\']',
                    r'href=["\'](https?://[^"\']+)["\'][^>]*class=["\'][^"\']*link[^"\']*',
                    r'href=["\'](https?://[^"\']+)["\']',
                ]

                for pattern in linktree_patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    for match in matches:
                        if isinstance(match, tuple):
                            match = match[0]
                        # filter out internal links and assets
                        if (
                            match.startswith("http")
                            and "linktr.ee" not in match
                            and "beacons.ai" not in match
                            and "campsite.bio" not in match
                            and ".css" not in match
                            and ".js" not in match
                            and "facebook.com/tr" not in match  # tracking pixel
                            and "google-analytics" not in match
                        ):
                            links.add(match)

                return list(links)[:20]  # limit to 20 links

        except Exception as e:
            logger.debug("[mapper] aggregator expansion failed for %s: %s", url, e)
            return []

    # ─── verification ──────────────────────────────────────────────

    async def _verify_batch(self, found: dict[str, PlatformLink]):
        """verify multiple platform links concurrently"""
        to_verify = [
            (key, link) for key, link in found.items()
            if not link.verified and link.confidence >= 0.3
        ]

        if not to_verify:
            return

        semaphore = asyncio.Semaphore(self.max_concurrent_verifications)

        async def _verify_one(key: str, link: PlatformLink):
            async with semaphore:
                verified = await self._verify_link(link)
                if verified:
                    link.verified = True
                    link.confidence = min(1.0, link.confidence + 0.2)
                else:
                    link.confidence = max(0.1, link.confidence - 0.3)

        tasks = [_verify_one(k, l) for k, l in to_verify]
        await asyncio.gather(*tasks, return_exceptions=True)

        verified_count = sum(1 for _, l in to_verify if l.verified)
        logger.debug("[mapper] verified %d/%d links", verified_count, len(to_verify))

    async def _verify_link(self, link: PlatformLink) -> bool:
        """verify that a linked account actually exists"""
        if not link.url:
            return False

        proxy = None
        if self.proxy_rotator:
            proxy = await self.proxy_rotator.get_proxy()

        proxy_url = self._format_proxy(proxy) if proxy else None

        try:
            http = await self._get_http()
            async with http.get(
                link.url,
                proxy=proxy_url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                # 200 = exists, 404 = not found, 302 = might be redirect to login
                if resp.status == 200:
                    # additional check — some platforms return 200 with "not found" in body
                    if resp.content_length and resp.content_length < 500:
                        body = await resp.text()
                        if any(
                            phrase in body.lower()
                            for phrase in ["not found", "doesn't exist", "sorry", "404", "page not found"]
                        ):
                            return False
                    return True

                if resp.status in (401, 403):
                    # exists but private — still counts
                    return True

                return False

        except Exception:
            return False

    # ─── username correlation ──────────────────────────────────────

    def _generate_username_candidates(self, username: str) -> list[PlatformLink]:
        """generate likely platform links based on username patterns"""
        candidates = []
        clean = username.lower().strip("@")

        # platforms where people often use the same handle
        platforms_to_try = [
            "twitter", "tiktok", "youtube", "github", "twitch",
            "reddit", "pinterest", "medium",
        ]

        for platform in platforms_to_try:
            if platform in self.PLATFORM_URLS:
                url = self.PLATFORM_URLS[platform].format(handle=clean)
                candidates.append(PlatformLink(
                    platform=platform,
                    handle=clean,
                    url=url,
                    confidence=0.3,
                    source="username_correlation",
                ))

        return candidates

    # ─── helpers ───────────────────────────────────────────────────

    def _build_platform_url(self, platform: str, handle: str) -> str:
        """build a platform profile URL from handle"""
        if platform in self.PLATFORM_URLS:
            return self.PLATFORM_URLS[platform].format(handle=handle)

        # default patterns
        patterns = {
            "signal": f"signal://{handle}",
            "whatsapp": f"https://wa.me/{handle}",
        }
        return patterns.get(platform, f"https://{platform}.com/{handle}")

    def _format_proxy(self, proxy: str) -> Optional[str]:
        if not proxy:
            return None
        if proxy.startswith(("http://", "socks5://", "socks4://")):
            return proxy
        return f"socks5://{proxy}"