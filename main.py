#!/usr/bin/env python3
"""
insta_dossier — instagram osint dossier generator
usage: python main.py --target john_doe_ [--mode full] [--export json]
"""

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

import yaml

# ─── bootstrap logging ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ─── CLI ────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        prog="insta_dossier",
        description="instagram osint dossier generator — extract, map, reconstruct, export",
        epilog="passive by default. active modes may trigger notifications.",
    )

    parser.add_argument("--target", "-t", help="target instagram username or profile URL")
    parser.add_argument("--batch", "-b", help="file with list of usernames (one per line)")
    parser.add_argument("--config", "-c", default="config.yaml", help="config file path")
    parser.add_argument(
        "--mode", "-m",
        choices=["passive", "active", "full"],
        default="passive",
        help="extraction mode (default: passive)",
    )
    parser.add_argument("--export", "-e", choices=["json", "html"], default="json", help="export format")
    parser.add_argument("--output", "-o", default="output/dossiers", help="output directory")
    parser.add_argument("--proxies", "-p", help="path to socks5 proxy list")
    parser.add_argument("--no-images", action="store_true", help="skip profile picture download")
    parser.add_argument("--no-verify", action="store_true", help="skip link verification")
    parser.add_argument("--no-reconstruct", action="store_true", help="skip identity reconstruction")
    parser.add_argument("--stats", action="store_true", help="show database statistics")
    parser.add_argument("--search", help="search existing targets by name")
    parser.add_argument("--recent", type=int, default=0, help="show N recent dossiers")
    parser.add_argument("--theme", choices=["hacker", "neon", "ocean", "sunset"], default="hacker")
    parser.add_argument("--small-banner", action="store_true", help="use compact banner")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")

    return parser.parse_args()


# ─── config loader ──────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    default_config = {
        "modes": {
            "passive": {"scrape_profile": True, "parse_bio": True, "map_links": True,
                        "enumerate_reset": False, "reconstruct_identity": False, "verify_links": False},
            "active": {"scrape_profile": True, "parse_bio": True, "map_links": True,
                       "enumerate_reset": True, "reconstruct_identity": False, "verify_links": True},
            "full": {"scrape_profile": True, "parse_bio": True, "map_links": True,
                     "enumerate_reset": True, "reconstruct_identity": True, "verify_links": True},
        },
        "network": {"max_retries": 3, "timeout": 15, "max_concurrent_scrapes": 5,
                    "max_concurrent_verifications": 4, "download_images": True},
        "proxies": {"file": "proxies/socks5_list.txt", "rotation_mode": "weighted",
                    "max_failures": 2, "cooldown_seconds": 600, "min_proxies_required": 10,
                    "prefer_residential": True},
        "notifications": {"telegram_bot_token": None, "telegram_chat_id": None,
                         "discord_webhook_url": None, "notify_on_dossier": True,
                         "notify_on_business_email": True, "notify_on_identity": True},
        "database": {"path": "output/insta_dossier.db"},
        "output": {"dir": "output", "pretty_print": True, "max_dossiers_per_target": 10},
    }

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, "r") as f:
            user_config = yaml.safe_load(f) or {}
        for section, values in user_config.items():
            if section in default_config and isinstance(default_config[section], dict) and isinstance(values, dict):
                default_config[section].update(values)
            else:
                default_config[section] = values
        logger.info("config loaded from %s", config_path)
    else:
        logger.warning("config not found — writing defaults to %s", config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)

    return default_config


# ─── tool builder ───────────────────────────────────────────────────

async def build_tool(config: dict, args):
    """initialize all modules and return components dict"""
    from core.profile_scraper import ProfileScraper
    from core.reset_enumerator import ResetEnumerator
    from core.bio_parser import BioParser
    from core.linked_mapper import LinkedMapper
    from core.pattern_reconstructor import PatternReconstructor
    from core.dossier_builder import DossierBuilder
    from network.proxy_rotator import ProxyRotator
    from network.session_manager import SessionManager
    from network.fingerprint_engine import FingerprintEngine
    from storage.db import Database
    from storage.dossier_logger import DossierLogger
    from notifications.alerts import AlertManager
    from ui.colors import Colors, Theme

    components = {}

    # theme
    theme_map = {
        "hacker": Colors.THEME_HACKER, "neon": Colors.THEME_NEON,
        "ocean": Colors.THEME_OCEAN, "sunset": Colors.THEME_SUNSET,
    }
    Colors.set_theme(theme_map.get(args.theme, Colors.THEME_HACKER))

    # database
    db = Database(config["database"]["path"])
    await db.initialize()
    components["db"] = db

    # alerts
    alerts = AlertManager(
        telegram_bot_token=config["notifications"]["telegram_bot_token"],
        telegram_chat_id=config["notifications"]["telegram_chat_id"],
        discord_webhook_url=config["notifications"]["discord_webhook_url"],
        debug_mode=args.verbose,
    )
    await alerts.start()
    components["alerts"] = alerts

    # proxy rotator
    proxy_file = args.proxies or config["proxies"]["file"]
    proxy_rotator = ProxyRotator(
        proxy_file=proxy_file,
        rotation_mode=config["proxies"]["rotation_mode"],
        max_failures=config["proxies"]["max_failures"],
        cooldown_seconds=config["proxies"]["cooldown_seconds"],
        min_proxies_required=config["proxies"]["min_proxies_required"],
        prefer_residential=config["proxies"]["prefer_residential"],
    )
    proxy_count = await proxy_rotator.load_proxies()
    components["proxy_rotator"] = proxy_rotator

    # session manager
    session_manager = SessionManager()
    await session_manager.start()
    components["session_manager"] = session_manager

    # fingerprint engine
    fingerprint_engine = FingerprintEngine()
    components["fingerprint_engine"] = fingerprint_engine

    # dossier logger
    dossier_logger = DossierLogger(
        output_dir=args.output or config["output"]["dir"],
        pretty_print=config["output"]["pretty_print"],
        max_dossiers_per_target=config["output"]["max_dossiers_per_target"],
    )
    components["dossier_logger"] = dossier_logger

    # profile scraper
    profile_scraper = ProfileScraper(
        proxy_rotator=proxy_rotator,
        session_manager=session_manager,
        fingerprint_engine=fingerprint_engine,
        output_dir=args.output or config["output"]["dir"],
        download_images=not args.no_images,
        max_retries=config["network"]["max_retries"],
        timeout=config["network"]["timeout"],
    )
    components["scraper"] = profile_scraper

    # reset enumerator
    reset_enumerator = ResetEnumerator(
        proxy_rotator=proxy_rotator,
        session_manager=session_manager,
        fingerprint_engine=fingerprint_engine,
        max_retries=2,
        timeout=config["network"]["timeout"],
    )
    components["enumerator"] = reset_enumerator

    # bio parser (no dependencies)
    components["bio_parser"] = BioParser()

    # linked mapper
    linked_mapper = LinkedMapper(
        proxy_rotator=proxy_rotator,
        session_manager=session_manager,
        verify_links=config["modes"]["full"].get("verify_links", False) and not args.no_verify,
        expand_aggregators=True,
        timeout=config["network"]["timeout"],
        max_concurrent_verifications=config["network"]["max_concurrent_verifications"],
    )
    components["linked_mapper"] = linked_mapper

    # pattern reconstructor
    components["reconstructor"] = PatternReconstructor()

    # dossier builder
    dossier_builder = DossierBuilder(
        output_dir=args.output or config["output"]["dir"],
        pretty_print=config["output"]["pretty_print"],
        include_raw=args.verbose,
    )
    components["dossier_builder"] = dossier_builder

    components["config"] = config
    components["proxy_count"] = proxy_count
    return components


# ─── main commands ──────────────────────────────────────────────────

async def cmd_stats(components: dict):
    """show database statistics"""
    from ui.colors import Colors
    from ui.table_writer import TableWriter

    db = components["db"]
    proxy_rotator = components["proxy_rotator"]

    stats = await db.get_stats()
    proxy_stats = await proxy_rotator.get_pool_stats()
    output_size = await components["dossier_logger"].get_output_size()

    print()
    print(f"  {Colors.highlight('═' * 50)}")
    print(f"  {Colors.bold('  INSTA_DOSSIER — STATISTICS')}")
    print(f"  {Colors.highlight('═' * 50)}")
    print(f"  {Colors.info('Targets Investigated:')}    {stats['total_targets']}")
    print(f"  {Colors.info('Dossiers Generated:')}     {stats['total_dossiers']}")
    print(f"  {Colors.info('High Risk Targets:')}      {stats['high_risk_targets']}")
    print(f"  {Colors.info('Business Accounts:')}      {stats['business_accounts']}")
    print(f"  {Colors.info('Emails Discovered:')}      {stats['total_emails_discovered']}")
    print(f"  {Colors.info('Platforms Mapped:')}       {stats['total_platforms_mapped']}")
    print(f"  {Colors.muted('─' * 50)}")
    print(f"  {Colors.info('Proxies Available:')}      {proxy_stats['available']}/{proxy_stats['total']}")
    print(f"  {Colors.info('Output Size:')}            {output_size['total_size_formatted']}")
    print(f"  {Colors.info('Dossier Files:')}          {output_size['dossier_count']}")
    print(f"  {Colors.info('Images Downloaded:')}      {output_size['image_count']}")
    print(f"  {Colors.highlight('═' * 50)}")
    print()


async def cmd_search(components: dict, query: str):
    """search targets in database"""
    from ui.colors import Colors

    db = components["db"]
    results = await db.search_targets(query)

    if not results:
        print(f"  {Colors.muted('No targets found matching:')} {query}")
        return

    print(f"  {Colors.bold(f'Targets matching \"{query}\":')} ({len(results)} found)")
    print(f"  {Colors.muted('─' * 55)}")
    for r in results[:20]:
        risk = r.get("privacy_risk", "—") or "—"
        risk_color = {"LOW": Colors.success, "MEDIUM": Colors.warning,
                      "HIGH": Colors.error, "CRITICAL": Colors.error}.get(risk, Colors.muted)
        print(f"  {Colors.secondary('@' + r['username']):<28} {r.get('full_name', '—') or '—':<20} {risk_color(risk):<12} {Colors.muted(r.get('last_scraped_at', '')[:10] or '—')}")
    print()


async def cmd_recent(components: dict, count: int):
    """show recent dossiers"""
    from ui.colors import Colors

    db = components["db"]
    dossiers = await db.get_recent_dossiers(count)

    if not dossiers:
        print(f"  {Colors.muted('No dossiers generated yet.')}")
        return

    print(f"  {Colors.bold(f'Recent Dossiers:')} ({len(dossiers)})")
    print(f"  {Colors.muted('─' * 55)}")
    for d in dossiers:
        risk = d.get("risk_level", "—") or "—"
        risk_color = {"LOW": Colors.success, "MEDIUM": Colors.warning,
                      "HIGH": Colors.error, "CRITICAL": Colors.error}.get(risk, Colors.muted)
        print(f"  {Colors.secondary('@' + d['username']):<28} {risk_color(risk):<12} {Colors.info(str(d.get('emails_found', 0)) + ' emails'):<14} {Colors.muted(d.get('generated_at', '')[:10] or '—')}")
    print()


async def cmd_target(components: dict, target: str, mode: str, args):
    """run full extraction on a single target"""
    from ui.banner import Banner
    from ui.progress import ProgressTracker
    from ui.table_writer import TableWriter
    from ui.colors import Colors

    config = components["config"]
    mode_config = config["modes"].get(mode, config["modes"]["passive"])

    proxy_count = components.get("proxy_count", 0)
    Banner.display_simple()
    Banner.display_target_header(target, mode, proxy_count)

    tracker = ProgressTracker(use_rich=True)
    tracker.start()
    total_phases = sum(1 for v in mode_config.values() if v)
    phase_num = 0
    start_time = time.monotonic()

    dossier_id = f"dossier_{target}_{int(time.time())}"
    extraction_summary = {}

    # ─── phase 1: profile scraping ─────────────────────────────────
    if mode_config.get("scrape_profile"):
        phase_num += 1
        Banner.display_phase_header(phase_num, total_phases, "Public Profile Scraping")
        tracker.start_phase(phase_num, total_phases, "Profile Scraping")

        scraper = components["scraper"]
        profile = await scraper.scrape(target)

        if profile and profile.user_id:
            tracker.add_result("✓", f"full_name: {profile.full_name or 'N/A'}")
            tracker.add_result("✓", f"followers: {profile.follower_count:,}")
            tracker.add_result("✓", f"following: {profile.following_count:,}")
            tracker.add_result("✓", f"posts: {profile.media_count}")

            if profile.is_business:
                tracker.add_result("✓", f"business: {profile.business_category}")
                if profile.business_email:
                    tracker.add_result("✓", f"business_email: {profile.business_email}")
                    if config["notifications"].get("notify_on_business_email"):
                        await components["alerts"].business_email_found(target, profile.business_email)
            if profile.is_verified:
                tracker.add_result("✓", "verified: true")
            if profile.external_url:
                tracker.add_result("✓", f"external_url: {profile.external_url}")

            await components["db"].save_target(target, {
                "user_id": profile.user_id, "full_name": profile.full_name,
                "is_business": profile.is_business, "is_verified": profile.is_verified,
                "follower_count": profile.follower_count, "following_count": profile.following_count,
                "media_count": profile.media_count, "business_email": profile.business_email,
                "business_phone": profile.business_phone,
            })
            tracker.complete_phase()
            extraction_summary["profile"] = {"status": "success", "followers": profile.follower_count}
        else:
            tracker.add_error("profile not found or inaccessible")
            tracker.fail_phase("profile not found")
            tracker.finish()
            return
    else:
        profile = None

    # ─── phase 2: bio parsing ──────────────────────────────────────
    bio_extracts = None
    if mode_config.get("parse_bio") and profile:
        phase_num += 1
        Banner.display_phase_header(phase_num, total_phases, "Bio Parsing & Pattern Extraction")
        tracker.start_phase(phase_num, total_phases, "Bio Parsing")

        bio_parser = components["bio_parser"]
        bio_extracts = bio_parser.parse(
            bio_text=profile.biography,
            full_name=profile.full_name,
            username=profile.username,
            external_url=profile.external_url,
        )

        if bio_extracts.emails:
            tracker.add_result("✓", f"emails: {', '.join(bio_extracts.emails[:3])}")
        if bio_extracts.phones:
            tracker.add_result("✓", f"phones: {', '.join(bio_extracts.phones[:2])}")
        if bio_extracts.locations:
            tracker.add_result("✓", f"locations: {', '.join(bio_extracts.locations[:3])}")
        if bio_extracts.occupations:
            tracker.add_result("✓", f"occupation: {', '.join(bio_extracts.occupations[:2])}")

        social_count = sum(len(v) for v in [
            bio_extracts.snapchat, bio_extracts.telegram, bio_extracts.discord,
            bio_extracts.twitter, bio_extracts.tiktok, bio_extracts.youtube,
            bio_extracts.github, bio_extracts.twitch, bio_extracts.reddit,
        ] if v)
        if social_count:
            tracker.add_result("✓", f"social handles: {social_count} found")

        tracker.complete_phase()
        extraction_summary["bio"] = {"emails": len(bio_extracts.emails), "social": social_count}

        TableWriter.bio_extracts({
            "extracted_locations": bio_extracts.locations,
            "occupations": bio_extracts.occupations,
            "social_handles": {
                k: v for k, v in {
                    "snapchat": bio_extracts.snapchat, "telegram": bio_extracts.telegram,
                    "discord": bio_extracts.discord, "twitter": bio_extracts.twitter,
                    "tiktok": bio_extracts.tiktok, "youtube": bio_extracts.youtube,
                    "github": bio_extracts.github, "twitch": bio_extracts.twitch,
                }.items() if v
            },
        })

    # ─── phase 3: reset enumeration (active) ───────────────────────
    reset_data = None
    if mode_config.get("enumerate_reset"):
        phase_num += 1
        Banner.display_phase_header(phase_num, total_phases, "Password Reset Enumeration")
        tracker.start_phase(phase_num, total_phases, "Reset Enumeration")

        enumerator = components["enumerator"]
        reset_data = await enumerator.enumerate(target)

        if reset_data and reset_data.account_exists:
            if reset_data.masked_email:
                tracker.add_result("✓", f"masked_email: {reset_data.masked_email}")
            if reset_data.masked_phone:
                tracker.add_result("✓", f"masked_phone: {reset_data.masked_phone}")
            if reset_data.email_provider:
                tracker.add_result("✓", f"provider: {reset_data.email_provider}")
            if reset_data.phone_country_name:
                tracker.add_result("✓", f"country: {reset_data.phone_country_name}")
            tracker.complete_phase()
            extraction_summary["reset"] = {
                "has_email": reset_data.has_email,
                "has_phone": reset_data.has_phone,
            }
        elif reset_data and reset_data.account_locked:
            tracker.add_error("account locked — too many reset attempts")
            tracker.fail_phase("account locked")
        else:
            tracker.add_result("⚠", "no masked data available")
            tracker.complete_phase()

    # ─── phase 4: linked account mapping ───────────────────────────
    linked_accounts = None
    if mode_config.get("map_links"):
        phase_num += 1
        Banner.display_phase_header(phase_num, total_phases, "Linked Account Mapping")
        tracker.start_phase(phase_num, total_phases, "Linked Mapping")

        linked_mapper = components["linked_mapper"]
        linked_mapper.verify_links = mode_config.get("verify_links", False) and not args.no_verify

        linked_accounts = await linked_mapper.map(
            username=target,
            bio_extracts=bio_extracts,
            external_url=profile.external_url if profile else "",
            bio_links=profile.bio_links if profile else [],
            profile_data=profile,
        )

        verified = linked_accounts.get_verified()
        tracker.add_result("✓", f"platforms found: {linked_accounts.total_platforms_found}")
        if verified:
            tracker.add_result("✓", f"verified: {len(verified)}")

        if linked_accounts.link_aggregators:
            total_expanded = sum(len(a.get("expanded_links", [])) for a in linked_accounts.link_aggregators)
            tracker.add_result("✓", f"aggregator links expanded: {total_expanded}")

        tracker.complete_phase()
        extraction_summary["linked"] = {"platforms": linked_accounts.total_platforms_found}

        TableWriter.linked_platforms([
            {"platform": p.platform, "handle": p.handle,
             "verified": p.verified, "confidence": p.confidence}
            for p in linked_accounts.platforms[:15]
        ])

        if linked_accounts.total_platforms_found >= 3:
            platforms_list = [p.platform for p in linked_accounts.platforms[:8]]
            await components["alerts"].linked_platforms_found(
                target, linked_accounts.total_platforms_found, platforms_list,
            )

    # ─── phase 5: identity reconstruction ──────────────────────────
    reconstructed = None
    if mode_config.get("reconstruct_identity") and not args.no_reconstruct:
        phase_num += 1
        Banner.display_phase_header(phase_num, total_phases, "Identity Reconstruction")
        tracker.start_phase(phase_num, total_phases, "Identity Reconstruction")

        reconstructor = components["reconstructor"]

        known_handles = []
        if linked_accounts:
            known_handles = [p.handle for p in linked_accounts.platforms if p.verified]

        reconstructed = reconstructor.reconstruct(
            username=target,
            full_name=profile.full_name if profile else "",
            masked_email=reset_data.masked_email if reset_data else "",
            masked_phone=reset_data.masked_phone if reset_data else "",
            email_domain=reset_data.email_provider if reset_data else "",
            email_first_char=reset_data.email_first_char if reset_data else "",
            email_last_chars=reset_data.email_last_chars if reset_data else "",
            phone_country_code=reset_data.phone_country_code if reset_data else "",
            phone_last_digits=reset_data.phone_last_digits if reset_data else "",
            bio_emails=bio_extracts.emails if bio_extracts else [],
            known_handles=known_handles,
        )

        if reconstructed.best_email and reconstructed.best_email.confidence >= 0.5:
            tracker.add_result("✓", f"best email: {reconstructed.best_email.email} ({reconstructed.best_email.confidence:.0%})")
        if reconstructed.best_phone and reconstructed.best_phone.confidence >= 0.5:
            tracker.add_result("✓", f"best phone: {reconstructed.best_phone.full_number}")
        tracker.add_result("✓", f"candidates: {reconstructed.total_email_candidates} emails, {reconstructed.total_phone_candidates} phones")

        tracker.complete_phase()
        extraction_summary["reconstruction"] = {
            "best_email": reconstructed.best_email.email if reconstructed.best_email else None,
            "confidence": reconstructed.best_email.confidence if reconstructed.best_email else 0,
        }

        TableWriter.email_candidates([
            {"email": e.email, "confidence": e.confidence, "pattern": e.pattern_used}
            for e in (reconstructed.email_candidates[:10] if reconstructed else [])
        ])

        if reconstructed.best_email and reconstructed.best_email.confidence >= 0.7:
            await components["alerts"].identity_reconstructed(
                target, reconstructed.best_email.email, reconstructed.best_email.confidence,
            )

    # ─── phase 6: dossier assembly ──────────────────────────────────
    phase_num += 1
    Banner.display_phase_header(phase_num, total_phases, "Dossier Assembly & Export")
    tracker.start_phase(phase_num, total_phases, "Dossier Export")

    dossier_builder = components["dossier_builder"]
    dossier = dossier_builder.build(
        username=target,
        profile=profile,
        reset=reset_data,
        bio=bio_extracts,
        linked=linked_accounts,
        identity=reconstructed,
        profile_pic_path=profile.profile_pic_path if profile else "",
    )

    filepath = dossier_builder.export_json(dossier)
    tracker.add_result("✓", f"dossier saved: {filepath}")

    # save to database
    await components["db"].save_dossier(
        dossier_id=dossier.dossier_id,
        username=target,
        filepath=filepath,
        risk_level=dossier.risk_assessment.get("privacy_score", ""),
        emails=len(dossier.contact.get("emails_discovered", [])),
        phones=len(dossier.contact.get("phones_discovered", [])),
        platforms=len(dossier.linked_platforms),
        identity_reconstructed=bool(
            dossier.identity_reconstruction.get("best_email")
        ),
    )

    await components["db"].update_target_osint(
        target,
        masked_email=reset_data.masked_email if reset_data else "",
        masked_phone=reset_data.masked_phone if reset_data else "",
        linked_platforms_count=len(dossier.linked_platforms),
        privacy_risk=dossier.risk_assessment.get("privacy_score", ""),
        osint_value=dossier.risk_assessment.get("osint_value", ""),
        data_points_collected=dossier.summary.get("data_points_collected", 0),
    )

    tracker.complete_phase()
    extraction_summary["dossier"] = {"filepath": filepath}

    # ─── finish ────────────────────────────────────────────────────
    total_time = time.monotonic() - start_time
    tracker.finish(total_time)

    # display results
    Banner.display_dossier_complete(
        filepath=filepath,
        image_path=profile.profile_pic_path if profile and profile.profile_pic_downloaded else "",
        summary={
            "risk": dossier.risk_assessment.get("privacy_score", "?"),
            "emails": str(len(dossier.contact.get("emails_discovered", []))),
            "platforms": str(len(dossier.linked_platforms)),
            "data_points": str(dossier.summary.get("data_points_collected", 0)),
        },
    )

    TableWriter.contact_info(dossier.contact)
    TableWriter.risk_assessment(dossier.risk_assessment)
    TableWriter.summary_box(dossier.summary)

    # notify
    if config["notifications"].get("notify_on_dossier"):
        await components["alerts"].dossier_complete(
            target, filepath,
            summary={
                "risk": dossier.risk_assessment.get("privacy_score", "?"),
                "data_points": str(dossier.summary.get("data_points_collected", 0)),
            },
        )

    print(f"  {Colors.success('[ ✓ ]')} Dossier complete.")
    print(f"  {Colors.muted(f'[ ⏱  ] Total time: {total_time:.1f}s')}")
    print()


async def cmd_batch(components: dict, batch_file: str, mode: str, args):
    """process multiple targets from a file"""
    from ui.colors import Colors

    batch_path = Path(batch_file)
    if not batch_path.exists():
        print(f"  {Colors.error('Batch file not found:')} {batch_file}")
        return

    targets = [
        line.strip()
        for line in batch_path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not targets:
        print(f"  {Colors.warning('No targets found in batch file.')}")
        return

    print(f"  {Colors.info(f'Batch mode: {len(targets)} targets')}")
    print()

    completed = 0
    failed = 0
    start_time = time.monotonic()

    for i, target in enumerate(targets, 1):
        print(f"  {Colors.secondary(f'[{i}/{len(targets)}]')} Processing @{target}...")
        try:
            await cmd_target(components, target, mode, args)
            completed += 1
        except Exception as e:
            logger.error("batch failed for @%s: %s", target, e)
            print(f"  {Colors.error(f'  ✗ Failed: {e}')}")
            failed += 1

    total_time = time.monotonic() - start_time
    print(f"  {Colors.highlight('═' * 50)}")
    print(f"  {Colors.bold('BATCH COMPLETE')}")
    print(f"  {Colors.success(f'  ✓ {completed} completed')}")
    if failed:
        print(f"  {Colors.error(f'  ✗ {failed} failed')}")
    print(f"  {Colors.muted(f'  ⏱ {total_time:.1f}s')}")
    print()

    await components["alerts"].batch_summary(len(targets), completed, failed, total_time)


# ─── main ───────────────────────────────────────────────────────────

async def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = load_config(args.config)
    components = await build_tool(config, args)

    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("shutdown signal received")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if args.stats:
            await cmd_stats(components)
        elif args.search:
            await cmd_search(components, args.search)
        elif args.recent:
            await cmd_recent(components, args.recent)
        elif args.batch:
            await cmd_batch(components, args.batch, args.mode, args)
        elif args.target:
            await cmd_target(components, args.target, args.mode, args)
        else:
            from ui.banner import Banner
            Banner.display()
            print("  usage: python main.py --target <username>")
            print("         python main.py --batch targets.txt")
            print("         python main.py --stats")
            print("         python main.py --search <query>")
            print()
    except KeyboardInterrupt:
        logger.info("interrupted by user")
    except Exception as e:
        logger.exception("fatal error: %s", e)
        if components.get("alerts"):
            await components["alerts"].error_alert("Fatal Error", str(e))
    finally:
        logger.info("shutting down...")
        if components.get("alerts"):
            await components["alerts"].stop()
        if components.get("session_manager"):
            await components["session_manager"].stop()
        if components.get("scraper"):
            await components["scraper"].close()
        if components.get("enumerator"):
            await components["enumerator"].close()
        if components.get("linked_mapper"):
            await components["linked_mapper"].close()
        if components.get("db"):
            await components["db"].close()
        logger.info("goodbye.")


if __name__ == "__main__":
    asyncio.run(main())