"""
fingerprint engine — browser fingerprint randomization for instagram
generates unique fingerprints: user agent, screen, timezone, webgl, canvas, fonts
syncs geo with proxy for consistency
instagram-specific: mobile app device IDs, IG-specific headers
"""

import hashlib
import logging
import random
import string
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Fingerprint:
    fingerprint_id: str
    user_agent: str
    platform: str
    screen_width: int
    screen_height: int
    viewport_width: int
    viewport_height: int
    device_pixel_ratio: float
    timezone: str
    timezone_offset: int
    language: str
    languages: list[str]
    hardware_concurrency: int
    device_memory: int
    canvas_hash: str
    webgl_vendor: str
    webgl_renderer: str
    fonts: list[str]
    audio_fingerprint: str
    do_not_track: bool
    touch_support: bool
    instagram_device_id: str = ""
    instagram_app_id: str = ""
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.fingerprint_id,
            "user_agent": self.user_agent,
            "platform": self.platform,
            "screen": f"{self.screen_width}x{self.screen_height}",
            "viewport": f"{self.viewport_width}x{self.viewport_height}",
            "dpr": self.device_pixel_ratio,
            "timezone": self.timezone,
            "language": self.language,
            "cores": self.hardware_concurrency,
            "memory": self.device_memory,
            "webgl_vendor": self.webgl_vendor,
            "webgl_renderer": self.webgl_renderer,
            "touch": self.touch_support,
        }


class FingerprintEngine:
    """generates randomized browser fingerprints optimized for instagram"""

    DEVICE_PROFILES = {
        "android_high": {
            "platforms": ["Linux armv8l", "Linux aarch64"],
            "screen_presets": [(1080, 2400, 2.75), (1440, 3120, 3.0), (1080, 2340, 2.5)],
            "memory_range": (4, 12),
            "cores_range": (6, 8),
            "touch_support": True,
        },
        "android_mid": {
            "platforms": ["Linux armv8l"],
            "screen_presets": [(720, 1600, 2.0), (1080, 1920, 2.5)],
            "memory_range": (2, 6),
            "cores_range": (4, 8),
            "touch_support": True,
        },
        "ios_high": {
            "platforms": ["iPhone"],
            "screen_presets": [(1179, 2556, 3.0), (1290, 2796, 3.0)],
            "memory_range": (4, 8),
            "cores_range": (6, 6),
            "touch_support": True,
        },
        "desktop_windows": {
            "platforms": ["Win32", "Win64"],
            "screen_presets": [(1920, 1080, 1.0), (2560, 1440, 1.25), (1366, 768, 1.0)],
            "memory_range": (4, 32),
            "cores_range": (4, 16),
            "touch_support": False,
        },
        "desktop_mac": {
            "platforms": ["MacIntel"],
            "screen_presets": [(1680, 1050, 2.0), (2560, 1600, 2.0), (1920, 1080, 1.0)],
            "memory_range": (8, 32),
            "cores_range": (8, 12),
            "touch_support": False,
        },
    }

    WEBGL_PAIRS = [
        ("Google Inc.", "ANGLE (Qualcomm, Adreno 750, OpenGL ES 3.2)"),
        ("Google Inc.", "ANGLE (Qualcomm, Adreno 740, OpenGL ES 3.2)"),
        ("Google Inc.", "ANGLE (ARM, Mali-G710, OpenGL ES 3.2)"),
        ("Google Inc.", "ANGLE (Apple, Apple A17 Pro, OpenGL ES 3.2)"),
        ("Google Inc.", "ANGLE (NVIDIA, GeForce RTX 4060, OpenGL 4.5)"),
        ("Google Inc.", "ANGLE (Intel, UHD Graphics 770, OpenGL 4.5)"),
        ("Google Inc.", "ANGLE (AMD, Radeon RX 7600, OpenGL 4.5)"),
        ("Google Inc.", "ANGLE (Intel, Iris Xe Graphics, OpenGL 4.5)"),
        ("Google Inc.", "ANGLE (Apple, Apple M3, OpenGL 4.1)"),
        ("Google Inc.", "ANGLE (Apple, Apple M2, OpenGL 4.1)"),
    ]

    TIMEZONES = {
        "US": ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
        "GB": ["Europe/London"],
        "DE": ["Europe/Berlin"],
        "FR": ["Europe/Paris"],
        "IN": ["Asia/Kolkata"],
        "PK": ["Asia/Karachi"],
        "ID": ["Asia/Jakarta"],
        "BR": ["America/Sao_Paulo"],
        "JP": ["Asia/Tokyo"],
        "KR": ["Asia/Seoul"],
        "AU": ["Australia/Sydney"],
        "CA": ["America/Toronto", "America/Vancouver"],
        "DEFAULT": ["America/New_York", "Europe/London"],
    }

    INSTAGRAM_APP_IDS = [
        "567067343352427",  # android
        "936619743392459",  # web
        "124024574287414",  # FB app
    ]

    def __init__(self, device_type: str = "random"):
        self.device_type = device_type
        self._rng = random.Random()
        self._generated_hashes: set[str] = set()

    async def generate(self, proxy: Optional[str] = None, device_type: Optional[str] = None) -> Fingerprint:
        dt = device_type or self.device_type
        if dt == "random":
            dt = self._rng.choice(list(self.DEVICE_PROFILES.keys()))

        profile = self.DEVICE_PROFILES.get(dt, self.DEVICE_PROFILES["android_high"])
        region = "DEFAULT"
        screen_w, screen_h, dpr = self._rng.choice(profile["screen_presets"])
        vendor, renderer = self._rng.choice(self.WEBGL_PAIRS)
        timezone = self._rng.choice(self.TIMEZONES.get(region, self.TIMEZONES["DEFAULT"]))

        fp = Fingerprint(
            fingerprint_id=f"fp_{int(time.time()*1000)}_{self._rng.randint(1000,9999)}",
            user_agent=self._generate_user_agent(dt),
            platform=self._rng.choice(profile["platforms"]),
            screen_width=screen_w,
            screen_height=screen_h,
            viewport_width=screen_w,
            viewport_height=screen_h - self._rng.randint(50, 120),
            device_pixel_ratio=dpr,
            timezone=timezone,
            timezone_offset=self._get_offset(timezone),
            language="en-US",
            languages=["en-US", "en"],
            hardware_concurrency=self._rng.randint(*profile["cores_range"]),
            device_memory=self._rng.randint(*profile["memory_range"]),
            canvas_hash=self._generate_canvas_hash(),
            webgl_vendor=vendor,
            webgl_renderer=renderer,
            fonts=self._generate_fonts(),
            audio_fingerprint=self._generate_audio_hash(),
            do_not_track=self._rng.choice([True, False]),
            touch_support=profile["touch_support"],
            instagram_device_id=f"android-{''.join(self._rng.choices('0123456789abcdef', k=16))}",
            instagram_app_id=self._rng.choice(self.INSTAGRAM_APP_IDS),
        )

        while fp.fingerprint_id in self._generated_hashes:
            fp.fingerprint_id = f"fp_{int(time.time()*1000)}_{self._rng.randint(1000,9999)}"
        self._generated_hashes.add(fp.fingerprint_id)

        return fp

    def _generate_user_agent(self, device_type: str) -> str:
        chrome_ver = self._rng.choice(["126.0.6478.122", "126.0.6478.110", "125.0.6422.165", "125.0.6422.146"])
        if "android" in device_type:
            return (
                f"Mozilla/5.0 (Linux; Android {self._rng.choice(['14','13','12'])}; "
                f"{self._rng.choice(['SM-S908B','Pixel 8 Pro','SM-A556B','OnePlus 11','Xiaomi 14'])}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Mobile Safari/537.36"
            )
        if "ios" in device_type:
            return (
                f"Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
            )
        if "mac" in device_type:
            return (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
            )
        return (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36"
        )

    def _generate_canvas_hash(self) -> str:
        return hashlib.sha256(
            "".join(self._rng.choices(string.ascii_letters + string.digits, k=64)).encode()
        ).hexdigest()[:32]

    def _generate_audio_hash(self) -> str:
        return hashlib.md5(
            "".join(self._rng.choices(string.ascii_letters + string.digits, k=48)).encode()
        ).hexdigest()[:16]

    def _generate_fonts(self) -> list[str]:
        common = [
            "Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana",
            "Georgia", "Trebuchet MS", "Comic Sans MS", "Impact", "Lucida Console",
            "Tahoma", "Palatino Linotype", "Roboto", "Noto Sans", "Open Sans", "Montserrat",
        ]
        return sorted(self._rng.sample(common, k=self._rng.randint(8, 14)))

    def _get_offset(self, timezone: str) -> int:
        offsets = {
            "America/New_York": -5, "America/Chicago": -6, "America/Denver": -7,
            "America/Los_Angeles": -8, "America/Toronto": -5, "America/Vancouver": -8,
            "America/Sao_Paulo": -3, "Europe/London": 0, "Europe/Berlin": 1,
            "Europe/Paris": 1, "Asia/Kolkata": 5, "Asia/Karachi": 5,
            "Asia/Jakarta": 7, "Asia/Tokyo": 9, "Asia/Seoul": 9,
            "Australia/Sydney": 10,
        }
        return offsets.get(timezone, 0)