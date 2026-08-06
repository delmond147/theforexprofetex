# Theforexprohetess Bot — Task Tracker

**Last Updated:** 2026-08-04

---

## 🟢 COMPLETED FEATURES

### Core Verification System
- [x] Exness partner affiliation check via API
- [x] MT5 account detection and verification
- [x] NEW MT5 account check (created after verification date)
- [x] Trading activity verification via orders endpoint
- [x] Grace period system for MT5 completion (5 days default)
- [x] User can manually check MT5 status with button
- [x] Rate limiting on verification attempts
- [x] Email validation and error handling

### Scheduled Jobs
- [x] Daily activity check (3AM UTC)
- [x] MT5 verification check (every 6 hours)
- [x] Incomplete flow reminders (every 4 hours)
- [x] Partner switch detection (daily)
- [x] Inactivity warnings (30-day threshold)
- [x] Automatic removal after warning period (7 days)

### Payment Flows
- [x] VIP Mentorship (One-on-One and Group packages)
- [x] VIP Signal Subscription (4 duration options)
- [x] Different Broker Subscription (monthly)
- [x] 3 payment methods with copyable details
- [x] Payment proof submission flow

### Admin Commands
- [x] `/setcredentials` - Guided credential setup
- [x] `/settoken` - Manual JWT token setting
- [x] `/checkapi` - Test API connection
- [x] `/clearcredentials` - Wipe credentials
- [x] `/cleartoken` - Clear JWT token
- [x] `/broadcast` - Message all users
- [x] `/signal` - Send trade signals
- [x] `/announce` - Send announcements
- [x] `/checkinactive` - Manual activity check
- [x] `/listusers` - List all verified users
- [x] `/checkstatus` - Show DB state
- [x] `/kickunverified` - Kick users without MT5
- [x] `/mt5status` - Comprehensive MT5 status report

### Security & Infrastructure
- [x] Fernet encryption for credentials
- [x] Automatic JWT token refresh
- [x] Automatic re-login on token expiry
- [x] Admin-only command protection
- [x] Message deletion for sensitive data
- [x] Structured logging with context
- [x] Multi-client SaaS architecture (60+ env vars)

### User Experience
- [x] Returning user detection
- [x] Onboarding flow after verification
- [x] FAQ system with 6 questions
- [x] Group link generation per mentorship type
- [x] Typing indicators during API calls
- [x] Clear error messages and guidance
- [x] Partner change guidance flow

---

## 🟡 IN PROGRESS

*No tasks currently in progress*

---

## 🔴 PENDING / TODO

### Priority 1 — Critical Business Logic

#### 1. Inactivity Period Adjustment
**Status:** Needs implementation  
**Current:** 60 days (in some deployments)  
**Required:** 30 days (standardized)  
**Files to modify:**
- `src/core/settings.py` — Update default value
- `.env.example` — Update example
- Railway deployment env vars

**Acceptance Criteria:**
- [ ] Default `INACTIVITY_DAYS` set to 30 in settings.py
- [ ] .env.example updated
- [ ] Existing deployments updated
- [ ] Tested with manual `/checkinactive` command

---

#### 2. Partner Switch Grace Period Configuration
**Status:** Needs clarification  
**Current:** Immediate removal after 24-hour warning  
**Question:** Should there be a configurable grace period?

**Options:**
- Keep current: 24-hour warning then removal
- Add grace period: Warning → X days → Final warning → Removal

**Acceptance Criteria:**
- [ ] Business decision made on grace period
- [ ] If adding grace: new env var `PARTNER_SWITCH_GRACE_DAYS`
- [ ] Update `activity_checker.py` logic
- [ ] Update warning messages
- [ ] Test partner switch flow

---

#### 3. Minimum Deposit Verification Enhancement
**Status:** Needs investigation  
**Current:** Uses `volume_lots > 0` as proxy for funded account  
**Goal:** Verify actual deposit amount if possible

**Investigation needed:**
- [ ] Test `GET /api/reports/orders/` with verified email
- [ ] Check if deposit transactions are returned
- [ ] Document response structure for deposits
- [ ] Determine if deposit amount is available

**If deposit data available:**
- [ ] Implement minimum deposit check ($10 default)
- [ ] Update `check_mt5_funded()` logic
- [ ] Add `MT5_MIN_DEPOSIT` enforcement
- [ ] Update user messages to mention minimum deposit

**If deposit data NOT available:**
- [ ] Document limitation in CLAUDE.md
- [ ] Keep current `volume_lots > 0` approach

---

### Priority 2 — User Experience Improvements

#### 4. Multi-Language Support
**Status:** Not started  
**Effort:** Large  
**Value:** High for international deployment

**Requirements:**
- [ ] Add language selection on `/start`
- [ ] Create translation files (JSON or YAML)
- [ ] Translate all user-facing messages
- [ ] Update keyboards with language context
- [ ] Store user language preference in DB
- [ ] Update `settings.py` with language configs

**Languages to support:**
- [ ] English (default)
- [ ] French
- [ ] Spanish
- [ ] Portuguese
- [ ] Other (as needed per client)

---

#### 5. Enhanced Onboarding Experience
**Status:** Basic implementation exists  
**Enhancement:** Add interactive tutorial

**Features:**
- [ ] Welcome video or GIF
- [ ] Step-by-step group rules walkthrough
- [ ] Trading schedule calendar view
- [ ] First-time user checklist
- [ ] "Getting Started" guide with screenshots

---

#### 6. User Dashboard Command
**Status:** Not started  
**Command:** `/dashboard` or `/mystatus`

**Features:**
- [ ] Show verification status
- [ ] Show MT5 account details
- [ ] Show last trade date
- [ ] Show days until inactivity warning
- [ ] Show mentorship type and group access
- [ ] Show payment history (if applicable)

---

### Priority 3 — Admin Tools Enhancement

#### 7. Admin Analytics Dashboard
**Status:** Not started  
**Command:** `/analytics` or `/stats`

**Metrics to show:**
- [ ] Total users (all time)
- [ ] Verified users (current)
- [ ] Pending MT5 verification
- [ ] Active traders (last 30 days)
- [ ] Inactive users (warning sent)
- [ ] Removed users (all time)
- [ ] New registrations (last 7 days)
- [ ] Partner switches detected (last 30 days)
- [ ] Revenue estimation (based on active traders)

**Visualization:**
- [ ] Daily signup trends
- [ ] Activity rate percentage
- [ ] Retention metrics

---

#### 8. Bulk User Management
**Status:** Partially implemented  
**Enhancement:** More granular controls

**New commands:**
- [ ] `/whitelistuser <email>` - Bypass MT5 check for specific user
- [ ] `/blacklistuser <email>` - Permanently ban user
- [ ] `/resetuser <telegram_id>` - Reset user verification state
- [ ] `/extenddeadline <telegram_id> <days>` - Extend MT5 grace period
- [ ] `/manualverify <telegram_id>` - Force verify user (emergency)

---

#### 9. Export & Reporting
**Status:** Not started

**Features:**
- [ ] `/exportusers` - Export all users to CSV
- [ ] `/exportactivity <days>` - Export activity log to CSV
- [ ] `/exportpayments` - Export payment requests to CSV
- [ ] Weekly email reports to admin (if email configured)
- [ ] Monthly revenue reports

---

### Priority 4 — Technical Improvements

#### 10. Database Migration to PostgreSQL
**Status:** Not started  
**Reason:** SQLite has limitations at scale  
**Trigger:** When user count exceeds 10,000

**Tasks:**
- [ ] Create PostgreSQL migration scripts
- [ ] Test on staging environment
- [ ] Update `database.py` to use PostgreSQL connection
- [ ] Add connection pooling
- [ ] Update deployment documentation

---

#### 11. API Response Caching
**Status:** Not started  
**Goal:** Reduce API calls and improve speed

**Implementation:**
- [ ] Add Redis or in-memory cache
- [ ] Cache affiliation checks (5-minute TTL)
- [ ] Cache account data (2-minute TTL)
- [ ] Invalidate cache on user action
- [ ] Add cache hit/miss logging

---

#### 12. Webhook Health Monitoring
**Status:** Not started  
**Goal:** Detect and alert on bot downtime

**Features:**
- [ ] Heartbeat endpoint for monitoring service
- [ ] Auto-restart on webhook failure
- [ ] Alert admin on repeated failures
- [ ] Health check command `/health` (admin only)

---

#### 13. Unit & Integration Tests
**Status:** Not started  
**Coverage:** 0%  
**Target:** 70%+

**Test files to create:**
- [ ] `tests/test_verification.py`
- [ ] `tests/test_exness_client.py`
- [ ] `tests/test_database.py`
- [ ] `tests/test_activity_checker.py`
- [ ] `tests/test_admin_commands.py`

**Test infrastructure:**
- [ ] Setup pytest
- [ ] Mock Telegram API
- [ ] Mock Exness API
- [ ] Test database fixtures
- [ ] CI/CD integration (GitHub Actions)

---

#### 14. Error Recovery & Retry Logic
**Status:** Basic implementation exists  
**Enhancement:** Exponential backoff

**Improvements:**
- [ ] Retry failed API calls with exponential backoff
- [ ] Queue failed notifications for retry
- [ ] Dead letter queue for permanently failed operations
- [ ] Admin notification on repeated failures

---

### Priority 5 — Optional / Nice to Have

#### 15. Telegram Mini App Integration
**Status:** Not started  
**Effort:** Very Large  
**Value:** High (modern UX)

**Features:**
- [ ] Web-based dashboard within Telegram
- [ ] Real-time trading stats
- [ ] Payment processing within app
- [ ] Group access without invite links

---

#### 16. Automated Trading Signals
**Status:** Not started  
**Requirement:** External signal provider integration

**Features:**
- [ ] Connect to signal provider API
- [ ] Auto-post signals to verified users
- [ ] Track signal performance
- [ ] User feedback on signals

---

#### 17. Referral System
**Status:** Not started

**Features:**
- [ ] Generate unique referral links
- [ ] Track referrals per user
- [ ] Reward system (discounts, free months)
- [ ] Leaderboard for top referrers

---

#### 18. Multi-Admin Support
**Status:** Not started  
**Current:** Single admin (ADMIN_CHAT_ID)

**Features:**
- [ ] Admin roles table in database
- [ ] Role-based permissions (superadmin, moderator, support)
- [ ] `/addadmin`, `/removeadmin`, `/listadmins` commands
- [ ] Audit log for admin actions

---

## 🐛 KNOWN BUGS / ISSUES

### 1. Duplicate Daily Job Registration
**Severity:** Medium  
**File:** `main.py` lines 301-317  
**Issue:** `_daily_activity_job` is scheduled twice

```python
# Lines 301-307
if app.job_queue:
    app.job_queue.run_daily(
        _daily_activity_job,
        time=dtime(hour=3, minute=0),
        name="daily_activity_check",
    )
    logger.info("daily_job_scheduled")

# Lines 312-317 (DUPLICATE)
if app.job_queue:
    app.job_queue.run_daily(
        _daily_activity_job,
        time=dtime(hour=3, minute=0),
        name="daily_activity_check",
    )
```

**Fix:**
- [ ] Remove duplicate job registration
- [ ] Test job scheduling

---

### 2. Activity Check Logic Duplication
**Severity:** Low  
**File:** `activity_checker.py` lines 114-140  
**Issue:** Orders parsing logic is duplicated

```python
# Lines 114-126 (first instance)
if orders:
    last_trade = account.get("client_account_last_trade")
    logger.info(...)
    return True, last_trade

# Lines 127-140 (duplicate)
orders = []
if isinstance(data, dict):
    orders = data.get("data") or []

if orders:
    last_trade = account.get("client_account_last_trade")
    logger.info(...)
    return True, last_trade
```

**Fix:**
- [ ] Remove duplicate code block
- [ ] Test activity checking

---

### 3. Unused Import in main.py
**Severity:** Very Low  
**File:** `main.py` line 6  
**Issue:** `from multiprocessing import context` is imported but never used

**Fix:**
- [ ] Remove unused import

---

## 📝 DOCUMENTATION TASKS

- [ ] Create API integration guide for new Exness endpoints
- [ ] Document deployment process for new clients (step-by-step)
- [ ] Create troubleshooting guide for common issues
- [ ] Video tutorial: How to set up the bot for a new client
- [ ] Architecture diagram (flowchart of verification process)
- [ ] Database schema diagram (ER diagram)

---

## 🔧 MAINTENANCE TASKS

### Regular Maintenance
- [ ] Review and update dependencies quarterly
- [ ] Security audit of credential storage
- [ ] Performance profiling and optimization
- [ ] Database backup and recovery testing
- [ ] Log rotation and cleanup

### Version Updates
- [ ] Python 3.11 → 3.12 migration plan
- [ ] python-telegram-bot library updates
- [ ] Railway platform updates

---

## 💡 FEATURE REQUESTS (From Users/Clients)

*Document feature requests here as they come in*

**Format:**
```
### FR-001: Feature Title
**Requested by:** Client Name / User
**Date:** YYYY-MM-DD
**Description:** Detailed description
**Priority:** High/Medium/Low
**Status:** Reviewing / Approved / Rejected
```

---

## 📊 METRICS TO TRACK

### Performance Metrics
- Average verification time (affiliation + MT5 + trading check)
- API response times (per endpoint)
- Job execution times
- Bot uptime percentage

### Business Metrics
- User conversion rate (started → verified)
- MT5 completion rate (verified → MT5 complete)
- Retention rate (active users after 30/60/90 days)
- Partner switch rate (% of users switching)
- Inactivity rate (users removed for inactivity)

---

## 🎯 UPCOMING MILESTONES

### Milestone 1: Stability & Performance (Q3 2026)
- [ ] Fix all known bugs
- [ ] Implement caching layer
- [ ] Achieve 99.9% uptime
- [ ] Complete unit test coverage (70%+)

### Milestone 2: Enhanced Admin Tools (Q4 2026)
- [ ] Analytics dashboard
- [ ] Bulk management commands
- [ ] Export & reporting features
- [ ] Multi-admin support

### Milestone 3: User Experience 2.0 (Q1 2027)
- [ ] Multi-language support
- [ ] User dashboard
- [ ] Enhanced onboarding
- [ ] Telegram Mini App (if feasible)

---

**Notes:**
- Update this file after completing tasks
- Move completed items to "COMPLETED" section with completion date
- Keep this file in version control
- Review priorities monthly
