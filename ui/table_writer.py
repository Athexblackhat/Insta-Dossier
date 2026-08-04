"""
table writer — formatted terminal tables for results display
handles: linked platforms table, email candidates table,
         contact info table, risk assessment panel
"""

from .colors import Colors


class TableWriter:
    """writes formatted tables to the terminal"""

    @classmethod
    def linked_platforms(cls, platforms: list[dict], max_rows: int = 15):
        """display linked platforms table"""
        if not platforms:
            print(f"  {Colors.muted('  No linked platforms found.')}")
            return

        print(f"  {Colors.bold('🔗 LINKED PLATFORMS')}")
        print(f"  {Colors.muted('─' * 55)}")
        print(f"  {Colors.dim('  PLATFORM':<16} {'HANDLE':<22} {'VERIFIED':<10} {'CONF':>6}")
        print(f"  {Colors.muted('  ' + '─' * 53)}")

        for p in platforms[:max_rows]:
            platform = p.get("platform", "unknown")
            handle = p.get("handle", "")
            verified = Colors.success("✓ yes") if p.get("verified") else Colors.muted("○ no")
            confidence = p.get("confidence", 0)
            conf_bar = cls._confidence_bar(confidence)

            print(f"  {Colors.secondary(platform):<16} {Colors.info(handle[:20]):<22} {verified:<10} {conf_bar}")

        if len(platforms) > max_rows:
            print(f"  {Colors.muted(f'  ... and {len(platforms) - max_rows} more')}")
        print()

    @classmethod
    def email_candidates(cls, candidates: list[dict], max_rows: int = 10):
        """display email reconstruction candidates"""
        if not candidates:
            return

        print(f"  {Colors.bold('📧 EMAIL CANDIDATES')}")
        print(f"  {Colors.muted('─' * 55)}")
        print(f"  {Colors.dim('  EMAIL':<32} {'CONFIDENCE':<14} {'PATTERN':>8}")
        print(f"  {Colors.muted('  ' + '─' * 53)}")

        for c in candidates[:max_rows]:
            email = c.get("email", "")
            confidence = c.get("confidence", 0)
            pattern = c.get("pattern", c.get("pattern_used", ""))
            conf_bar = cls._confidence_bar(confidence)
            print(f"  {Colors.info(email[:30]):<32} {conf_bar:<14} {Colors.muted(pattern):>8}")

        print()

    @classmethod
    def contact_info(cls, contact: dict):
        """display contact information summary"""
        print(f"  {Colors.bold('📋 CONTACT INTELLIGENCE')}")
        print(f"  {Colors.muted('─' * 55)}")

        emails = contact.get("emails_discovered", [])
        if emails:
            for e in emails:
                source = e.get("source", "unknown")
                email = e.get("email", "")
                print(f"  {Colors.success('✉')} {Colors.info(email)} {Colors.muted(f'({source})')}")
        else:
            print(f"  {Colors.muted('  No emails discovered.')}")

        masked_email = contact.get("masked_email", "")
        if masked_email:
            print(f"  {Colors.warning('◌')} Masked: {Colors.secondary(masked_email)}")

        masked_phone = contact.get("masked_phone", "")
        if masked_phone:
            print(f"  {Colors.warning('◌')} Masked: {Colors.secondary(masked_phone)}")

        print()

    @classmethod
    def risk_assessment(cls, risk: dict):
        """display risk assessment panel"""
        privacy = risk.get("privacy_score", "UNKNOWN")
        exposure = risk.get("data_exposure", "UNKNOWN")
        osint_val = risk.get("osint_value", "UNKNOWN")
        account = risk.get("account_type", "UNKNOWN")
        flags = risk.get("flags", [])

        privacy_color = {
            "LOW": Colors.success, "MEDIUM": Colors.warning,
            "HIGH": Colors.error, "CRITICAL": Colors.error,
        }.get(privacy, Colors.info)

        print(f"  {Colors.bold('🛡 RISK ASSESSMENT')}")
        print(f"  {Colors.muted('─' * 55)}")
        print(f"  {'Privacy Score:':<22} {privacy_color(privacy)}")
        print(f"  {'Data Exposure:':<22} {Colors.info(exposure)}")
        print(f"  {'OSINT Value:':<22} {Colors.info(osint_val)}")
        print(f"  {'Account Type:':<22} {Colors.secondary(account)}")

        if flags:
            print(f"  {'Flags:':<22} {Colors.warning(', '.join(flags[:5]))}")
            if len(flags) > 5:
                print(f"  {'':<22} {Colors.muted(f'+ {len(flags) - 5} more')}")

        print()

    @classmethod
    def summary_box(cls, summary: dict):
        """display the final summary box"""
        text = summary.get("text", "")
        risk = summary.get("risk_level", "UNKNOWN")
        data_points = summary.get("data_points_collected", 0)

        risk_color = {
            "LOW": Colors.success, "MEDIUM": Colors.warning,
            "HIGH": Colors.error, "CRITICAL": Colors.error,
        }.get(risk, Colors.info)

        print(f"  {Colors.secondary('─' * 60)}")
        print(f"  {Colors.bold('SUMMARY:')} {Colors.info(text[:100])}")
        print(f"  Risk: {risk_color(risk)} | Data Points: {Colors.highlight(str(data_points))}")
        print(f"  {Colors.secondary('─' * 60)}")
        print()

    @classmethod
    def bio_extracts(cls, extracts: dict):
        """display bio extraction results"""
        locations = extracts.get("extracted_locations", [])
        occupations = extracts.get("occupations", [])
        social = extracts.get("social_handles", {})

        if not any([locations, occupations, social]):
            return

        print(f"  {Colors.bold('🔍 BIO ANALYSIS')}")
        print(f"  {Colors.muted('─' * 55)}")

        if locations:
            print(f"  {Colors.tag('📍')} Locations: {Colors.info(', '.join(locations[:5]))}")

        if occupations:
            print(f"  {Colors.tag('💼')} Occupation: {Colors.info(', '.join(occupations[:3]))}")

        # social handles summary
        social_count = sum(len(v) for v in social.values() if v)
        if social_count:
            active_platforms = [k for k, v in social.items() if v]
            print(f"  {Colors.tag('🔗')} {social_count} handles across {len(active_platforms)} platforms")

        print()

    # ─── helpers ───────────────────────────────────────────────────

    @classmethod
    def _confidence_bar(cls, confidence: float) -> str:
        """visual confidence bar"""
        if confidence >= 0.9:
            return Colors.success(f"████ {confidence:.0%}")
        elif confidence >= 0.7:
            return Colors.secondary(f"███░ {confidence:.0%}")
        elif confidence >= 0.5:
            return Colors.warning(f"██░░ {confidence:.0%}")
        elif confidence >= 0.3:
            return Colors.warning(f"█░░░ {confidence:.0%}")
        else:
            return Colors.muted(f"░░░░ {confidence:.0%}")

    @classmethod
    def horizontal_rule(cls, width: int = 60):
        """print a horizontal rule"""
        print(f"  {Colors.muted('─' * width)}")