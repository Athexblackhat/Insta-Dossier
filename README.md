# insta_dossier

<div align="center">

> **instagram osint dossier generator** — target → extract → map → reconstruct → export

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-educational%20use%20only-red.svg)](#disclaimer)
[![Rich](https://img.shields.io/badge/terminal-rich-purple.svg)](https://github.com/Textualize/rich)

<img src="https://img.shields.io/badge/platform-instagram-E4405F?logo=instagram&logoColor=white" alt="instagram">
<img src="https://img.shields.io/badge/proxy-socks4%20%7C%20socks5-555" alt="socks proxy">
<img src="https://img.shields.io/badge/notifications-telegram%20%7C%20discord-555" alt="notifications">
<img src="https://img.shields.io/badge/export-json-555" alt="json export">

</div>

---

## overview

**insta_dossier** extracts publicly available instagram data, enumerates masked contact information, maps cross-platform identities, and reconstructs likely email addresses and phone numbers — all packaged into a structured intelligence dossier.

| mode | description | risk to target |
|------|-------------|:---:|
| `passive` | scrape profile + parse bio + map linked platforms | none |
| `active` | adds password reset enumeration (masked email/phone) | low |
| `full` | adds identity reconstruction (email + phone candidates) | low |

---

## features

- ✅ three extraction modes — passive, active, full
- ✅ public profile scraping — 3 fallback endpoints
- ✅ business contact extraction — full unmasked email + phone
- ✅ bio regex engine — 15 social + 5 payment platforms
- ✅ password reset enumeration — masked email + phone with carrier detection
- ✅ link aggregator expansion — linktree, beacons, campsite, bento, carrd + more
- ✅ cross-platform mapping — 38 platforms detected + verified
- ✅ identity reconstruction — 16 email patterns, 6-factor confidence scoring
- ✅ 50+ country phone prefix database with carrier identification
- ✅ profile picture download — HD saved locally
- ✅ rich terminal UI — hacker-theme ASCII banner, live progress, formatted tables
- ✅ 4 color themes — hacker, neon, ocean, sunset
- ✅ telegram + discord notifications
- ✅ sqlite3 database — target history, dossier tracking, extraction logs
- ✅ json dossier export — structured, pretty-printed
- ✅ batch processing from file
- ✅ socks4/socks5 proxy support — weighted rotation, health checks, cooldown
- ✅ browser fingerprint randomization
- ✅ search + stats — query past targets, view tool statistics

---

## requirements

- python 3.11+
- socks5 proxies (minimum 50, recommended 500+)
- telegram bot / discord webhook (optional, for notifications)

---

## installation

```bash
git clone https://github.com/your-repo/insta_dossier.git
cd insta_dossier
pip install -r requirements.txt

 (optional) notifications
edit config.yaml:

yaml
notifications:
  telegram_bot_token: "your-bot-token"
  telegram_chat_id: "your-chat-id"
  discord_webhook_url: "https://discord.com/api/webhooks/..."
3. run
bash
python main.py --target johndoe                  # passive
python main.py --target johndoe --mode active    # + reset enumeration
python main.py --target johndoe --mode full      # + identity reconstruction
python main.py --batch targets.txt --mode full   # batch mode
python main.py --stats                           # show stats
python main.py --search johndoe                  # search past targets
usage
text
python main.py [options]
flag	description
-t, --target	target instagram username, @handle, or profile URL
-b, --batch	file with list of usernames (one per line)
-c, --config	config file path (default: config.yaml)
-m, --mode	passive / active / full (default: passive)
-e, --export	json / html (default: json)
-o, --output	output directory (default: output/dossiers)
-p, --proxies	path to socks5 proxy list
--no-images	skip profile picture download
--no-verify	skip link verification
--no-reconstruct	skip identity reconstruction
--stats	show database statistics
--search	search existing targets by name
--recent N	show N most recent dossiers
--theme	hacker / neon / ocean / sunset
--small-banner	compact ASCII banner
-v, --verbose	debug logging
how it works
text
@target → profile scraper → bio parser → linked mapper
              ↓                  ↓              ↓
         reset enumerator ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
              ↓
       identity reconstructor
              ↓
        dossier builder → JSON export + notification
extraction modes
passive mode
scrapes public profile, parses bio, maps linked platforms. target will never know.

active mode
adds password reset enumeration — reveals masked email (j****e@gmail.com) and masked phone (+1 3** *** 5678). verifies linked accounts.

⚠️ password reset may trigger a notification to the target. the tool enforces 1-hour cooldown per proxy.

full mode
adds identity reconstruction — generates ranked email/phone candidates with confidence scores using 16 common patterns, name analysis, and cross-platform correlation.

project structure
text
insta_dossier/
├── main.py                      # CLI entry, pipeline orchestrator
├── config.yaml                  # all settings
├── requirements.txt             # pip dependencies
├── bootstrap.py                 # folder structure generator
│
├── core/                        # osint engine
│   ├── profile_scraper.py       # public JSON scraping (3 endpoints)
│   ├── reset_enumerator.py      # masked email/phone extraction
│   ├── bio_parser.py            # regex engine (20 platform patterns)
│   ├── linked_mapper.py         # cross-platform discovery (38 platforms)
│   ├── pattern_reconstructor.py # masked → full identity reconstruction
│   └── dossier_builder.py       # final dossier assembly + risk assessment
│
├── network/                     # infrastructure
│   ├── proxy_rotator.py         # socks4/socks5 pool management
│   ├── session_manager.py       # aiohttp session + cookie management
│   └── fingerprint_engine.py    # browser fingerprint randomization
│
├── ui/                          # terminal interface
│   ├── banner.py                # ASCII art + styled panels
│   ├── progress.py              # rich progress bars + spinners
│   ├── colors.py                # ANSI codes + 4 color themes
│   └── table_writer.py          # formatted result tables
│
├── storage/                     # persistence
│   ├── db.py                    # sqlite3 (targets, dossiers, extraction log)
│   └── dossier_logger.py        # JSON export + file management
│
├── notifications/alerts.py      # telegram + discord notifications
│
├── data/                        # static data
│   ├── email_patterns.json      # 13 patterns with prevalence + nicknames
│   ├── phone_prefixes.json      # 50+ countries, all major carriers
│   ├── user_agents.txt          # 100 rotating user agents
│   └── linked_platforms.json    # 38 platforms + 12 link aggregators
│
├── proxies/socks5_list.txt      # your proxies
└── output/                      # dossiers, images, database
output dossier format
json
{
  "dossier_id": "dossier_johndoe_2026-07-16",
  "target_username": "johndoe",
  "profile": {
    "full_name": "John Doe",
    "follower_count": 4521,
    "is_business": false
  },
  "contact": {
    "emails_discovered": [
      {"email": "dev@email.com", "source": "bio_text"}
    ],
    "masked_email": "j****e@gmail.com",
    "masked_phone": "+1 3** *** 5678"
  },
  "identity_reconstruction": {
    "best_email": {
      "email": "john.doe@gmail.com",
      "confidence": 0.92,
      "pattern": "first.last"
    },
    "email_candidates": [
      {"email": "john.doe@gmail.com", "confidence": 0.92},
      {"email": "johndoe@gmail.com", "confidence": 0.78}
    ]
  },
  "linked_platforms": {
    "twitter": {"handle": "johndoe", "verified": true},
    "github": {"handle": "johndoe", "verified": true}
  },
  "risk_assessment": {
    "privacy_score": "HIGH",
    "data_exposure": "SIGNIFICANT",
    "osint_value": "HIGH"
  },
  "summary": {
    "text": "@johndoe (John Doe) is a personal account with 4,521 followers. Privacy exposure is HIGH. Identity likely reconstructable — best candidate: john.doe@gmail.com (92% confidence).",
    "data_points_collected": 27
  }
}
platforms detected
social: facebook, twitter/x, tiktok, youtube, linkedin, github, twitch, snapchat, telegram, discord, reddit, pinterest, threads, mastodon, bluesky

creative: behance, dribbble, soundcloud, vimeo, medium, substack, patreon, spotify

messaging: signal, whatsapp, line, wechat

payment: venmo, cashapp, paypal, buymeacoffee, ko-fi

adult: onlyfans

aggregators: linktree, beacons, campsite, bento, carrd, lnk.bio, solo.to, allmylinks, hoo.be, bio.site, msha.ke, about.me

notifications
event	when
✅ dossier complete	extraction finished
✅ business email found	unmasked business email discovered
✅ identity reconstructed	high-confidence email (>70%)
ℹ️ platforms mapped	3+ platforms found
⚠️ proxy pool low	available proxies below threshold
🚨 fatal error	pipeline failure
configuration
<details> <summary><b>full config.yaml</b></summary>
yaml
modes:
  passive:
    scrape_profile: true
    parse_bio: true
    map_links: true
    enumerate_reset: false
    reconstruct_identity: false
    verify_links: false
  active:
    scrape_profile: true
    parse_bio: true
    map_links: true
    enumerate_reset: true       # ⚠ may trigger notification
    reconstruct_identity: false
    verify_links: true
  full:
    scrape_profile: true
    parse_bio: true
    map_links: true
    enumerate_reset: true
    reconstruct_identity: true
    verify_links: true

network:
  max_retries: 3
  timeout: 15
  max_concurrent_scrapes: 5
  max_concurrent_verifications: 4
  download_images: true

proxies:
  file: "proxies/socks5_list.txt"
  rotation_mode: "weighted"
  max_failures: 2
  cooldown_seconds: 600
  min_proxies_required: 10
  prefer_residential: true

notifications:
  telegram_bot_token: null
  telegram_chat_id: null
  discord_webhook_url: null
  notify_on_dossier: true
  notify_on_business_email: true
  notify_on_identity: true

database:
  path: "output/insta_dossier.db"

output:
  dir: "output"
  pretty_print: true
  max_dossiers_per_target: 10
</details>
troubleshooting
problem	solution
profile not found	account may be private/banned. try different proxies.
all endpoints empty	instagram login wall. use residential/mobile proxies.
proxy pool exhausted	test proxies manually. reduce max_failures. increase pool.
reset enumeration empty	account may have no recovery contact set.
low confidence reconstruction	add more linked platform handles. use full mode.
import rich failed	pip install rich. tool falls back to basic text.
database
query directly:

bash
sqlite3 output/insta_dossier.db "SELECT username, privacy_risk FROM targets ORDER BY last_scraped_at DESC LIMIT 10;"
sqlite3 output/insta_dossier.db "SELECT COUNT(*) as total, SUM(emails_found) as emails FROM dossiers;"
disclaimer
this tool is for educational purposes, authorized penetration testing, and legitimate OSINT research only. using it against accounts you do not own or have written authorization to investigate may violate instagram's terms of service and applicable laws including the CFAA (united states), computer misuse act 1990 (united kingdom), GDPR (european union), and similar legislation worldwide.

you are solely responsible for compliance with all applicable laws.

<div align="center">