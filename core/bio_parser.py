"""
bio parser — regex extraction engine for instagram bio text
extracts: emails, phones, DOB, locations, social handles, payment handles
purely passive — text analysis only, no network requests
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BioExtracts:
    """all data extracted from bio text via regex"""

    # raw input
    bio_text: str = ""
    full_name: str = ""
    username: str = ""

    # contact info
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    phone_country_hints: list[str] = field(default_factory=list)

    # personal info
    dates_of_birth: list[str] = field(default_factory=list)
    age_hints: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)

    # social platforms (from bio text + links)
    snapchat: list[str] = field(default_factory=list)
    telegram: list[str] = field(default_factory=list)
    discord: list[str] = field(default_factory=list)
    signal: list[str] = field(default_factory=list)
    whatsapp: list[str] = field(default_factory=list)
    twitter: list[str] = field(default_factory=list)
    tiktok: list[str] = field(default_factory=list)
    youtube: list[str] = field(default_factory=list)
    facebook: list[str] = field(default_factory=list)
    linkedin: list[str] = field(default_factory=list)
    github: list[str] = field(default_factory=list)
    twitch: list[str] = field(default_factory=list)
    spotify: list[str] = field(default_factory=list)
    pinterest: list[str] = field(default_factory=list)
    reddit: list[str] = field(default_factory=list)

    # payment / money handles
    venmo: list[str] = field(default_factory=list)
    cashapp: list[str] = field(default_factory=list)
    paypal: list[str] = field(default_factory=list)
    bitcoin: list[str] = field(default_factory=list)
    ethereum: list[str] = field(default_factory=list)

    # other
    websites: list[str] = field(default_factory=list)
    occupations: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    emoji_flags: list[str] = field(default_factory=list)
    custom_handles: list[str] = field(default_factory=list)

    # metadata
    parsed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    parse_duration_ms: float = 0.0


class BioParser:
    """
    regex-based bio text extractor

    usage:
        parser = BioParser()
        extracts = parser.parse(bio_text="LA📍 | dev@email.com | SC: john.snap")
        # extracts.emails → ["dev@email.com"]
        # extracts.snapchat → ["john.snap"]
        # extracts.locations → ["Los Angeles"]
    """

    # ─── email patterns ────────────────────────────────────────────

    EMAIL_PATTERNS = [
        # standard email
        r'[\w.+-]+@[\w-]+\.[\w.-]+',
        # obfuscated: john [at] gmail [dot] com
        r'[\w.+-]+\s*\[?at\]?\s*[\w-]+\s*\[?dot\]?\s*[\w.-]+',
        # spaced: john @ gmail . com
        r'[\w.+-]+\s+@\s+[\w-]+\s+\.\s+\w+',
    ]

    # ─── phone patterns ────────────────────────────────────────────

    PHONE_PATTERNS = [
        # international: +1 234 567 8900
        r'\+\d{1,3}[\s\-\(\)]*\d[\d\s\-\(\)]{6,}\d',
        # US format: (123) 456-7890
        r'\(\d{3}\)[\s\-]*\d{3}[\s\-]*\d{4}',
        # dotted: +1.234.567.8900
        r'\+\d{1,3}\.\d{1,4}\.\d{1,4}\.\d{1,4}',
        # simple 10+ digit sequence with separators
        r'\d{3}[\s\-\.]\d{3}[\s\-\.]\d{4}',
        # whatsapp style: wa.me/+1234567890
        r'wa\.me/\+?\d{7,15}',
    ]

    # ─── DOB patterns ──────────────────────────────────────────────

    DOB_PATTERNS = [
        # DD/MM/YYYY or MM/DD/YYYY
        r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b',
        # YYYY-MM-DD
        r'\b\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}\b',
        # "born on Jan 15 1995"
        r'(?i)born\s+(?:on\s+)?(?:\d{1,2}\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}',
        # age: "21 y/o", "age: 25"
        r'(?i)(?:age|yo|y/o)[\s:]*\d{1,2}',
    ]

    # ─── location patterns ─────────────────────────────────────────

    LOCATION_PATTERNS = [
        # "📍 Los Angeles, CA"
        r'📍\s*([\w\s,]+)',
        # "📍LA" (emoji with no space)
        r'📍([\w]+)',
        # "based in New York"
        r'(?i)(?:based|located|living)\s+(?:in|at)\s+([\w\s,]+?)(?:\s*[•·|]|\s*$)',
        # "from London"
        r'(?i)from\s+([\w\s]+?)(?:\s*[•·|]|\s*$)',
        # "NYC | LA | MIA" — common city abbreviations
        r'\b(NYC|LA|MIA|ATL|CHI|SF|SD|PDX|ATX|DFW|DC|PHL|BOS|DEN|LV|SEA|MKE|STL|KC|NOLA|MSP|DTW|PHX)\b',
        # pin emoji variations
        r'[📍📌🧭]+\s*([\w\s,]+)',
    ]

    # ─── social platform patterns ──────────────────────────────────

    SOCIAL_PATTERNS = {
        "snapchat": [
            r'(?i)(?:snap(?:chat)?|sc)[:\s]+@?(\w[\w.-]{0,30})',
            r'(?i)snap(?:chat)?\s*[:.-]\s*@?(\w[\w.-]{0,30})',
        ],
        "telegram": [
            r'(?i)(?:telegram|tg|t\.me)[:\s]+@?(\w[\w.]{0,30})',
            r'(?i)t\.me/(\w[\w.]{0,30})',
        ],
        "discord": [
            r'(?i)(?:discord|dc|disc)[:\s]+@?([\w#]{3,30})',
            r'(?i)discord\s*[:.-]\s*@?([\w#]{3,30})',
        ],
        "signal": [
            r'(?i)signal[:\s]+@?(\w[\w.-]{0,30})',
        ],
        "whatsapp": [
            r'(?i)(?:whatsapp|wa)[:\s]+(\+?\d[\d\s\-]{7,})',
            r'(?i)wa\.me/(\+?\d{7,})',
        ],
        "twitter": [
            r'(?i)(?:twitter|x|twt)[:\s]+@?(\w{1,15})',
            r'(?i)(?:x\.com|twitter\.com)/(\w{1,15})',
        ],
        "tiktok": [
            r'(?i)(?:tiktok|tt)[:\s]+@?([\w.]{1,30})',
            r'(?i)tiktok\.com/@([\w.]{1,30})',
        ],
        "youtube": [
            r'(?i)(?:youtube|yt)[:\s]+@?([\w-]{1,30})',
            r'(?i)youtube\.com/@([\w-]{1,30})',
            r'(?i)youtube\.com/c/([\w-]{1,30})',
        ],
        "facebook": [
            r'(?i)(?:facebook|fb)[:\s]+@?([\w.]{1,50})',
            r'(?i)facebook\.com/([\w.]{1,50})',
        ],
        "linkedin": [
            r'(?i)(?:linkedin|li)[:\s]+@?([\w-]{1,50})',
            r'(?i)linkedin\.com/in/([\w-]{1,50})',
        ],
        "github": [
            r'(?i)(?:github|gh)[:\s]+@?([\w-]{1,39})',
            r'(?i)github\.com/([\w-]{1,39})',
        ],
        "twitch": [
            r'(?i)(?:twitch|ttv)[:\s]+@?([\w]{1,25})',
            r'(?i)twitch\.tv/([\w]{1,25})',
        ],
        "spotify": [
            r'(?i)spotify[:\s]+@?([\w]{1,30})',
        ],
        "pinterest": [
            r'(?i)pinterest[:\s]+@?([\w]{1,30})',
            r'(?i)pinterest\.com/([\w]{1,30})',
        ],
        "reddit": [
            r'(?i)(?:reddit|r/)[:\s]+u/([\w-]{1,20})',
            r'(?i)reddit\.com/u(?:ser)?/([\w-]{1,20})',
        ],
    }

    # ─── payment platform patterns ─────────────────────────────────

    PAYMENT_PATTERNS = {
        "venmo": [
            r'(?i)(?:venmo|vnmo)[:\s]+@?([\w-]{1,30})',
            r'(?i)venmo\.com/([\w-]{1,30})',
        ],
        "cashapp": [
            r'(?i)(?:cashapp|ca\$h|cash app)[:\s]+\$?([\w$]{1,30})',
            r'(?i)cash\.app/([\w$]{1,30})',
        ],
        "paypal": [
            r'(?i)(?:paypal|pp)[:\s]+@?([\w.@-]{1,50})',
            r'(?i)paypal\.me/([\w]{1,30})',
        ],
        "bitcoin": [
            r'(?i)(?:btc|bitcoin)[:\s]+([13bc1][a-zA-Z0-9]{25,42})',
        ],
        "ethereum": [
            r'(?i)(?:eth|ethereum)[:\s]+(0x[a-fA-F0-9]{40})',
        ],
    }

    # ─── occupation patterns ───────────────────────────────────────

    OCCUPATION_PATTERNS = [
        r'(?i)(?:developer|engineer|designer|artist|writer|photographer|musician|'
        r'dj|producer|model|actor|doctor|nurse|lawyer|teacher|student|'
        r'founder|ceo|cto|entrepreneur|freelancer|influencer|creator|'
        r'streamer|gamer|coach|trainer|chef|barber|tattoo|architect|'
        r'scientist|analyst|consultant|manager|director)',
    ]

    # ─── website patterns ──────────────────────────────────────────

    WEBSITE_PATTERNS = [
        r'https?://[^\s]{4,}',
        r'[\w-]+\.[\w.-]+\.\w{2,}(?:/[^\s]*)?',
    ]

    # ─── emoji flag → country ──────────────────────────────────────

    EMOJI_FLAG_MAP = {
        "🇺🇸": "United States", "🇬🇧": "United Kingdom", "🇨🇦": "Canada",
        "🇦🇺": "Australia", "🇩🇪": "Germany", "🇫🇷": "France",
        "🇮🇳": "India", "🇵🇰": "Pakistan", "🇧🇷": "Brazil",
        "🇯🇵": "Japan", "🇰🇷": "South Korea", "🇮🇹": "Italy",
        "🇪🇸": "Spain", "🇲🇽": "Mexico", "🇷🇺": "Russia",
        "🇵🇭": "Philippines", "🇮🇩": "Indonesia", "🇹🇷": "Turkey",
        "🇸🇦": "Saudi Arabia", "🇦🇪": "UAE", "🇳🇬": "Nigeria",
        "🇿🇦": "South Africa", "🇪🇬": "Egypt", "🇦🇷": "Argentina",
        "🇨🇴": "Colombia", "🇵🇪": "Peru", "🇨🇱": "Chile",
        "🇻🇳": "Vietnam", "🇹🇭": "Thailand", "🇲🇾": "Malaysia",
        "🇳🇱": "Netherlands", "🇧🇪": "Belgium", "🇨🇭": "Switzerland",
        "🇸🇪": "Sweden", "🇳🇴": "Norway", "🇩🇰": "Denmark",
    }

    def __init__(self):
        self._compiled_email = [re.compile(p, re.IGNORECASE) for p in self.EMAIL_PATTERNS]
        self._compiled_phone = [re.compile(p, re.IGNORECASE) for p in self.PHONE_PATTERNS]
        self._compiled_dob = [re.compile(p, re.IGNORECASE) for p in self.DOB_PATTERNS]
        self._compiled_location = [re.compile(p) for p in self.LOCATION_PATTERNS]
        self._compiled_occupation = [re.compile(p, re.IGNORECASE) for p in self.OCCUPATION_PATTERNS]
        self._compiled_website = [re.compile(p, re.IGNORECASE) for p in self.WEBSITE_PATTERNS]

    # ─── main parse method ─────────────────────────────────────────

    def parse(
        self,
        bio_text: str = "",
        full_name: str = "",
        username: str = "",
        external_url: str = "",
    ) -> BioExtracts:
        """
        parse bio text and extract all identifiable information

        bio_text: the biography field from instagram profile
        full_name: display name for additional context
        username: @handle for additional context
        external_url: the external link from profile
        """
        import time
        start = time.monotonic()

        extracts = BioExtracts(
            bio_text=bio_text,
            full_name=full_name,
            username=username,
        )

        # combine all text sources
        combined_text = f"{bio_text}\n{full_name}\n{external_url}"

        if not combined_text.strip():
            extracts.parse_duration_ms = (time.monotonic() - start) * 1000
            return extracts

        # extract everything
        extracts = self._extract_emails(combined_text, extracts)
        extracts = self._extract_phones(combined_text, extracts)
        extracts = self._extract_dob(combined_text, extracts)
        extracts = self._extract_locations(combined_text, extracts)
        extracts = self._extract_social(combined_text, extracts)
        extracts = self._extract_payment(combined_text, extracts)
        extracts = self._extract_websites(combined_text, extracts)
        extracts = self._extract_occupations(combined_text, extracts)
        extracts = self._extract_hashtags(combined_text, extracts)
        extracts = self._extract_mentions(combined_text, extracts)
        extracts = self._extract_emoji_flags(combined_text, extracts)

        # deduplicate
        extracts = self._deduplicate(extracts)

        extracts.parse_duration_ms = (time.monotonic() - start) * 1000

        logger.debug(
            "[bio_parser] extracted — emails:%d phones:%d locations:%d social:%d",
            len(extracts.emails),
            len(extracts.phones),
            len(extracts.locations),
            sum(len(v) for v in [
                extracts.snapchat, extracts.telegram, extracts.discord,
                extracts.twitter, extracts.tiktok, extracts.youtube,
            ]),
        )

        return extracts

    # ─── individual extractors ─────────────────────────────────────

    def _extract_emails(self, text: str, extracts: BioExtracts) -> BioExtracts:
        for pattern in self._compiled_email:
            matches = pattern.findall(text)
            for match in matches:
                # clean obfuscated emails
                clean = match.strip()
                clean = re.sub(r'\s*\[?at\]?\s*', '@', clean, flags=re.IGNORECASE)
                clean = re.sub(r'\s*\[?dot\]?\s*', '.', clean, flags=re.IGNORECASE)
                clean = re.sub(r'\s+', '', clean)
                if '@' in clean and '.' in clean.split('@')[-1]:
                    extracts.emails.append(clean.lower())
        return extracts

    def _extract_phones(self, text: str, extracts: BioExtracts) -> BioExtracts:
        for pattern in self._compiled_phone:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                clean = re.sub(r'[\s\-\(\)\.]', '', match.strip())
                if clean.startswith('+') and len(clean) >= 10:
                    extracts.phones.append(clean)
                elif len(clean) == 10 and clean.isdigit():
                    extracts.phones.append(clean)
                    extracts.phone_country_hints.append("likely US (+1)")
        return extracts

    def _extract_dob(self, text: str, extracts: BioExtracts) -> BioExtracts:
        for pattern in self._compiled_dob:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                clean = match.strip()
                if clean and len(clean) >= 3:
                    if re.search(r'\d', clean):  # must contain digits
                        extracts.dates_of_birth.append(clean)
                        # check if it's an age hint
                        age_match = re.search(r'(\d{1,2})', clean)
                        if age_match:
                            age = int(age_match.group(1))
                            if 13 <= age <= 80:
                                extracts.age_hints.append(str(age))
        return extracts

    def _extract_locations(self, text: str, extracts: BioExtracts) -> BioExtracts:
        for pattern in self._compiled_location:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                clean = match.strip().rstrip('.,;:•·|').strip()
                if clean and len(clean) >= 2:
                    # filter out common non-location words
                    if clean.lower() not in ("i", "me", "my", "the", "and", "for", "you", "now", "new", "one", "all", "bio", "link"):
                        extracts.locations.append(clean)
                        # classify city vs country
                        if ',' in clean:
                            extracts.cities.append(clean.split(',')[0].strip())
        return extracts

    def _extract_social(self, text: str, extracts: BioExtracts) -> BioExtracts:
        platform_map = {
            "snapchat": extracts.snapchat,
            "telegram": extracts.telegram,
            "discord": extracts.discord,
            "signal": extracts.signal,
            "whatsapp": extracts.whatsapp,
            "twitter": extracts.twitter,
            "tiktok": extracts.tiktok,
            "youtube": extracts.youtube,
            "facebook": extracts.facebook,
            "linkedin": extracts.linkedin,
            "github": extracts.github,
            "twitch": extracts.twitch,
            "spotify": extracts.spotify,
            "pinterest": extracts.pinterest,
            "reddit": extracts.reddit,
        }

        for platform, patterns in self.SOCIAL_PATTERNS.items():
            for pattern in patterns:
                compiled = re.compile(pattern, re.IGNORECASE)
                matches = compiled.findall(text)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    clean = match.strip().lstrip('@').strip()
                    if clean and len(clean) >= 2:
                        target_list = platform_map.get(platform, [])
                        if clean not in target_list:
                            target_list.append(clean)

        return extracts

    def _extract_payment(self, text: str, extracts: BioExtracts) -> BioExtracts:
        payment_map = {
            "venmo": extracts.venmo,
            "cashapp": extracts.cashapp,
            "paypal": extracts.paypal,
            "bitcoin": extracts.bitcoin,
            "ethereum": extracts.ethereum,
        }

        for platform, patterns in self.PAYMENT_PATTERNS.items():
            for pattern in patterns:
                compiled = re.compile(pattern, re.IGNORECASE)
                matches = compiled.findall(text)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    clean = match.strip().lstrip('@$').strip()
                    if clean and len(clean) >= 2:
                        target_list = payment_map.get(platform, [])
                        if clean not in target_list:
                            target_list.append(clean)

        return extracts

    def _extract_websites(self, text: str, extracts: BioExtracts) -> BioExtracts:
        for pattern in self._compiled_website:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                clean = match.strip().rstrip('.,;:)!]').strip()
                if clean and '.' in clean and len(clean) >= 6:
                    # filter out false positives (dates, etc)
                    if not re.match(r'^\d{1,2}[./]\d{1,2}[./]\d{2,4}$', clean):
                        extracts.websites.append(clean)
        return extracts

    def _extract_occupations(self, text: str, extracts: BioExtracts) -> BioExtracts:
        for pattern in self._compiled_occupation:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                clean = match.strip().lower()
                if clean and clean not in extracts.occupations:
                    extracts.occupations.append(clean)
        return extracts

    def _extract_hashtags(self, text: str, extracts: BioExtracts) -> BioExtracts:
        hashtag_pattern = re.compile(r'#(\w+)')
        matches = hashtag_pattern.findall(text)
        extracts.hashtags = list(set(matches))
        return extracts

    def _extract_mentions(self, text: str, extracts: BioExtracts) -> BioExtracts:
        mention_pattern = re.compile(r'@(\w[\w.]{0,29})')
        matches = mention_pattern.findall(text)
        # filter out the target's own username
        own = extracts.username.lower()
        extracts.mentions = [
            m for m in set(matches)
            if m.lower() != own
        ]
        return extracts

    def _extract_emoji_flags(self, text: str, extracts: BioExtracts) -> BioExtracts:
        for emoji, country in self.EMOJI_FLAG_MAP.items():
            if emoji in text and country not in extracts.countries:
                extracts.countries.append(country)
                extracts.emoji_flags.append(emoji)
        return extracts

    # ─── helpers ───────────────────────────────────────────────────

    def _deduplicate(self, extracts: BioExtracts) -> BioExtracts:
        """remove duplicates from all list fields"""
        list_fields = [
            f for f in extracts.__dataclass_fields__
            if isinstance(getattr(extracts, f), list)
        ]
        for field_name in list_fields:
            current = getattr(extracts, field_name)
            seen = set()
            deduped = []
            for item in current:
                item_lower = item.lower() if isinstance(item, str) else item
                if item_lower not in seen:
                    seen.add(item_lower)
                    deduped.append(item)
            setattr(extracts, field_name, deduped)
        return extracts

    def get_summary(self, extracts: BioExtracts) -> dict:
        """return a summary of what was found"""
        return {
            "emails_found": len(extracts.emails),
            "phones_found": len(extracts.phones),
            "locations_found": len(extracts.locations),
            "social_platforms_found": sum(
                1 for v in [
                    extracts.snapchat, extracts.telegram, extracts.discord,
                    extracts.signal, extracts.whatsapp, extracts.twitter,
                    extracts.tiktok, extracts.youtube, extracts.facebook,
                    extracts.linkedin, extracts.github, extracts.twitch,
                    extracts.spotify, extracts.pinterest, extracts.reddit,
                ] if v
            ),
            "payment_platforms_found": sum(
                1 for v in [
                    extracts.venmo, extracts.cashapp, extracts.paypal,
                    extracts.bitcoin, extracts.ethereum,
                ] if v
            ),
            "occupations_found": len(extracts.occupations),
            "websites_found": len(extracts.websites),
        }