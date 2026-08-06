# Exness Partner Telegram Bot — Project Documentation

## Project Overview

**Project Name:** Theforexprohetess  
**Type:** Production Telegram Bot for Exness Affiliate Partners  
**Language:** Python 3.11  
**Framework:** python-telegram-bot v20.7  
**Database:** SQLite  
**Deployment:** Railway with webhook mode  
**Status:** Production-ready, Multi-client SaaS architecture

## What This Bot Does

This bot automates community management for Exness forex affiliate partners who run trading mentorship communities. It solves the critical problem of partners earning zero commission from members who:
- Register but never create/fund MT5 accounts
- Switch to different partners
- Stop trading (inactive accounts)
- Consume group resources without generating partner revenue

### Core Value Proposition

**For Partners:** Automated verification + activity monitoring = only active, revenue-generating members stay in paid groups

**For Members:** Seamless onboarding, automated access management, and clear requirements

## Architecture & Structure

```
Theforexprohetess/
├── main.py                          # Entry point, all handlers wired
├── requirements.txt                 # Dependencies
├── runtime.txt                      # Python 3.11.11
├── Procfile                         # Railway deployment
├── .env.example                     # Environment template
├── README.md                        # Detailed technical docs
└── src/
    ├── core/
    │   ├── settings.py              # ALL config via env vars
    │   ├── logging.py               # structlog structured logging
    │   └── vault.py                 # Fernet encryption for credentials
    ├── db/
    │   └── database.py              # SQLite operations
    ├── middleware/
    │   └── rate_limit.py            # Email verification rate limiting
    ├── services/
    │   ├── exness_client.py         # Exness Partnership API client
    │   └── activity_checker.py      # Scheduled jobs (3 types)
    └── handlers/
        ├── welcome.py               # /start command
        ├── keyboards.py             # All InlineKeyboard layouts
        ├── verification.py          # Core verification flows
        ├── menu.py                  # Menu callbacks
        ├── faq.py                   # FAQ system
        ├── admin.py                 # Admin commands + notifications
        ├── signals.py               # Signal/announcement broadcasting
        └── group_access.py          # Group link generation
```

## Database Schema

### `users` table (Core)
```sql
telegram_id INTEGER PRIMARY KEY
username TEXT
first_name TEXT
verified_email TEXT                  -- Exness email after verification
mentorship_type TEXT                 -- "beginners", "advanced", "swing"
verified_at TEXT
joined_at TEXT
last_active_check TEXT
warning_sent_at TEXT
removed INTEGER DEFAULT 0
mt5_verified INTEGER DEFAULT 0       -- NEW MT5 account verified
mt5_check_deadline TEXT              -- Grace period deadline
mt5_account_id TEXT                  -- MT5 account number
partner_switch_warned_at TEXT        -- Partner switch warning timestamp
```

### Other Tables
- `verification_attempts` - All email verification attempts
- `bot_config` - Encrypted credentials/config storage
- `activity_log` - Daily activity check results
- `incomplete_flows` - Users who started but didn't finish flows (for reminders)
- `partner_switch_log` - Partner switch detection log

## Exness Partnership API Integration

**Base URL:** `https://my.exnessaffiliates.com/api`

### Authentication Flow
1. Load JWT token from encrypted DB storage
2. On 401: Try token refresh via `POST /api/v2/auth/token/`
3. On refresh fail: Re-login with stored encrypted credentials via `POST /api/v2/auth/`
4. On login fail: Notify admin to run `/settoken` or `/setcredentials`

### Key Endpoints Used

| Endpoint | Method | Purpose | Returns |
|---|---|---|---|
| `/api/v2/auth/` | POST | Get JWT token | `{"token": "JWT ..."}` |
| `/api/partner/affiliation/` | POST | Check email under partner | `{"affiliation": true, "accounts": [...], "client_uid": "..."}` |
| `/api/reports/clients/accounts/` | GET | Get client accounts + trade data | Array of accounts with platform, volume, dates |
| `/api/reports/orders/` | GET | Get trade orders for account | Array of orders with dates, volume, rewards |

### Verification Logic (3-Step Process)

**Step 1: Affiliation Check**
```
POST /api/partner/affiliation/ {"email": "user@example.com"}
→ affiliation: true/false
```

**Step 2: MT5 Account Check**
```
GET /api/reports/clients/accounts/?search=email
→ Check for MT5 platform AND created_date AFTER verified_at
→ NEW account (not old account from previous partner)
```

**Step 3: Funding/Trading Check**
```
GET /api/reports/orders/?client_account=123456
→ Check for at least 1 closed order (confirms funded + traded)
→ Fallback: volume_lots > 0 from accounts endpoint
```

**All three must pass** for full verification. If any fail, user gets grace period.

## Core Flows

### 1. Verification Flow (verification.py)

```
User taps mentorship button (beginners/advanced/swing)
    ↓
"Do you have an Exness account?"
    → No  → Show partner registration link + "I've registered" button
    → Yes → "Enter your Exness email"
               ↓
        [Step 1: Affiliation Check]
        POST /api/partner/affiliation/
               ↓
        affiliation: false → "Account not linked" flow
               ↓                  ↓
        affiliation: true    Guide to change partner
               ↓              or register fresh
        [Step 2: MT5 Check - NEW account only]
        GET /api/reports/clients/accounts/
               ↓
        Compare account creation date with verified_at
               ↓
        [Step 3: Trading Check]
        GET /api/reports/orders/
               ↓
        ✅ All pass → Grant group access + onboarding
        ❌ Any fail → MT5_GRACE_DAYS deadline + instructions
```

**MT5 Grace Period:** Default 5 days (configurable via `MT5_GRACE_DAYS`)  
**User can check status:** "Check MT5 Status" button reruns Steps 2-3

### 2. Scheduled Jobs (activity_checker.py)

**Job 1: Daily Activity Check** (3AM UTC)
```python
async def run_activity_check(bot: Bot):
    # Step 1: Remove users past partner switch 24h deadline
    # Step 2: Remove users past inactivity warning deadline
    # Step 3: Check all verified users for partner switch
    # Step 4: Check all verified users for trading activity
    # Step 5: Send admin summary
```

**Job 2: MT5 Verification Check** (Every 6 hours)
```python
async def run_mt5_check(bot: Bot):
    # Check pending MT5 users
    # Grant access if now verified
    # Remove users past MT5 grace period deadline
```

**Job 3: Incomplete Flow Reminders** (Every 4 hours)
```python
async def run_reminder_check(bot: Bot):
    # Remind users who started but didn't finish flows
    # Max 42 reminders over 7 days
    # Stop if user blocked bot
```

### 3. Payment Flows (verification.py)

**VIP Mentorship:**
- Two packages: One-on-One ($1200), Group ($250)
- Collects: name, phone
- Shows 3 payment methods with copyable details

**VIP Signal Subscription:**
- 4 packages: 1mo, 2mo, 6mo, 1yr
- Collects: name, phone
- Shows payment details + proof submission

**Different Broker Subscription:**
- Monthly fee ($35 default)
- For users trading with non-Exness brokers
- Collects: name, phone

## Code Patterns & Standards

### Configuration Management
```python
# ALL config from environment variables in settings.py
from src.core.settings import BOT_TOKEN, MENTOR_NAME, ADMIN_CHAT_ID

# NEVER hardcode values
# ALWAYS use .format(MENTOR_NAME=MENTOR_NAME) for dynamic text
```

### Database Operations
```python
# All DB operations in database.py
from src.db.database import save_verification, get_user, mark_removed

# Never write raw SQL in handlers
# Use provided helper functions
```

### Logging
```python
from src.core.logging import logger

# Structured logging with context
logger.info("verification_attempt", user_id=123, email="test@test.com")
logger.error("api_call_failed", endpoint="/affiliation", error=str(e))
```

### Message Formatting
```python
# Use Markdown parse_mode
# Use .format() for dynamic values (NOT f-strings in Markdown)
text = (
    "✅ Welcome {name}!\n\n"
    "Your {MENTOR_NAME} account is ready."
).format(name=first_name, MENTOR_NAME=MENTOR_NAME)

await update.message.reply_text(text, parse_mode="Markdown")

# For copyable values, send separate plain message with backticks
await bot.send_message(chat_id=chat_id, text=f"`{value}`", parse_mode="Markdown")
```

### Conversation Handlers
```python
# Define states as integers at top of file
AWAITING_EMAIL = 1
AWAITING_PHONE = 2

# All ConversationHandlers:
ConversationHandler(
    entry_points=[...],
    states={...},
    fallbacks=[...],
    allow_reentry=True,      # REQUIRED
    per_message=False,       # REQUIRED
)

# Always call clear_incomplete_flow() on completion/cancellation
```

### Security
```python
# Credentials encrypted with Fernet before storage
from src.core.vault import encrypt, decrypt
set_config("api_login", encrypt(email))

# Admin commands check ADMIN_CHAT_ID
def _is_admin(user_id: int) -> bool:
    return user_id == int(ADMIN_CHAT_ID)

# Sensitive messages deleted immediately
await update.message.delete()
```

## Admin Commands

| Command | Purpose | Example |
|---|---|---|
| `/start` | Main menu | User command |
| `/help` | Show help text | User command |
| `/setcredentials` | Guided credential setup | Admin only |
| `/settoken <jwt>` | Set JWT token manually | Admin only |
| `/checkapi` | Test API connection | Admin only |
| `/clearcredentials` | Wipe stored credentials | Admin only |
| `/cleartoken` | Clear JWT token | Admin only |
| `/broadcast <msg>` | Message all users | Admin only |
| `/signal <msg>` | Send trade signal | Admin only |
| `/announce <msg>` | Send announcement | Admin only |
| `/checkinactive` | Manual activity check | Admin only |
| `/listusers` | Show all verified users | Admin only |
| `/checkstatus` | Show DB state | Admin only |
| `/kickunverified` | Kick users without MT5 | Admin only |
| `/mt5status` | Full MT5 status report | Admin only |

## Environment Variables (Critical Config)

### Required
```bash
BOT_TOKEN="telegram_bot_token"
SECRET_KEY="fernet_encryption_key"
PARTNER_LINK="exness_partner_link"
ADMIN_CHAT_ID="telegram_user_id"
```

### API & Groups
```bash
ADMIN_USERNAME="telegram_username"
MENTOR_NAME="1BigMarathon"
MENTOR_CONTACT="https://t.me/username"
BEGINNERS_GROUP_LINK="https://t.me/group1"
ADVANCED_GROUP_LINK="https://t.me/group2"
SWING_TRADING_LINK="https://t.me/group3"
VIP_GROUP_ID="-1001234567890"      # For kicking users
```

### Timing & Thresholds
```bash
INACTIVITY_DAYS="30"               # Days before inactivity warning
WARNING_DAYS="7"                   # Days after warning before removal
MT5_GRACE_DAYS="5"                 # Days to complete MT5 verification
MT5_MIN_DEPOSIT="10.0"             # Minimum deposit amount
PARTNER_SWITCH_WARNING_HOURS="24"  # Hours before removal after switch
```

### Labels (Multi-client)
```bash
LABEL_BEGINNERS="Beginners Mentorship"
LABEL_ADVANCED="Advanced Mentorship"
LABEL_SWING="Swing Trading"
LABEL_VIP="VIP Mentorship"
LABEL_SIGNAL="VIP Signal"
LABEL_DIFFERENT_BROKER="Using Different Broker?"
```

### Pricing
```bash
VIP_ONE_ON_ONE_PRICE="$1200"
VIP_GROUP_PRICE="$250"
DIFFERENT_BROKER_PRICE="$35"
SIGNAL_PRICE_1MONTH="$15"
SIGNAL_PRICE_2MONTH="$25"
SIGNAL_PRICE_6MONTH="$50"
SIGNAL_PRICE_1YEAR="$100"
```

### Payment Methods (3 options)
```bash
# Method 1: Bank Transfer
PAYMENT_METHOD_1_NAME="Bank Transfer"
PAYMENT_METHOD_1_BANK="Bank Name"
PAYMENT_METHOD_1_ACCOUNT_NAME="Account Holder"
PAYMENT_METHOD_1_ACCOUNT_NUMBER="1234567890"

# Method 2: Mobile Money
PAYMENT_METHOD_2_NAME="Mobile Money"
PAYMENT_METHOD_2_NETWORK="MTN"
PAYMENT_METHOD_2_NUMBER="0712345678"
PAYMENT_METHOD_2_ACCOUNT_NAME="Account Name"

# Method 3: Crypto
PAYMENT_METHOD_3_NAME="Crypto (USDT)"
PAYMENT_METHOD_3_NETWORK="TRC20"
PAYMENT_METHOD_3_WALLET="wallet_address_here"
```

## Multi-Client SaaS Design

The entire bot is **zero-code configurable** via environment variables. Deploy a new client in ~30 minutes:
1. Create new Railway project
2. Set environment variables (60+ vars)
3. Deploy
4. Client-specific branding, pricing, groups, flows — all via ENV

No code changes needed between deployments.

## Key Files to Read First (In Order)

1. **`src/core/settings.py`** — Understand all configuration
2. **`src/db/database.py`** — Data model and operations
3. **`src/services/exness_client.py`** — API integration patterns
4. **`src/handlers/verification.py`** — Core verification flows
5. **`main.py`** — How everything is wired together
6. **`src/services/activity_checker.py`** — Scheduled job logic
7. **`src/handlers/admin.py`** — Admin commands and notifications

## Important Implementation Notes

### MT5 Verification Requirements (STRICT)

**All three conditions must be true:**
1. Affiliation confirmed under correct partner
2. MT5 account is NEW (created after `verified_at` date)
3. Account has traded (at least 1 closed order via `/api/reports/orders/`)

**Why "NEW account" check matters:**
- Old MT5 accounts from previous partners still generate commissions for OLD partner
- Even if user switches Exness partner, existing MT5 accounts stay with old partner
- User MUST create NEW MT5 account AFTER switching to new partner
- This is critical business logic — never skip this check

**Implementation:**
```python
# In exness_client.py
async def check_mt5_funded(email, verified_at):
    accounts = await get_client_accounts(email)
    
    # Check if account was created AFTER verified_at
    created_dt = datetime.fromisoformat(account["client_account_created"])
    verified_dt = datetime.fromisoformat(verified_at)
    is_new = created_dt >= verified_dt
    
    # Only NEW accounts count
    if not is_new:
        return False, account_id, False  # Old account rejected
```

### Partner Switch Detection

Runs daily at 3AM UTC:
```python
# Re-check affiliation for ALL verified users
affiliation = await exness.check_partner_affiliation(user["verified_email"])

if not affiliation or not affiliation.get("affiliation"):
    # User switched partners
    # Send 24-hour warning
    # Remove after deadline
```

### Error Handling Patterns

```python
# API calls with timeout
try:
    result = await asyncio.wait_for(
        exness.check_partner_affiliation(email),
        timeout=20.0
    )
except asyncio.TimeoutError:
    logger.error("api_timeout", email=email)
    # Handle gracefully

# Telegram errors
try:
    await bot.send_message(...)
except TelegramError as e:
    logger.error("message_send_failed", error=str(e))
    # Continue processing
```

### Rate Limiting

Verification attempts limited to prevent spam:
```python
from src.middleware.rate_limit import is_rate_limited

if is_rate_limited(user_id):
    await update.message.reply_text("⏳ Too many attempts...")
    return
```

## Testing & Development

### Local Development
```bash
# Install dependencies
uv sync

# Copy environment template
cp .env.example .env

# Edit .env with your values
# Leave WEBHOOK_URL empty for polling mode

# Run
uv run main.py
```

### Database Location
```bash
# Development: ./data/theforexprophetess.db
# Production: /app/data/theforexprophetess.db (Railway volume)
```

## Common Tasks

### Adding a New Mentorship Type
1. Add env vars: `LABEL_NEWTYPE`, `NEWTYPE_GROUP_LINK`
2. Update `keyboards.py` with new button
3. Add entry handler in `verification.py`
4. Add keyboard helper in `keyboards.py`
5. Update `_mentorship_assets()` function
6. Add to `MENTORSHIP_DISPLAY_NAME` dict

### Adding a New Admin Command
1. Define handler function in `admin.py` or `signals.py`
2. Add `_is_admin()` check
3. Register in `main.py`: `app.add_handler(CommandHandler("cmd", handler))`
4. Test with admin account

### Modifying Verification Requirements
1. Update logic in `exness_client.py` → `check_mt5_funded()`
2. Update messages in `verification.py` → `_send_mt5_pending()`
3. Update grace period checks in `activity_checker.py` → `run_mt5_check()`
4. Update env var defaults in `settings.py`

## Deployment (Railway)

1. Create Railway project
2. Add PostgreSQL? **No** — SQLite on volume
3. Add volume mounted at `/app/data`
4. Set all environment variables
5. Set `WEBHOOK_URL` to Railway domain
6. Deploy
7. Test `/checkapi` command
8. Monitor logs via Railway dashboard

## Known Issues & Solutions

### Issue: Token expires frequently
**Solution:** Use `/setcredentials` instead of `/settoken` for auto-refresh

### Issue: Users report "not linked" but they are
**Solution:** Check partner link is correct, wait 5 minutes after partner switch

### Issue: MT5 accounts not detected
**Solution:** Ensure account was created AFTER verification date, not before

### Issue: Job not running
**Solution:** Check Railway logs, verify JobQueue is enabled in main.py

## Important Business Rules

1. **Never skip MT5 NEW account check** — old accounts don't generate revenue
2. **30-day inactivity period** — users must trade at least once per month
3. **7-day warning period** — users get 7 days after warning before removal
4. **5-day MT5 grace period** — users get 5 days to create/fund MT5 after affiliation
5. **24-hour partner switch warning** — immediate warning, 24h to fix
6. **Minimum deposit $10** — configurable via `MT5_MIN_DEPOSIT`

## Support & Troubleshooting

### User can't verify
1. Check email is correct Exness registration email
2. Verify partner link in env vars is correct
3. Run `/checkapi` to test API connection
4. Check logs for API errors

### User kicked unexpectedly
1. Check `/mt5status` for their trading activity
2. Check `activity_log` table in database
3. Review partner affiliation status

### Admin commands not working
1. Verify `ADMIN_CHAT_ID` is set correctly (numeric user ID, not username)
2. Check user is sending commands to bot directly (not in group)
3. Review logs for permission errors

## Contact & Links

- Exness Partner Dashboard: https://my.exnessaffiliates.com
- Exness API Docs: https://my.exnessaffiliates.com/api/schema/swagger-ui/
- python-telegram-bot Docs: https://docs.python-telegram-bot.org/

---

**Last Updated:** 2026-08-04  
**Bot Version:** Production v1.0  
**Python Version:** 3.11.11  
**Framework:** python-telegram-bot 20.7
