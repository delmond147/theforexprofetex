"""
exness_client.py — Async HTTP client for the Exness Partnership API.

Auth strategy (fully automatic, no manual intervention needed):
1. Load JWT token from DB (set via /settoken) or cache
2. On 401: try POST /api/v2/auth/token/ to refresh silently
3. On refresh fail: re-login with stored credentials
4. On login fail: notify admin to run /settoken manually
"""

from __future__ import annotations
import httpx
from src.core.logging import logger
from src.core.settings import API_BASE
from src.core.vault import decrypt, encrypt
from src.db.database import get_config, set_config, delete_config


class ExnessClient:

    def __init__(self) -> None:
        self._token: str | None = None
        # FIXED: Managed persistent client session instance to handle connection pooling efficiently
        self._client = httpx.AsyncClient(timeout=15)

    # ── Load credentials ──────────────────────────────────────────────────────

    def _get_credentials(self) -> tuple[str, str] | tuple[None, None]:
        enc_login = get_config("api_login")
        enc_password = get_config("api_password")
        if not enc_login or not enc_password:
            return None, None
        login = decrypt(enc_login)
        password = decrypt(enc_password)
        if not login or not password:
            return None, None
        return login, password

    def has_credentials(self) -> bool:
        return bool(get_config("api_login") and get_config("api_password"))

    # ── Auth header ───────────────────────────────────────────────────────────

    def _auth_header(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"JWT {self._token}"}
        return {}

    # ── Step 1: Load token from DB ────────────────────────────────────────────

    def _load_stored_token(self) -> bool:
        """Load JWT token stored via /settoken."""
        enc_token = get_config("api_jwt_token")
        if enc_token:
            token = decrypt(enc_token)
            if token:
                self._token = token
                logger.info("token_loaded_from_db", preview=token[:20] + "...")
                return True
        return False

    # ── Step 2: Refresh token ─────────────────────────────────────────────────

    async def _refresh_token(self) -> bool:
        """
        Try to refresh the current token silently.
        POST /api/v2/auth/token/
        """
        if not self._token:
            return False
        try:
            # FIXED: Migrated from isolated connection calls to persistent connection client pooling
            resp = await self._client.post(
                f"{API_BASE}/v2/auth/token/",
                headers={"Authorization": f"JWT {self._token}"},
            )
            logger.info(
                "token_refresh_response",
                status=resp.status_code,
                body=resp.text[:200],
            )
            if resp.status_code == 200:
                data = resp.json()
                new_token = (
                    data.get("token") or data.get("access") or data.get("access_token")
                )
                if new_token:
                    self._token = new_token
                    # Save refreshed token to DB
                    set_config("api_jwt_token", encrypt(new_token))
                    logger.info(
                        "token_refreshed_successfully",
                        preview=new_token[:20] + "...",
                    )
                    return True
        except Exception as exc:
            logger.error("token_refresh_failed", error=str(exc))
        return False

    # ── Step 3: Re-login with credentials ────────────────────────────────────

    async def _login_with_credentials(self) -> bool:
        """
        Full re-login using stored credentials.
        POST /api/v2/auth/
        """
        login, password = self._get_credentials()
        if not login or not password:
            logger.warning("no_credentials_for_relogin")
            return False
        try:
            resp = await self._client.post(
                f"{API_BASE}/v2/auth/",
                json={"login": login, "password": password},
            )
            logger.info(
                "relogin_response", status=resp.status_code, body=resp.text[:200]
            )
            resp.raise_for_status()
            data = resp.json()
            new_token = (
                data.get("token")
                or data.get("access")
                or data.get("access_token")
                or data.get("jwt")
                or data.get("key")
            )
            if new_token:
                self._token = new_token
                set_config("api_jwt_token", encrypt(new_token))
                logger.info("relogin_successful", preview=new_token[:20] + "...")
                return True
        except Exception as exc:
            logger.error("relogin_failed", error=str(exc))
        return False

    # ── Step 4: Notify admin ──────────────────────────────────────────────────

    async def _notify_token_expired(self) -> None:
        """Notify admin when all auth methods have failed."""
        from src.core.settings import ADMIN_CHAT_ID, BOT_TOKEN

        if not ADMIN_CHAT_ID:
            return
        try:
            from telegram import Bot

            bot = Bot(token=BOT_TOKEN)
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "⚠️ *API Authentication Failed*\n\n"
                    "The bot could not authenticate with the Exness API.\n\n"
                    "Please do one of the following:\n\n"
                    "✅ *Option 1 — Quick fix:*\n"
                    "Get a token from Swagger UI and send:\n"
                    "`/settoken your_token_here`\n\n"
                    "✅ *Option 2 — Permanent fix:*\n"
                    "Set your credentials so the bot logs in automatically:\n"
                    "`/setcredentials your_email your_password`"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("admin_notify_failed", error=str(e))

    # ── Main authenticate method ──────────────────────────────────────────────

    async def authenticate(self) -> bool:
        """
        Full auth chain:
        1. Load stored token from DB
        2. Try token refresh
        3. Try credential re-login
        4. Notify admin if all fail
        """
        if self._load_stored_token():
            return True

        if await self._login_with_credentials():
            return True

        logger.error("all_auth_methods_failed")
        await self._notify_token_expired()
        return False

    async def _handle_401(self) -> bool:
        """
        Called when API returns 401.
        Tries refresh then re-login before giving up.
        """
        logger.warning("got_401_attempting_recovery")

        self._token = None
        if await self._refresh_token():
            return True

        if await self._login_with_credentials():
            return True

        logger.error("token_recovery_failed")
        delete_config("api_jwt_token")
        await self._notify_token_expired()
        return False

    # ── Generic GET request ───────────────────────────────────────────────────

    async def _get(
        self,
        endpoint: str,
        params: dict | None = None,
        _retry: bool = True,
    ) -> dict | list | None:
        if not self._token:
            ok = await self.authenticate()
            if not ok:
                return None

        try:
            url = f"{API_BASE}{endpoint}"
            resp = await self._client.get(
                url,
                headers=self._auth_header(),
                params=params or {},
            )
            logger.info("api_response", status=resp.status_code, body=resp.text[:300])

            if resp.status_code == 401 and _retry:
                ok = await self._handle_401()
                if not ok:
                    return None
                return await self._get(endpoint, params, _retry=False)

            if resp.status_code == 404:
                return resp.json()

            resp.raise_for_status()
            return resp.json()

        except Exception as exc:
            logger.error("api_get_failed", error=str(exc), endpoint=endpoint)
            return None

    # ── Affiliation check — PRIMARY verification method ───────────────────────

    async def check_partner_affiliation(self, email: str) -> dict | None:
        """
        POST /api/partner/affiliation/
        {"email": "client@email.com"}
        """
        if not self._token:
            ok = await self.authenticate()
            if not ok:
                return None

        try:
            resp = await self._client.post(
                f"{API_BASE}/partner/affiliation/",
                headers=self._auth_header(),
                json={"email": email.strip()},
            )
            logger.info(
                "affiliation_response",
                status=resp.status_code,
                body=resp.text[:300],
            )

            if resp.status_code == 401:
                ok = await self._handle_401()
                if not ok:
                    return None
                resp = await self._client.post(
                    f"{API_BASE}/partner/affiliation/",
                    headers=self._auth_header(),
                    json={"email": email.strip()},
                )

            if resp.status_code in (400, 404):
                return {"affiliation": False}

            resp.raise_for_status()
            return resp.json()

        except Exception as exc:
            logger.error("affiliation_check_failed", error=str(exc))
            return None

    async def find_client_by_email(self, email: str) -> dict | None:
        """
        Returns affiliation dict if client is linked to this partner.
        Returns None if not linked or not found.
        """
        data = await self.check_partner_affiliation(email)

        # FIXED: Added fallback checking mechanism to ensure safely returning None on non-dictionary/empty outputs
        if not isinstance(data, dict):
            logger.info("affiliation_no_response", email=email)
            return None

        affiliated = data.get("affiliation", False)
        logger.info(
            "affiliation_result",
            email=email,
            affiliated=affiliated,
            client_uid=data.get("client_uid"),
        )

        return data if affiliated else None

    # ── Other endpoints ───────────────────────────────────────────────────────

    async def get_client_orders(
        self, client_account: str, date_from: str | None = None
    ) -> list[dict]:
        """
        Fetch trade orders for a specific client account.
        GET /api/reports/orders/

        Returns list of order dicts with:
        - volume_lots: lots traded
        - close_date: when trade last closed
        - client_account: MT5 account number
        """
        params: dict = {"client_account": client_account}
        if date_from:
            params["date_from"] = date_from

        data = await self._get("/reports/orders/", params=params)
        logger.info(
            "client_orders_response",
            client_account=client_account,
            data=str(data)[:300],
        )

        if isinstance(data, dict):
            return data.get("data") or []
        return []

    async def check_recent_trading(
        self, client_account: str, days: int = 15
    ) -> tuple[bool, float]:
        """
        Check if a client has traded in the last N days.
        Returns (has_traded_recently, total_reward_usd)
        """

        from datetime import datetime, timedelta

        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        orders = await self.get_client_orders(
            client_account=client_account, date_from=date_from
        )

        if not orders:
            return False, 0.0
        total_reward = sum(float(order.get("reward_usd", 0)) for order in orders)
        return True, total_reward

    # ── Client accounts ─────────────────────────────────────────────────────

    async def get_client_accounts(self, email: str) -> list[dict]:
        """
        Fetch all trading accounts for a client email.
        GET /api/reports/clients/accounts/?search=email

        Returns list of account dicts. Each dict contains:
        - platform: "mt5" or "mt4"
        - volume_lots: total lots traded (> 0 means funded and traded)
        - client_account_created: date account was created
        - client_account_last_trade: last trade date
        - client_account: account number/ID
        """
        data = await self._get(
            "/reports/clients/accounts/",
            params={"search": email.strip(), "page_size": 50},
        )
        logger.info("client_accounts_response", email=email, data=str(data)[:300])

        if isinstance(data, dict):
            return data.get("data") or data.get("results") or []
        return data if isinstance(data, list) else []

    async def check_mt5_funded(
        self,
        email: str,
        min_deposit: float = 10.0,
        verified_at: str | None = None,
    ) -> tuple[bool, str | None, bool]:
        """
        Check if client has a NEW MT5 account created after verification
        that has confirmed trading activity (closed trades via orders endpoint).

        Returns (is_funded_and_traded, mt5_account_id, is_new_account).

        Criteria for full pass:
        1. MT5 account exists
        2. Account was created AFTER verified_at date (new account)
        3. Has at least one CLOSED trade in orders endpoint (confirms funded + traded)

        All three must be true to return (True, account_id, True).
        """
        from datetime import datetime

        accounts = await self.get_client_accounts(email)
        logger.info(
            "mt5_check_started",
            email=email,
            account_count=len(accounts),
            verified_at=verified_at,
        )

        if not accounts:
            logger.info("mt5_no_accounts_found", email=email)
            return False, None, False

        # Separate MT5 accounts into new and old
        new_mt5_accounts = []
        old_mt5_accounts = []

        for account in accounts:
            platform = str(account.get("platform", "")).lower()
            if platform != "mt5":
                continue

            account_id = str(account.get("client_account") or "")
            created_date = str(account.get("client_account_created") or "")

            if not account_id:
                continue

            # Determine if account is NEW (created after verification)
            is_new = False
            if verified_at and created_date:
                try:
                    # Normalize both dates to date-only for comparison
                    created_dt = datetime.fromisoformat(created_date[:10]).date()
                    verified_dt = datetime.fromisoformat(verified_at[:10]).date()
                    is_new = created_dt >= verified_dt
                    logger.info(
                        "mt5_date_comparison",
                        account_id=account_id,
                        created=str(created_dt),
                        verified=str(verified_dt),
                        is_new=is_new,
                    )
                except Exception as e:
                    logger.error(
                        "mt5_date_parse_error",
                        created=created_date,
                        verified=verified_at,
                        error=str(e),
                    )
                    is_new = False
            elif not verified_at:
                # No verified_at date — treat as new (first time verification)
                is_new = True

            if is_new:
                new_mt5_accounts.append(account_id)
            else:
                old_mt5_accounts.append(account_id)

        logger.info(
            "mt5_accounts_categorized",
            email=email,
            new_count=len(new_mt5_accounts),
            old_count=len(old_mt5_accounts),
        )

        # ── Check new accounts for actual closed trades ───────────────────────────
        for account_id in new_mt5_accounts:
            has_trades = await self._check_account_has_trades(account_id)
            logger.info(
                "mt5_new_account_trade_check",
                account_id=account_id,
                has_trades=has_trades,
            )
            if has_trades:
                logger.info("mt5_fully_verified", email=email, account_id=account_id)
                return True, account_id, True

        # ── New accounts exist but none have trades yet ───────────────────────────
        if new_mt5_accounts:
            logger.info(
                "mt5_new_account_no_trades", email=email, accounts=new_mt5_accounts
            )
            return False, new_mt5_accounts[0], True

        # ── Only old accounts found ───────────────────────────────────────────────
        if old_mt5_accounts:
            logger.info("mt5_old_account_only", email=email, accounts=old_mt5_accounts)
            return False, old_mt5_accounts[0], False

        # ── No MT5 accounts at all ────────────────────────────────────────────────
        logger.info("mt5_no_mt5_accounts", email=email)
        return False, None, False

    async def _check_account_has_trades(self, account_id: str) -> bool:
        """
        Check if a specific MT5 account has at least one closed trade
        using the orders endpoint.

        This is the definitive proof that an account is funded and active —
        you cannot place a trade without funds in the account.
        """
        try:
            data = await self._get(
                "/reports/orders/",
                params={
                    "client_account": account_id,
                    "page_size": 1,  # we only need to know if ANY exist
                },
            )
            logger.info(
                "orders_check_response",
                account_id=account_id,
                data=str(data)[:200],
            )

            if not isinstance(data, dict):
                return False

            orders = data.get("data") or []
            totals = data.get("totals") or {}

            # Check orders list directly
            if orders and len(orders) > 0:
                return True

            # Check totals count as fallback
            total_count = totals.get("count") or 0
            if int(total_count) > 0:
                return True

            return False

        except Exception as e:
            logger.error("orders_check_failed", account_id=account_id, error=str(e))
            # On error assume not funded to avoid false positives
            return False


exness = ExnessClient()
