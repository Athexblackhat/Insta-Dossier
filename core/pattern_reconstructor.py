"""
pattern reconstructor — masked email/phone → full identity reconstruction
uses name, username, known patterns, and domain intelligence
generates ranked candidates with confidence scoring
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EmailCandidate:
    """a reconstructed email candidate"""
    email: str
    pattern_used: str            # "first.last", "flast", etc.
    confidence: float = 0.0      # 0.0 — 1.0
    match_details: dict = field(default_factory=dict)


@dataclass
class PhoneCandidate:
    """a reconstructed phone number candidate"""
    full_number: str
    country_code: str
    pattern: str                # "last4_match", "carrier_match", etc.
    confidence: float = 0.0


@dataclass
class ReconstructedIdentity:
    """full identity reconstruction results"""

    username: str
    full_name: str = ""

    # source data
    masked_email: str = ""
    masked_phone: str = ""
    email_domain: str = ""
    email_first_char: str = ""
    email_last_chars: str = ""
    phone_country_code: str = ""
    phone_last_digits: str = ""

    # candidates
    email_candidates: list[EmailCandidate] = field(default_factory=list)
    phone_candidates: list[PhoneCandidate] = field(default_factory=list)

    # best guess
    best_email: Optional[EmailCandidate] = None
    best_phone: Optional[PhoneCandidate] = None

    # stats
    total_email_candidates: int = 0
    total_phone_candidates: int = 0
    high_confidence_count: int = 0   # >80%
    reconstructed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class PatternReconstructor:
    """
    masked data → full identity reconstruction engine

    usage:
        recon = PatternReconstructor()
        identity = recon.reconstruct(
            username="john_doe_",
            full_name="John Doe",
            masked_email="j****e@gmail.com",
            masked_phone="+1 3** *** 5678",
        )
        # identity.best_email → EmailCandidate(email="john.doe@gmail.com", confidence=0.92)
    """

    # common email patterns ordered by prevalence
    EMAIL_PATTERNS = [
        ("first.last", "{first}.{last}"),
        ("firstlast", "{first}{last}"),
        ("first_last", "{first}_{last}"),
        ("flast", "{f}{last}"),
        ("first.l", "{first}.{l}"),
        ("f.last", "{f}.{last}"),
        ("last.first", "{last}.{first}"),
        ("firstl", "{first}{l}"),
        ("first", "{first}"),
        ("lastfirst", "{last}{first}"),
        ("firstmiddlelast", "{first}{middle}{last}"),
        ("fmlast", "{f}{m}{last}"),
        ("nicknamelast", "{nickname}{last}"),
        ("first_last_birthyear", "{first}_{last}{birth_year_short}"),
        ("firstlast_birthyear", "{first}{last}{birth_year_short}"),
        ("first_birthyear", "{first}{birth_year_short}"),
    ]

    # common separators
    SEPARATORS = ["", ".", "_", "-"]

    # common number suffixes
    NUMBER_SUFFIXES = ["", "1", "12", "123", "007", "01", "99", "23", "42", "69", "00", "7", "11"]

    def __init__(self):
        self._common_names = self._load_common_names()

    # ─── main reconstruction ───────────────────────────────────────

    def reconstruct(
        self,
        username: str = "",
        full_name: str = "",
        masked_email: str = "",
        masked_phone: str = "",
        email_domain: str = "",
        email_first_char: str = "",
        email_last_chars: str = "",
        phone_country_code: str = "",
        phone_last_digits: str = "",
        bio_emails: list[str] = None,
        known_handles: list[str] = None,
    ) -> ReconstructedIdentity:
        """
        reconstruct full identity from masked data and context

        username: instagram @handle
        full_name: display name from profile
        masked_email: from reset flow — "j****e@gmail.com"
        masked_phone: from reset flow — "+1 3** *** 5678"
        bio_emails: any emails found in bio
        known_handles: usernames from linked platforms
        """
        identity = ReconstructedIdentity(
            username=username,
            full_name=full_name,
            masked_email=masked_email,
            masked_phone=masked_phone,
            email_domain=email_domain,
            email_first_char=email_first_char,
            email_last_chars=email_last_chars,
            phone_country_code=phone_country_code,
            phone_last_digits=phone_last_digits,
        )

        # extract name parts
        name_parts = self._parse_name(full_name, username)

        # reconstruct email
        if masked_email:
            identity = self._reconstruct_email(identity, name_parts, bio_emails or [])

        # reconstruct phone
        if masked_phone:
            identity = self._reconstruct_phone(identity, phone_country_code, phone_last_digits)

        # cross-reference with known handles
        if known_handles:
            identity = self._cross_reference_handles(identity, known_handles)

        # select best candidates
        if identity.email_candidates:
            identity.email_candidates.sort(key=lambda x: x.confidence, reverse=True)
            identity.best_email = identity.email_candidates[0]

        if identity.phone_candidates:
            identity.phone_candidates.sort(key=lambda x: x.confidence, reverse=True)
            identity.best_phone = identity.phone_candidates[0]

        identity.total_email_candidates = len(identity.email_candidates)
        identity.total_phone_candidates = len(identity.phone_candidates)
        identity.high_confidence_count = sum(
            1 for e in identity.email_candidates if e.confidence >= 0.8
        ) + sum(1 for p in identity.phone_candidates if p.confidence >= 0.8)

        logger.info(
            "[reconstructor] @%s — %d emails (%d high conf), %d phones",
            username,
            identity.total_email_candidates,
            identity.high_confidence_count,
            identity.total_phone_candidates,
        )

        return identity

    # ─── name parsing ──────────────────────────────────────────────

    def _parse_name(self, full_name: str, username: str) -> dict:
        """parse full name into components"""
        parts = {
            "first": "",
            "last": "",
            "middle": "",
            "f": "",   # first initial
            "l": "",   # last initial
            "m": "",   # middle initial
            "nickname": "",
        }

        if full_name:
            name_parts = full_name.strip().split()
            if len(name_parts) >= 1:
                parts["first"] = name_parts[0].lower()
                parts["f"] = name_parts[0][0].lower() if name_parts[0] else ""
            if len(name_parts) >= 2:
                parts["last"] = name_parts[-1].lower()
                parts["l"] = name_parts[-1][0].lower() if name_parts[-1] else ""
            if len(name_parts) >= 3:
                parts["middle"] = name_parts[1].lower()
                parts["m"] = name_parts[1][0].lower() if name_parts[1] else ""

        # fallback: extract from username
        if not parts["first"] and username:
            # username patterns: john_doe, john.doe, johndoe, john_doe_123
            clean = username.lower().strip("@").rstrip("0123456789._-")
            clean = re.sub(r'[._-]', ' ', clean).strip()
            user_parts = clean.split()
            if len(user_parts) >= 1:
                if not parts["first"]:
                    parts["first"] = user_parts[0]
                    parts["f"] = user_parts[0][0]
            if len(user_parts) >= 2:
                if not parts["last"]:
                    parts["last"] = user_parts[-1]
                    parts["l"] = user_parts[-1][0]

        # nickname: first name variants
        if parts["first"]:
            parts["nickname"] = self._get_common_nickname(parts["first"])

        return parts

    # ─── email reconstruction ──────────────────────────────────────

    def _reconstruct_email(
        self,
        identity: ReconstructedIdentity,
        name_parts: dict,
        bio_emails: list[str],
    ) -> ReconstructedIdentity:
        """generate and score email candidates"""

        domain = identity.email_domain or "gmail.com"

        # if bio already has an email, that's highest confidence
        for bio_email in bio_emails:
            if self._matches_masked(bio_email, identity.masked_email):
                candidate = EmailCandidate(
                    email=bio_email.lower(),
                    pattern_used="bio_extract",
                    confidence=0.98,
                    match_details={"source": "bio_text"},
                )
                identity.email_candidates.append(candidate)

        # generate from patterns
        generated = set()

        for pattern_name, pattern_template in self.EMAIL_PATTERNS:
            try:
                email_local = pattern_template.format(
                    first=name_parts.get("first", ""),
                    last=name_parts.get("last", ""),
                    middle=name_parts.get("middle", ""),
                    f=name_parts.get("f", ""),
                    l=name_parts.get("l", ""),
                    m=name_parts.get("m", ""),
                    nickname=name_parts.get("nickname", name_parts.get("first", "")),
                    birth_year_short="",  # no DOB, skip
                )

                if email_local and len(email_local) >= 3:
                    # try with and without separators and number suffixes
                    for suffix in self.NUMBER_SUFFIXES[:3]:  # limit suffixes
                        local = f"{email_local}{suffix}"
                        if local not in generated:
                            generated.add(local)
                            email = f"{local}@{domain}"

                            # score based on masked match
                            confidence = self._score_email_match(
                                email, identity.masked_email, name_parts, pattern_name
                            )

                            if confidence >= 0.2:  # minimum threshold
                                candidate = EmailCandidate(
                                    email=email,
                                    pattern_used=pattern_name,
                                    confidence=confidence,
                                    match_details={
                                        "first_char_match": email[0] == identity.email_first_char if identity.email_first_char else None,
                                        "last_chars_match": email.split("@")[0][-2:] == identity.email_last_chars if identity.email_last_chars else None,
                                        "length_match": len(email.split("@")[0]) == identity.email_last_chars if hasattr(identity, 'email_masked_length') else None,
                                        "name_match": name_parts.get("first", "") in email.lower(),
                                    },
                                )
                                identity.email_candidates.append(candidate)

            except KeyError:
                continue

        # try with common domains if no domain specified
        if not identity.email_domain or identity.email_domain == "gmail.com":
            common_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"]
            for alt_domain in common_domains:
                if alt_domain == domain:
                    continue
                for candidate in identity.email_candidates[:5]:  # top 5 candidates
                    alt_email = candidate.email.replace(f"@{domain}", f"@{alt_domain}")
                    alt_confidence = candidate.confidence * 0.5  # lower — different domain
                    identity.email_candidates.append(EmailCandidate(
                        email=alt_email,
                        pattern_used=f"{candidate.pattern_used}@{alt_domain}",
                        confidence=alt_confidence,
                        match_details={"alternate_domain": True},
                    ))

        # deduplicate by email
        seen = set()
        unique = []
        for c in identity.email_candidates:
            if c.email not in seen:
                seen.add(c.email)
                unique.append(c)
        identity.email_candidates = unique

        return identity

    def _score_email_match(
        self,
        email: str,
        masked: str,
        name_parts: dict,
        pattern: str,
    ) -> float:
        """score how well a generated email matches the masked version"""
        score = 0.0
        local_part = email.split("@")[0]

        if not masked or "@" not in masked:
            return 0.3  # no mask to compare against

        masked_local, masked_domain = masked.split("@", 1)

        # 1. first character match
        if masked_local and local_part:
            if masked_local[0] != "*" and local_part[0] == masked_local[0]:
                score += 0.25
            elif masked_local[0] == "*":
                score += 0.15  # can't verify but not a mismatch

        # 2. length match
        if len(local_part) == len(masked_local):
            score += 0.20
        elif abs(len(local_part) - len(masked_local)) <= 2:
            score += 0.10

        # 3. pattern weight — some patterns are more common
        pattern_weights = {
            "first.last": 0.15, "firstlast": 0.12, "first_last": 0.10,
            "flast": 0.10, "first.l": 0.08, "f.last": 0.08,
            "last.first": 0.05, "first": 0.05, "firstl": 0.08,
        }
        score += pattern_weights.get(pattern, 0.05)

        # 4. name in email
        first = name_parts.get("first", "")
        last = name_parts.get("last", "")
        if first and first in local_part:
            score += 0.15
        if last and last in local_part:
            score += 0.10

        # 5. last characters match (if visible in mask)
        visible_last = re.sub(r'\*+', '', masked_local)
        if visible_last and len(visible_last) >= 2:
            if local_part.endswith(visible_last):
                score += 0.20
            elif local_part[-2:] == visible_last[-2:]:
                score += 0.10

        # 6. domain match
        email_domain = email.split("@")[1]
        if email_domain == masked_domain:
            score += 0.10

        return min(score, 0.95)  # cap at 0.95 — never 100% without verification

    def _matches_masked(self, email: str, masked: str) -> bool:
        """check if a full email matches the masked pattern"""
        if not masked or "@" not in masked:
            return False

        email_local, email_domain = email.split("@", 1)
        masked_local, masked_domain = masked.split("@", 1)

        # domain must match
        if email_domain.lower() != masked_domain.lower():
            return False

        # local part pattern match
        # convert mask to regex: j****e → j.*e
        mask_regex = masked_local.replace("*", ".*")
        mask_regex = f"^{mask_regex}$"

        return bool(re.match(mask_regex, email_local, re.IGNORECASE))

    # ─── phone reconstruction ──────────────────────────────────────

    def _reconstruct_phone(
        self,
        identity: ReconstructedIdentity,
        country_code: str,
        last_digits: str,
    ) -> ReconstructedIdentity:
        """generate phone number candidates based on masked data"""

        if not last_digits:
            return identity

        cc = country_code or identity.phone_country_code or "+1"
        cc_digits = re.sub(r'\D', '', cc)

        # carrier prefixes (from data/phone_prefixes.json — simplified here)
        carrier_prefixes = self._get_carrier_prefixes(cc)

        for prefix in carrier_prefixes:
            full_number = f"{cc}{prefix}{last_digits}"
            full_number = re.sub(r'\D', '', full_number)

            # format consistently
            if full_number.startswith("1") and len(full_number) == 11:
                formatted = f"+1 ({full_number[1:4]}) {full_number[4:7]}-{full_number[7:]}"
            else:
                formatted = f"{cc} {full_number[len(cc_digits):]}"

            confidence = 0.3  # base
            if prefix in self._get_common_prefixes(cc):
                confidence += 0.15
            if len(last_digits) >= 4:
                confidence += 0.20

            candidate = PhoneCandidate(
                full_number=formatted,
                country_code=cc,
                pattern=f"prefix_{prefix}",
                confidence=min(confidence, 0.9),
            )
            identity.phone_candidates.append(candidate)

        # deduplicate
        seen = set()
        unique = []
        for c in identity.phone_candidates:
            digits = re.sub(r'\D', '', c.full_number)
            if digits not in seen:
                seen.add(digits)
                unique.append(c)
        identity.phone_candidates = unique

        return identity

    def _get_carrier_prefixes(self, country_code: str) -> list[str]:
        """get carrier prefixes for a country code"""
        # simplified — in production, loaded from data/phone_prefixes.json
        prefixes = {
            "+1": ["310", "312", "314", "415", "510", "617", "718", "917", "202", "305", "404", "512", "602", "702", "808"],
            "+44": ["7940", "7950", "7710", "7720", "7911", "7800", "7700"],
            "+91": ["700", "701", "900", "901", "800", "801", "600", "601"],
            "+92": ["300", "301", "302", "303", "304", "305", "306", "307", "308", "309", "320", "321", "322", "323", "330", "331", "332", "333", "334", "340", "341", "342", "343", "344", "345"],
            "+86": ["130", "131", "132", "133", "134", "135", "136", "137", "138", "139", "150", "151", "152", "153", "155", "156", "157", "158", "159", "180", "181", "182", "183", "184", "185", "186", "187", "188", "189"],
        }

        return prefixes.get(country_code, [f"{i:03d}" for i in range(100, 999)])

    def _get_common_prefixes(self, country_code: str) -> list[str]:
        """most common prefixes for a country"""
        common = {
            "+1": ["310", "415", "917", "202", "512"],
            "+44": ["7940", "7911", "7700"],
            "+91": ["900", "800", "700"],
            "+92": ["300", "301", "321", "333", "345"],
        }
        return common.get(country_code, [])

    # ─── cross-reference ───────────────────────────────────────────

    def _cross_reference_handles(
        self,
        identity: ReconstructedIdentity,
        known_handles: list[str],
    ) -> ReconstructedIdentity:
        """cross-reference email candidates with known handles from other platforms"""
        for handle in known_handles:
            handle_clean = handle.lower().lstrip("@")
            for candidate in identity.email_candidates:
                local = candidate.email.split("@")[0].lower()
                # if handle appears in email local part, boost confidence
                if handle_clean in local or local in handle_clean:
                    candidate.confidence = min(0.95, candidate.confidence + 0.15)
                    candidate.match_details["cross_ref_handle"] = handle

        return identity

    # ─── helpers ───────────────────────────────────────────────────

    def _get_common_nickname(self, name: str) -> str:
        """get common nickname for a given name"""
        nicknames = {
            "john": "johnny", "jonathan": "jon", "william": "will",
            "robert": "rob", "james": "jim", "richard": "rick",
            "michael": "mike", "david": "dave", "joseph": "joe",
            "thomas": "tom", "christopher": "chris", "daniel": "dan",
            "matthew": "matt", "anthony": "tony", "andrew": "andy",
            "joshua": "josh", "nicholas": "nick", "benjamin": "ben",
            "samuel": "sam", "nathaniel": "nate", "alexander": "alex",
            "zachary": "zach", "gregory": "greg", "patrick": "pat",
            "timothy": "tim", "stephen": "steve", "jeffrey": "jeff",
            "katherine": "kate", "elizabeth": "liz", "jennifer": "jen",
            "jessica": "jess", "stephanie": "steph", "rebecca": "becky",
            "kimberly": "kim", "patricia": "pat", "deborah": "deb",
            "sandra": "sandy", "victoria": "vicky", "margaret": "meg",
        }
        return nicknames.get(name.lower(), name)

    def _load_common_names(self) -> dict:
        """load common first/last names (simplified)"""
        return {}  # could load from data files if needed

    def verify_email_exists(
        self,
        email: str,
        proxy: Optional[str] = None,
    ) -> bool:
        """
        verify if an email has an instagram account
        hit instagram lookup endpoint with email
        note: this is rate limited and may trigger alerts
        """
        # this would call instagram's accounts/lookup with email
        # keeping it as a placeholder — actual implementation depends on endpoint availability
        return False  # stub — implement if needed