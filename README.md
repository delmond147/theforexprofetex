# Exness Partner Telegram Bot — AI Agent Handover Guide

## Overview

This is a production Telegram bot built for **Exness affiliate partners** (forex mentors).
It automates community management, member verification, and trading activity monitoring
for partners who earn commissions from client trades on the Exness broker platform.

The bot is built in **Python 3.11** using `python-telegram-bot v20.7`, deployed on
**Railway** with a persistent SQLite database on a mounted volume.

---

## The Problem This Bot Solves

### How Exness Partner Commissions Work

When an Exness affiliate partner shares their partner link, and a client:
1. Registers an Exness account using that link
2. Creates an MT5 trading account
3. Makes a deposit into that MT5 account
4. Places trades on the MT5 account

→ The **partner earns a commission** on every trade based on lot size used.

### The Core Problem

Partners run trading mentorship communities (Telegram groups) where they provide:
- Free and paid trading signals
- Mentorship programs
- Educational content

Access to these groups is given to members who register under the partner's Exness link.
However partners face these critical problems:

1. **Members register but never create an MT5 account or deposit** — partner earns nothing
   but member still occupies a group spot and consumes resources
2. **Members switch to a different Exness partner** — partner stops earning commissions
   but member stays in the group
3. **Members stop trading** — partner commissions drop to zero but member remains in group
4. **Manual verification is impossible at scale** — partners cannot manually check
   hundreds of members every day
5. **No automated enforcement** — partners have no way to automatically remove
   non-compliant members

### The Solution This Bot Provides

A fully automated Telegram bot that:
- Verifies members are registered under the correct partner link before granting group access
- Checks that members have created an MT5 account and funded it
- Monitors trading activity daily and removes inactive members automatically
- Detects partner switches and removes members who move to a different partner
- Handles all onboarding, payments, and community management without manual work

---

## What Has Been Built

### Core Architecture

```
exness-partner-bot/
├── main.py                          ← entry point, all handlers wired here
├── requirements.txt                 ← pip dependencies
├── runtime.txt                      ← python 3.11.11
├── Procfile                         ← web: python main.py
├── DEPLOY.md                        ← deployment guide for new clients
└── src/
    ├── core/
    │   ├── settings.py              ← ALL configuration via env vars
    │   ├── logging.py               ← structlog structured logging
    │   └── vault.py                 ← Fernet encryption for credentials
    ├── db/
    │   └── database.py              ← SQLite with all DB operations
    ├── middleware/
    │   └── rate_limit.py            ← email attempt rate limiting
    ├── services/
    │   ├── exness_client.py         ← Exness Partnership API client
    │   └── activity_checker.py      ← scheduled jobs (activity + reminders)
    └── handlers/
        ├── welcome.py               ← /start, returning user detection
        ├── keyboards.py             ← all InlineKeyboard layouts
        ├── verification.py          ← ALL conversation flows
        ├── menu.py                  ← menu callbacks
        ├── faq.py                   ← FAQ question/answer flow
        ├── admin.py                 ← admin commands + notifications
        └── signals.py               ← signal/announcement commands
```

### Database Schema (SQLite)

```sql
-- Users table — all bot users and their verification status
CREATE TABLE users (
    telegram_id       INTEGER PRIMARY KEY,
    username          TEXT,
    first_name        TEXT,
    verified_email    TEXT,        -- Exness email after verification
    mentorship_type   TEXT,        -- "beginners", "advanced", "swing"
    verified_at       TEXT,
    joined_at         TEXT DEFAULT (datetime('now')),
    last_active_check TEXT,        -- last time activity was checked
    warning_sent_at   TEXT,        -- when inactivity warning was sent
    removed           INTEGER DEFAULT 0
);

-- Tracks every verification attempt
CREATE TABLE verification_attempts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id  INTEGER,
    email        TEXT,
    success      INTEGER,
    attempted_at TEXT DEFAULT (datetime('now'))
);

-- Encrypted credentials and config storage
CREATE TABLE bot_config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Daily activity check log
CREATE TABLE activity_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER,
    email           TEXT,
    last_trade_date TEXT,
    is_active       INTEGER,
    checked_at      TEXT DEFAULT (datetime('now'))
);

-- Tracks users who started a flow but didn't complete it (for reminders)
CREATE TABLE incomplete_flows (
    telegram_id    INTEGER PRIMARY KEY,
    username       TEXT,
    first_name     TEXT,
    flow_type      TEXT,       -- "beginners", "advanced", "vip_one_on_one" etc
    started_at     TEXT DEFAULT (datetime('now')),
    last_reminded  TEXT,
    reminder_count INTEGER DEFAULT 0
);
```

### Exness Partnership API Integration

**Base URL:** `https://my.exnessaffiliates.com/api`

**Authentication:**
- `POST /api/v2/auth/` with `{"login": email, "password": password}`
- Returns `{"token": "JWT eyJhbG..."}` 
- All requests use `Authorization: JWT <token>` header
- Token auto-refreshes on 401 using stored credentials
- Credentials stored encrypted in SQLite via Fernet encryption

**Endpoints currently used:**

| Endpoint | Method | Purpose | Status |
|---|---|---|---|
| `/api/v2/auth/` | POST | Get JWT token | ✅ Working |
| `/api/partner/affiliation/` | POST | Check if email is under partner | ✅ Working |
| `/api/reports/clients/accounts/` | GET | Get client account details + last trade date | ✅ Working |

**Known response from `/api/partner/affiliation/`:**
```json
{
  "affiliation": true,
  "accounts": ["44186977", "168247204"],
  "client_uid": "4ec0c5fa"
}
```

**Known response from `/api/reports/clients/accounts/?search=email`:**
```json
{
  "data": [{
    "id": 810206605,
    "partner_account": "1163683105934934542",
    "client_uid": "dc11e02f",
    "client_account": "134221327",
    "client_account_type": "Pro",
    "client_country": "ZA",
    "platform": "mt5",
    "client_account_created": "2026-04-30",
    "client_account_last_trade": "2026-06-02",
    "volume_lots": "39.7300000",
    "volume_mln_usd": "20.0045",
    "reward": "125.51"
  }]
}
```

### Menu Structure (Currently Active)

```
Main Menu
├── 📚 [LABEL_ADVANCED]           → verification flow → group access
├── 🔄 Using Different Broker?    → subscription flow → payment collection
├── 💎 VIP Mentorship             → package selection → details collection → payment
├── 📢 Community                  → direct Telegram link
├── 🆘 Get Support                → direct Telegram link
└── ❓ FAQs                       → 6 pre-built questions
```

Note: Some menu items are commented out in `keyboards.py` (beginners, swing, signal)
as this particular client deployment doesn't use them. They exist in the code.

### Verification Flow (Core Feature)

```
User taps mentorship button
    ↓
"Do you have an Exness account?"
    → No  → Show partner registration link
    → Yes → "Enter your Exness email"
               ↓
        POST /api/partner/affiliation/ {"email": email}
               ↓
        affiliation: true  → Save to DB → Show group invite link
        affiliation: false → "Do you have an account?"
                                → Yes → Guide to change partner
                                → No  → Guide to register
```

### Scheduled Jobs

| Job | Schedule | What it does |
|---|---|---|
| `run_activity_check` | Daily 3AM UTC | Checks all verified users for trading activity |
| `run_reminder_check` | Every 4 hours | Reminds users who started but didn't finish a flow |

**Activity check logic:**
1. Fetches all verified non-removed users from DB
2. For each user calls `GET /api/reports/clients/accounts/?search=email`
3. Reads `client_account_last_trade` field
4. If > `INACTIVITY_DAYS` (default 60) days since last trade → send warning
5. If warned > `WARNING_DAYS` (default 7) days ago → remove user + notify admin + kick from group

### Admin Commands

| Command | What it does |
|---|---|
| `/setcredentials` | Guided flow to set Exness API login/password |
| `/checkapi` | Test API connection |
| `/clearcredentials` | Wipe stored credentials |
| `/settoken` | Manually set JWT token |
| `/cleartoken` | Clear stored token |
| `/broadcast` | Send message to all users |
| `/signal` | Send trade signal to all verified users |
| `/announce` | Send announcement to all verified users |
| `/checkinactive` | Manually trigger activity check |
| `/listusers` | Show all verified users with status |

### Payment Flows Built

**VIP Mentorship:**
- Two packages: One-on-One ($1200) and Group ($250)
- Collects name + phone
- Shows 3 payment method options (Bank, Mobile Money, Crypto)
- Each payment method sends details to admin + user

**VIP Signal Subscription:**
- 4 packages: 1 month, 2 months, 6 months, 1 year
- Collects name + phone
- Shows payment details

**Different Broker Subscription:**
- Fixed monthly fee ($35)
- Collects name + phone
- Shows payment details

### Multi-Client / SaaS Design

The entire bot is configurable via environment variables — no code changes needed
between client deployments. A new client deployment takes ~26 minutes by following
`DEPLOY.md`.

**Key env vars that change per client:**

```
BOT_TOKEN, MENTOR_NAME, ADMIN_CHAT_ID, ADMIN_USERNAME
API_LOGIN, API_PASSWORD, PARTNER_LINK
BEGINNERS_GROUP_LINK, ADVANCED_GROUP_LINK, SWING_TRADING_LINK
INNER_CIRCLE_LINK, MENTOR_CONTACT
VIP_PRICE, VIP_ONE_ON_ONE_PRICE, VIP_GROUP_PRICE
SIGNAL_PRICE_1MONTH/2MONTH/6MONTH/1YEAR
DIFFERENT_BROKER_PRICE
PAYMENT_METHOD_1/2/3_NAME and details
LABEL_BEGINNERS/ADVANCED/SWING/VIP/SIGNAL etc
INACTIVITY_DAYS, WARNING_DAYS
VIP_GROUP_ID, VIP_GROUP_INVITE_LINK
SECRET_KEY, DB_PATH, WEBHOOK_URL
```

---

## What Is NOT Yet Built (Pending Tasks)

### PRIORITY 1 — MT5 Account + Deposit Verification (Critical)

**The Problem:**
After a member verifies their Exness account is under the partner link, there is no
check that they have actually created an MT5 trading account and made a deposit.
Without an MT5 account and deposit, the partner earns zero commission.

**Business Rule:**
- Member verifies email → affiliation confirmed ✅
- Bot must ALSO check: has this member created an MT5 account with a deposit?
- If no MT5 account with deposit within **2 days** of verification → remove from group
- Member must re-verify and meet ALL criteria to rejoin

**What we know from the API:**
The `GET /api/reports/clients/accounts/` endpoint returns account data including:
- `platform: "mt5"` — confirms it is an MT5 account
- `volume_lots` — if > 0, account has traded (implies funded)
- `client_account_created` — when the MT5 account was created
- `client_account_last_trade` — last trade date

**What needs to be built:**

1. After affiliation confirmed, immediately call `GET /api/reports/clients/accounts/?search=email`
2. Check if any account exists with `platform == "mt5"`
3. Check if `volume_lots > 0` (has traded, which implies funded)
4. If no MT5 account found → do NOT grant group access yet
   → Tell user: "Please create an MT5 account on Exness and make a deposit first"
   → Set a 2-day timer in DB
5. If MT5 account found but `volume_lots == 0` → account exists but not funded
   → Tell user: "Please fund your MT5 account to complete verification"
6. Only if MT5 account exists AND `volume_lots > 0` → grant group access
7. Scheduled job: check users who are pending MT5 verification
   → If 2 days passed with no MT5 + deposit → remove from any group joined

**New DB columns needed on `users` table:**
```sql
ALTER TABLE users ADD COLUMN mt5_verified INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN mt5_check_deadline TEXT;
ALTER TABLE users ADD COLUMN mt5_account_id TEXT;
```

**New flow after affiliation check:**
```
affiliation: true
    ↓
GET /api/reports/clients/accounts/?search=email
    ↓
MT5 account found AND volume_lots > 0?
    → YES → full verification → grant group access
    → NO MT5 account → "Create MT5 account + deposit" → 2-day timer
    → MT5 exists but no volume → "Fund your account" → 2-day timer
```

---

### PRIORITY 2 — Partner Switch Detection (Critical)

**The Problem:**
Members can switch to a different Exness partner after joining the group.
When they do this, the original partner stops earning commissions from their trades
but the member remains in the group.

**Business Rule:**
- Daily check all verified users
- Re-run `POST /api/partner/affiliation/` for each verified email
- If `affiliation: false` → member has switched partners → remove immediately
- No warning — immediate removal (they deliberately switched)
- Notify admin with details

**What needs to be built:**

Add to `run_activity_check()` in `activity_checker.py`:

```python
# Re-check affiliation for all verified users
affiliation = await exness.check_partner_affiliation(user["verified_email"])
if not affiliation or not affiliation.get("affiliation"):
    # Member switched partners — remove immediately
    await remove_user(bot, telegram_id, first_name, email)
    await notify_admin(bot, f"🚨 Partner switch detected: {email} removed")
    switched_count += 1
    continue  # skip activity check for this user
```

---

### PRIORITY 3 — Reduce Inactivity Period to 30 Days

**Change required:**
- Default `INACTIVITY_DAYS` from 60 to 30
- Update `settings.py` default value
- Update Railway env var

```python
INACTIVITY_DAYS: int = int(os.environ.get("INACTIVITY_DAYS", "30"))
```

---

### PRIORITY 4 — MT5 Pending Verification Scheduled Job

**What needs to be built:**

A new scheduled job that runs every 6 hours checking users who are
in "pending MT5 verification" state:

```python
async def run_mt5_check(bot: Bot) -> None:
    """
    Runs every 6 hours.
    Checks users who verified affiliation but haven't completed MT5 + deposit.
    Removes users whose 2-day deadline has passed.
    """
    pending_users = get_pending_mt5_users()  # new DB query needed
    for user in pending_users:
        # Check if they now have MT5 + deposit
        accounts = await exness.get_client_accounts(user["verified_email"])
        mt5_funded = any(
            a.get("platform") == "mt5" and float(a.get("volume_lots", 0)) > 0
            for a in accounts
        )
        if mt5_funded:
            # Grant group access now
            mark_mt5_verified(user["telegram_id"])
            await send_group_link(bot, user["telegram_id"])
        elif deadline_passed(user["mt5_check_deadline"]):
            # 2 days passed — remove
            await remove_user(bot, user["telegram_id"], ...)
            mark_removed(user["telegram_id"])
```

---

### PRIORITY 5 — Explore Deposit Amount Verification

**Unknown — needs investigation:**

The current API response does not explicitly show a deposit amount.
`volume_lots > 0` is used as a proxy for "account is funded and trading."

Need to test `GET /api/reports/orders/` endpoint in Swagger with a real
verified email to see if it returns deposit/withdrawal transaction history.

If deposit data is available, add a minimum deposit check:
- `MINIMUM_DEPOSIT` env var (e.g. $10)
- Check deposit amount before granting group access

---

## Technical Standards To Maintain

### Code Style
- All Python files use `from __future__ import annotations`
- All configuration via `os.environ.get()` in `settings.py` — never hardcoded
- All messages use `.format(MENTOR_NAME=MENTOR_NAME)` — never hardcoded mentor names
- Structured logging via `structlog` — use `logger.info()`, `logger.error()` etc
- All DB operations in `database.py` — never raw SQL in handler files
- All keyboards in `keyboards.py` — never build `InlineKeyboardMarkup` in settings files

### Error Handling
- All API calls wrapped in try/except
- 401 responses trigger automatic token refresh then credential re-login
- 404 on affiliation endpoint means "not affiliated" — not an error
- All Telegram errors caught with `TelegramError`
- Admin notified via `notify_admin()` for critical failures

### Message Formatting
- All messages use `parse_mode="Markdown"`
- Dynamic values use `.format()` — never f-strings with Markdown (causes parse errors)
- Never wrap emails or dynamic values in backticks inside Markdown messages
- Backtick-only messages (copyable values) are sent as separate plain messages

### Conversation Flows
- All multi-step flows use `ConversationHandler` with explicit state constants
- State constants defined at top of `verification.py` as integers
- All ConversationHandlers have `allow_reentry=True, per_message=False`
- ConversationHandlers registered in `main.py` BEFORE generic CallbackQueryHandlers
- `clear_incomplete_flow()` called on every completion and cancellation

### Security
- Credentials encrypted with Fernet before DB storage
- `SECRET_KEY` env var required — never committed to git
- `ADMIN_CHAT_ID` checked as integer comparison for all admin commands
- Sensitive messages (credentials) deleted immediately after reading

---

## Deployment

- **Platform:** Railway (Hobby $5/month)
- **Python:** 3.11.11 (pinned in `runtime.txt`)
- **Database:** SQLite at `/app/data/bot.db` on mounted Railway volume
- **Mode:** Webhook (set `WEBHOOK_URL` to Railway domain)
- **Volume:** Mounted at `/app/data` — survives all redeploys and restarts
- See `DEPLOY.md` for complete step-by-step deployment guide

---

## Key Files To Read First

Before making any changes, read these files in this order:

1. `src/core/settings.py` — understand all configuration
2. `src/db/database.py` — understand data model
3. `src/services/exness_client.py` — understand API integration
4. `src/handlers/verification.py` — understand the core flows
5. `main.py` — understand how everything is wired

---

## Running Locally

```bash
# Install dependencies
uv sync

# Copy and fill environment variables
cp .env.example .env

# Run in polling mode (WEBHOOK_URL must be empty in .env)
uv run main.py
```

---

## Environment Variables Reference

See `.env.example` for the full list with descriptions.
See `DEPLOY.md` for per-client deployment instructions.

---

## Questions / Decisions Needed

1. **Minimum deposit amount** — what is the minimum deposit a member must make
   for the partner to consider them "active"? This determines the threshold for
   the MT5 funding check.

2. **MT5 account grace period** — currently 2 days proposed. Is this correct?
   Should it be longer (e.g. 7 days) to give members time to fund their account?

3. **Partner switch grace period** — should there be a warning before removal
   when a partner switch is detected, or immediate removal?

4. **Deposit endpoint** — `GET /api/reports/orders/` needs to be tested in
   Swagger to confirm if deposit amounts are available. This will determine
   whether we can check actual deposit amounts or use `volume_lots > 0` as proxy.
