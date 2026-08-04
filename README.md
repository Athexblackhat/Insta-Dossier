# INSTA DOSSIER

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

```
git clone https://github.com/Athexblackhat/Insta-Dossier.git
cd Insta-Dossier
pip install -r requirements.txt
```
 *(optional) notifications*
 ```
edit config.yaml:

yaml
notifications:
  telegram_bot_token: "your-bot-token"
  telegram_chat_id: "your-chat-id"
  discord_webhook_url: "https://discord.com/api/webhooks/..."
```
### Execution
```
python main.py --target johndoe                  # passive
python main.py --target johndoe --mode active    # + reset enumeration
python main.py --target johndoe --mode full      # + identity reconstruction
python main.py --batch targets.txt --mode full   # batch mode
python main.py --stats                           # show stats
python main.py --search johndoe                  # search past targets
```
### Usage
```
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
```
### how it works
```
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
```
*⚠️ password reset may trigger a notification to the target. the tool enforces 1-hour cooldown per proxy.*

### full mode
*adds identity reconstruction — generates ranked email/phone candidates with confidence scores using 16 common patterns, name analysis, and cross-platform correlation.*


### output dossier format
```
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
```

## Disclaimer
*This tool is for educational purposes, authorized penetration testing, and legitimate OSINT research only. using it against accounts you do not own or have written authorization to investigate may violate instagram's terms of service and applicable laws including the CFAA (united states), computer misuse act 1990 (united kingdom), GDPR (european union), and similar legislation worldwide.*

***You are solely responsible for compliance with all applicable laws.***

<div align="center">
