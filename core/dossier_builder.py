"""
dossier builder — combines all modules into final intelligence dossier
takes outputs from profile_scraper, reset_enumerator, bio_parser,
linked_mapper, and pattern_reconstructor
produces structured Dossier dataclass + JSON export
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskAssessment:
    """risk/profile assessment of the target"""
    privacy_score: str = "UNKNOWN"       # LOW / MEDIUM / HIGH — how much they leak
    account_type: str = "PERSONAL"       # PERSONAL / BUSINESS / CREATOR
    data_exposure: str = "UNKNOWN"       # MINIMAL / MODERATE / SIGNIFICANT / CRITICAL
    osint_value: str = "UNKNOWN"         # LOW / MEDIUM / HIGH — overall intel value
    business_risk: str = "NONE"          # NONE / LOW / MEDIUM — if business, risk level
    flags: list[str] = field(default_factory=list)  # specific concerns


@dataclass
class Dossier:
    """complete intelligence dossier for an instagram target"""

    # meta
    dossier_id: str = ""
    target_username: str = ""
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tool_version: str = "1.0.0"

    # profile overview
    profile: dict = field(default_factory=dict)
    account_info: dict = field(default_factory=dict)

    # contact intelligence
    contact: dict = field(default_factory=dict)

    # business intelligence (if applicable)
    business: dict = field(default_factory=dict)

    # bio intelligence
    bio_analysis: dict = field(default_factory=dict)

    # cross-platform mapping
    linked_platforms: dict = field(default_factory=dict)
    platform_details: list = field(default_factory=list)

    # identity reconstruction
    identity_reconstruction: dict = field(default_factory=dict)

    # media
    media: dict = field(default_factory=dict)

    # risk assessment
    risk_assessment: dict = field(default_factory=dict)

    # raw data (optional — for debugging)
    raw_sources: dict = field(default_factory=dict)

    # summary
    summary: dict = field(default_factory=dict)


class DossierBuilder:
    """
    combines all OSINT module outputs into a comprehensive dossier

    usage:
        builder = DossierBuilder(output_dir="output/dossiers")
        dossier = builder.build(
            username="john_doe_",
            profile=profile_data,
            reset=reset_data,
            bio=bio_extracts,
            linked=linked_accounts,
            identity=reconstructed_identity,
        )
        filepath = builder.export_json(dossier)
        # or
        summary = builder.get_summary(dossier)
    """

    def __init__(
        self,
        output_dir: str = "output/dossiers",
        pretty_print: bool = True,
        include_raw: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pretty_print = pretty_print
        self.include_raw = include_raw

    # ─── build dossier ─────────────────────────────────────────────

    def build(
        self,
        username: str,
        profile=None,           # ProfileData
        reset=None,             # ResetData
        bio=None,               # BioExtracts
        linked=None,            # LinkedAccounts
        identity=None,          # ReconstructedIdentity
        profile_pic_path: str = "",
    ) -> Dossier:
        """assemble complete dossier from all module outputs"""

        dossier = Dossier(
            dossier_id=f"dossier_{username}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            target_username=username,
        )

        # 1. profile overview
        if profile:
            dossier.profile = self._build_profile_section(profile)
            dossier.account_info = self._build_account_info(profile)
            dossier.business = self._build_business_section(profile)

        # 2. contact intelligence
        dossier.contact = self._build_contact_section(profile, reset, bio)

        # 3. bio analysis
        if bio:
            dossier.bio_analysis = self._build_bio_section(bio)

        # 4. cross-platform mapping
        if linked:
            dossier.linked_platforms = linked.to_flat_dict()
            dossier.platform_details = self._build_platform_details(linked)

        # 5. identity reconstruction
        if identity:
            dossier.identity_reconstruction = self._build_identity_section(identity)

        # 6. media
        dossier.media = self._build_media_section(profile, profile_pic_path)

        # 7. risk assessment
        dossier.risk_assessment = self._assess_risk(dossier)

        # 8. summary
        dossier.summary = self._build_summary(dossier)

        # 9. raw sources (optional)
        if self.include_raw:
            dossier.raw_sources = self._build_raw_sources(profile, reset, bio, linked, identity)

        logger.info("[dossier] built for @%s", username)
        return dossier

    # ─── section builders ──────────────────────────────────────────

    def _build_profile_section(self, profile) -> dict:
        return {
            "username": profile.username,
            "user_id": profile.user_id,
            "full_name": profile.full_name,
            "biography": profile.biography,
            "pronouns": profile.pronouns,
            "category": profile.category,
            "is_private": profile.is_private,
            "is_verified": profile.is_verified,
            "is_business": profile.is_business,
            "is_professional": profile.is_professional,
            "business_category": profile.business_category,
            "account_type": self._translate_account_type(profile.account_type),
        }

    def _build_account_info(self, profile) -> dict:
        return {
            "follower_count": profile.follower_count,
            "following_count": profile.following_count,
            "media_count": profile.media_count,
            "follower_ratio": (
                round(profile.follower_count / max(profile.following_count, 1), 2)
                if profile.following_count > 0 else "N/A"
            ),
            "account_created_approx": profile.account_created_approx,
            "last_post_date": profile.last_post_date,
            "region": profile.region,
            "external_url": profile.external_url,
            "bio_links": profile.bio_links,
        }

    def _build_contact_section(self, profile, reset, bio) -> dict:
        contact = {
            "emails_discovered": [],
            "phones_discovered": [],
            "masked_email": "",
            "masked_phone": "",
            "email_provider": "",
            "phone_country": "",
            "email_reconstruction_possible": False,
            "phone_reconstruction_possible": False,
        }

        # from reset enumeration
        if reset:
            contact["masked_email"] = reset.masked_email
            contact["masked_phone"] = reset.masked_phone
            contact["email_provider"] = reset.email_provider
            contact["phone_country"] = reset.phone_country_name
            contact["email_reconstruction_possible"] = bool(
                reset.masked_email and reset.email_first_char
            )
            contact["phone_reconstruction_possible"] = bool(
                reset.masked_phone and reset.phone_last_digits
            )

        # from business profile
        if profile:
            if profile.business_email:
                contact["emails_discovered"].append({
                    "email": profile.business_email,
                    "source": "business_profile",
                    "confidence": 1.0,
                })
            if profile.business_phone:
                contact["phones_discovered"].append({
                    "phone": profile.business_phone,
                    "source": "business_profile",
                    "confidence": 1.0,
                })

        # from bio extracts
        if bio:
            for email in bio.emails:
                if email not in [e["email"] for e in contact["emails_discovered"]]:
                    contact["emails_discovered"].append({
                        "email": email,
                        "source": "bio_text",
                        "confidence": 0.85,
                    })
            for phone in bio.phones:
                if phone not in [p["phone"] for p in contact["phones_discovered"]]:
                    contact["phones_discovered"].append({
                        "phone": phone,
                        "source": "bio_text",
                        "confidence": 0.7,
                    })

        return contact

    def _build_business_section(self, profile) -> dict:
        if not profile or not profile.is_business:
            return {"is_business": False}

        return {
            "is_business": True,
            "business_category": profile.business_category,
            "business_email": profile.business_email,
            "business_phone": profile.business_phone,
            "business_address": profile.business_address,
            "business_contact_method": profile.business_contact_method,
            "connected_facebook_page": profile.connected_fb_page,
            "connected_facebook_page_id": profile.connected_fb_page_id,
        }

    def _build_bio_section(self, bio) -> dict:
        return {
            "raw_text": bio.bio_text,
            "extracted_emails": bio.emails,
            "extracted_phones": bio.phones,
            "extracted_locations": bio.locations,
            "extracted_countries": bio.countries,
            "extracted_cities": bio.cities,
            "dates_of_birth": bio.dates_of_birth,
            "age_hints": bio.age_hints,
            "occupations": bio.occupations,
            "social_handles": {
                "snapchat": bio.snapchat,
                "telegram": bio.telegram,
                "discord": bio.discord,
                "signal": bio.signal,
                "whatsapp": bio.whatsapp,
                "twitter": bio.twitter,
                "tiktok": bio.tiktok,
                "youtube": bio.youtube,
                "facebook": bio.facebook,
                "linkedin": bio.linkedin,
                "github": bio.github,
                "twitch": bio.twitch,
                "spotify": bio.spotify,
                "pinterest": bio.pinterest,
                "reddit": bio.reddit,
            },
            "payment_handles": {
                "venmo": bio.venmo,
                "cashapp": bio.cashapp,
                "paypal": bio.paypal,
                "bitcoin": bio.bitcoin,
                "ethereum": bio.ethereum,
            },
            "hashtags": bio.hashtags,
            "mentions": bio.mentions,
            "websites": bio.websites,
            "emoji_flags": bio.emoji_flags,
            "parse_duration_ms": bio.parse_duration_ms,
        }

    def _build_platform_details(self, linked) -> list:
        return [
            {
                "platform": p.platform,
                "handle": p.handle,
                "url": p.url,
                "confidence": p.confidence,
                "verified": p.verified,
                "source": p.source,
                "metadata": p.metadata,
            }
            for p in linked.platforms
        ]

    def _build_identity_section(self, identity) -> dict:
        return {
            "full_name": identity.full_name,
            "masked_email_source": identity.masked_email,
            "masked_phone_source": identity.masked_phone,
            "best_email": (
                {
                    "email": identity.best_email.email,
                    "confidence": identity.best_email.confidence,
                    "pattern": identity.best_email.pattern_used,
                }
                if identity.best_email else None
            ),
            "best_phone": (
                {
                    "phone": identity.best_phone.full_number,
                    "confidence": identity.best_phone.confidence,
                }
                if identity.best_phone else None
            ),
            "email_candidates": [
                {
                    "email": e.email,
                    "confidence": e.confidence,
                    "pattern": e.pattern_used,
                }
                for e in identity.email_candidates[:10]  # top 10
            ],
            "phone_candidates": [
                {
                    "phone": p.full_number,
                    "confidence": p.confidence,
                }
                for p in identity.phone_candidates[:5]  # top 5
            ],
            "total_email_candidates": identity.total_email_candidates,
            "total_phone_candidates": identity.total_phone_candidates,
            "high_confidence_count": identity.high_confidence_count,
        }

    def _build_media_section(self, profile, profile_pic_path: str) -> dict:
        media = {
            "profile_picture": {
                "url": "",
                "url_hd": "",
                "downloaded": False,
                "local_path": "",
            }
        }

        if profile:
            media["profile_picture"]["url"] = profile.profile_pic_url
            media["profile_picture"]["url_hd"] = profile.profile_pic_url_hd
            media["profile_picture"]["hash"] = profile.profile_pic_hash
            media["profile_picture"]["downloaded"] = profile.profile_pic_downloaded
            media["profile_picture"]["local_path"] = profile.profile_pic_path or profile_pic_path

        return media

    # ─── risk assessment ───────────────────────────────────────────

    def _assess_risk(self, dossier: Dossier) -> dict:
        """assess target's privacy exposure and OSINT value"""
        assessment = RiskAssessment()
        flags = []

        # account type
        if dossier.account_info.get("is_business"):
            assessment.account_type = "BUSINESS"
        elif dossier.account_info.get("is_professional"):
            assessment.account_type = "CREATOR"
        else:
            assessment.account_type = "PERSONAL"

        # privacy score — how much they leak
        leak_score = 0

        if dossier.contact.get("emails_discovered"):
            leak_score += 30
            flags.append("EMAIL_IN_BIO")
        if dossier.contact.get("phones_discovered"):
            leak_score += 25
            flags.append("PHONE_IN_BIO")
        if dossier.contact.get("masked_email"):
            leak_score += 10
        if dossier.contact.get("masked_phone"):
            leak_score += 10
        if dossier.contact.get("email_reconstruction_possible"):
            leak_score += 15
            flags.append("EMAIL_RECONSTRUCTABLE")
        if dossier.bio_analysis.get("dates_of_birth"):
            leak_score += 15
            flags.append("DOB_EXPOSED")
        if dossier.bio_analysis.get("extracted_locations"):
            leak_score += 10
            flags.append("LOCATION_EXPOSED")
        if dossier.linked_platforms:
            leak_score += min(len(dossier.linked_platforms) * 5, 25)
        if dossier.business.get("is_business"):
            leak_score += 20
            flags.append("BUSINESS_CONTACT_EXPOSED")
        if dossier.bio_analysis.get("payment_handles"):
            for platform, handles in dossier.bio_analysis["payment_handles"].items():
                if handles:
                    leak_score += 5
                    flags.append(f"PAYMENT_{platform.upper()}_EXPOSED")

        if leak_score >= 60:
            assessment.privacy_score = "CRITICAL"
        elif leak_score >= 35:
            assessment.privacy_score = "HIGH"
        elif leak_score >= 15:
            assessment.privacy_score = "MEDIUM"
        else:
            assessment.privacy_score = "LOW"

        # data exposure
        if leak_score >= 50:
            assessment.data_exposure = "CRITICAL"
        elif leak_score >= 30:
            assessment.data_exposure = "SIGNIFICANT"
        elif leak_score >= 10:
            assessment.data_exposure = "MODERATE"
        else:
            assessment.data_exposure = "MINIMAL"

        # OSINT value
        value_score = 0
        value_score += len(dossier.linked_platforms) * 8
        value_score += len(dossier.contact.get("emails_discovered", [])) * 15
        value_score += len(dossier.identity_reconstruction.get("email_candidates", [])) * 3
        if dossier.business.get("connected_facebook_page"):
            value_score += 20
        if dossier.bio_analysis.get("occupations"):
            value_score += 10

        if value_score >= 80:
            assessment.osint_value = "HIGH"
        elif value_score >= 40:
            assessment.osint_value = "MEDIUM"
        else:
            assessment.osint_value = "LOW"

        # business risk
        if dossier.business.get("is_business"):
            if dossier.business.get("business_email") and dossier.business.get("business_phone"):
                assessment.business_risk = "MEDIUM"
            else:
                assessment.business_risk = "LOW"
        else:
            assessment.business_risk = "NONE"

        assessment.flags = flags

        return {
            "privacy_score": assessment.privacy_score,
            "account_type": assessment.account_type,
            "data_exposure": assessment.data_exposure,
            "osint_value": assessment.osint_value,
            "business_risk": assessment.business_risk,
            "flags": assessment.flags,
            "leak_score": leak_score,
            "osint_value_score": value_score,
        }

    # ─── summary ───────────────────────────────────────────────────

    def _build_summary(self, dossier: Dossier) -> dict:
        """one-paragraph executive summary"""
        parts = []

        username = dossier.target_username
        name = dossier.profile.get("full_name", username)
        account_type = dossier.risk_assessment.get("account_type", "PERSONAL").lower()

        parts.append(
            f"@{username} ({name}) is a {account_type} account "
            f"with {dossier.account_info.get('follower_count', 0):,} followers."
        )

        # privacy
        privacy = dossier.risk_assessment.get("privacy_score", "UNKNOWN")
        parts.append(f"Privacy exposure is {privacy}.")

        # contact
        emails = dossier.contact.get("emails_discovered", [])
        if emails:
            parts.append(f"{len(emails)} email(s) were discovered.")

        masked = dossier.contact.get("masked_email", "")
        if masked and not emails:
            parts.append(f"Masked email found: {masked}.")

        # reconstruction
        best = dossier.identity_reconstruction.get("best_email")
        if best and best.get("confidence", 0) >= 0.7:
            parts.append(
                f"Identity likely reconstructable — "
                f"best candidate: {best['email']} ({best['confidence']:.0%} confidence)."
            )

        # linked
        linked_count = len(dossier.linked_platforms)
        if linked_count > 0:
            platforms = list(dossier.linked_platforms.keys())[:5]
            parts.append(f"Mapped to {linked_count} platforms ({', '.join(platforms)}).")

        return {
            "text": " ".join(parts),
            "target": f"@{username}",
            "risk_level": privacy,
            "data_points_collected": self._count_data_points(dossier),
        }

    def _count_data_points(self, dossier: Dossier) -> int:
        """count total discrete data points in dossier"""
        count = 0
        count += len(dossier.contact.get("emails_discovered", []))
        count += len(dossier.contact.get("phones_discovered", []))
        count += len(dossier.linked_platforms)
        count += len(dossier.identity_reconstruction.get("email_candidates", []))
        count += len(dossier.identity_reconstruction.get("phone_candidates", []))
        count += len(dossier.bio_analysis.get("extracted_locations", []))
        count += len(dossier.bio_analysis.get("social_handles", {}).get("twitter", []))
        count += len(dossier.bio_analysis.get("social_handles", {}).get("tiktok", []))
        count += len(dossier.bio_analysis.get("occupations", []))
        count += 1 if dossier.business.get("is_business") else 0
        return count

    # ─── raw sources ───────────────────────────────────────────────

    def _build_raw_sources(self, profile, reset, bio, linked, identity) -> dict:
        """include raw module outputs for debugging"""
        raw = {}
        if profile:
            raw["profile_raw_json"] = profile.raw_json if hasattr(profile, "raw_json") else {}
        if reset:
            raw["reset_data"] = {
                "masked_email": reset.masked_email,
                "masked_phone": reset.masked_phone,
            }
        if bio:
            raw["bio_extracts"] = {
                "emails": bio.emails,
                "phones": bio.phones,
                "locations": bio.locations,
            }
        if linked:
            raw["linked_platforms"] = [
                {"platform": p.platform, "handle": p.handle, "verified": p.verified}
                for p in linked.platforms
            ]
        if identity:
            raw["identity_top_candidates"] = [
                {"email": e.email, "confidence": e.confidence}
                for e in identity.email_candidates[:5]
            ]
        return raw

    # ─── export ────────────────────────────────────────────────────

    def export_json(self, dossier: Dossier, filename: str = "") -> str:
        """export dossier as JSON file, returns filepath"""
        if not filename:
            safe_username = dossier.target_username.replace("/", "_").replace("\\", "_")
            timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{safe_username}_{timestamp}.json"

        filepath = self.output_dir / filename

        dossier_dict = {
            "dossier_id": dossier.dossier_id,
            "target_username": dossier.target_username,
            "generated_at": dossier.generated_at,
            "tool_version": dossier.tool_version,
            "profile": dossier.profile,
            "account_info": dossier.account_info,
            "contact": dossier.contact,
            "business": dossier.business,
            "bio_analysis": dossier.bio_analysis,
            "linked_platforms": dossier.linked_platforms,
            "platform_details": dossier.platform_details,
            "identity_reconstruction": dossier.identity_reconstruction,
            "media": dossier.media,
            "risk_assessment": dossier.risk_assessment,
            "summary": dossier.summary,
        }

        if self.include_raw:
            dossier_dict["raw_sources"] = dossier.raw_sources

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                dossier_dict,
                f,
                indent=2 if self.pretty_print else None,
                ensure_ascii=False,
                default=str,
            )

        logger.info("[dossier] exported to %s", filepath)
        return str(filepath)

    def get_terminal_summary(self, dossier: Dossier) -> str:
        """generate a pretty terminal-friendly summary"""
        lines = []
        lines.append("═" * 60)
        lines.append(f"  DOSSIER: @{dossier.target_username}")
        lines.append("═" * 60)

        if dossier.profile:
            lines.append(f"  Name:        {dossier.profile.get('full_name', 'N/A')}")
            lines.append(f"  Followers:   {dossier.account_info.get('follower_count', 0):,}")
            lines.append(f"  Account:     {dossier.risk_assessment.get('account_type', 'UNKNOWN')}")

        lines.append(f"  Risk:        {dossier.risk_assessment.get('privacy_score', 'UNKNOWN')}")
        lines.append(f"  OSINT Value: {dossier.risk_assessment.get('osint_value', 'UNKNOWN')}")
        lines.append("-" * 60)

        emails = dossier.contact.get("emails_discovered", [])
        if emails:
            lines.append(f"  ✉ Emails:    {len(emails)} found")
            for e in emails[:3]:
                lines.append(f"    → {e['email']} ({e['source']})")

        best = dossier.identity_reconstruction.get("best_email")
        if best and not emails:
            lines.append(f"  ✉ Best Guess: {best['email']} ({best['confidence']:.0%})")

        linked = len(dossier.linked_platforms)
        if linked:
            lines.append(f"  🔗 Platforms: {linked} linked")
            for platform, data in list(dossier.linked_platforms.items())[:5]:
                handle = data.get("handle", "") if isinstance(data, dict) else data
                lines.append(f"    → {platform}: {handle}")

        lines.append("-" * 60)
        lines.append(f"  {dossier.summary.get('text', '')}")
        lines.append("═" * 60)

        return "\n".join(lines)

    # ─── helpers ───────────────────────────────────────────────────

    def _translate_account_type(self, account_type: str) -> str:
        """translate numeric account type to readable string"""
        types = {
            "1": "PERSONAL",
            "2": "BUSINESS",
            "3": "CREATOR",
            "4": "MEDIA_PUBLISHER",
        }
        return types.get(str(account_type), f"UNKNOWN ({account_type})")