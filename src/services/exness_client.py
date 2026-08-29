"""
exness_client.py — Async HTTP client for the Exness Partnership API.

Auth strategy (fully automatic, no manual intervention needed):
1. Load JWT token from DB (set via /settoken) or cache
2. On 401: try POST /api/v2/auth/token/ to refresh silently
3. On refresh fail: re-login with stored credentials
4. On login fail: notify admin to run /settoken manually
"""

from __future__ import annotations
from datetime import timedelta
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
        logger.info(
            "client_accounts_raw",
            email=email,
            data=str(data)[:500],
        )

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
        Check if client has a NEW MT5 account with confirmed trading volume.

        1. MT5 account exists
        2. Account created on or after verified_at (new account)
        3. volume_lots > 0 (real trades placed = account was funded)
        STRICT check: client must have a NEW MT5 account with volume_lots > 0.

        volume_lots > 0 = real trades placed = account was funded.
        No volume = no trades = account not funded = DENY ACCESS.

        Returns (is_funded, mt5_account_id, is_new_account)
        """
        from datetime import datetime, timedelta

        accounts = await self.get_client_accounts(email)

        logger.info(
            "mt5_check_inputs",
            email=email,
            verified_at=verified_at,
            account_count=len(accounts),
            accounts_summary=str(
                [
                    {
                        "id": str(a.get("client_account", "")),
                        "platform": str(a.get("platform", "")),
                        "created": str(a.get("client_account_created", "")),
                        "volume_lots": str(a.get("volume_lots", "0")),
                    }
                    for a in accounts
                ]
            )[:600],
        )

        if not accounts:
            return False, None, False

        # Parse verified_at date once
        verified_date = None
        if verified_at:
            try:
                verified_date = datetime.fromisoformat(verified_at[:10]).date()
            except Exception as e:
                logger.error(
                    "verified_at_parse_failed", verified_at=verified_at, error=str(e)
                )
                # If we can't parse verified_at, be STRICT — treat all as old
                verified_date = None

        new_funded = []
        new_unfunded = []
        old_funded = []

        for account in accounts:
            platform = str(account.get("platform") or "").lower().strip()
            if platform != "mt5":
                continue

            account_id = str(account.get("client_account") or "").strip()
            created_str = str(account.get("client_account_created") or "").strip()
            volume_lots = float(account.get("volume_lots") or 0)

            if not account_id:
                continue

            # ── Is this a NEW account? ────────────────────────────────────────
            is_new = False
            if verified_date and created_str:
                try:
                    created_date = datetime.fromisoformat(created_str[:10]).date()
                except Exception as e:
                    logger.error(
                        "created_date_parse_failed", created=created_str, error=str(e)
                    )
                    created_date = None

                    # Account must be created on or after verification date
                    # 1 day buffer for timezone differences only
                    is_new = created_date >= (verified_date - timedelta(days=1))
                except Exception as e:
                    logger.error(
                        "created_date_parse_failed", created=created_str, error=str(e)
                    )
                    is_new = False  # parse failed = treat as old = STRICT
            elif not verified_date:
                # No verified_at = cannot determine newness = STRICT = old
                is_new = False

            # ── Is this account funded and traded? ────────────────────────────
            is_funded = volume_lots > 0

            logger.info(
                "mt5_account_result",
                account_id=account_id,
                created=created_str,
                verified_date=str(verified_date),
                is_new=is_new,
                volume_lots=volume_lots,
                is_funded=is_funded,
            )

        if is_new and is_funded:
            new_funded.append(account_id)
        elif is_new and not is_funded:
            new_unfunded.append(account_id)
        elif not is_new and is_funded:
            old_funded.append(account_id)

        logger.info(
            "mt5_final_decision",
            email=email,
            new_funded=new_funded,
            new_unfunded=new_unfunded,
            old_funded=old_funded,
        )

        # ── CASE 1: New + funded + traded = FULL PASS ✅ ──────────────────────
        if new_funded:
            logger.info("mt5_pass", email=email, account_id=new_funded[0])
            return True, new_funded[0], True

        # ── CASE 2: New account exists but NOT funded ⏳ ──────────────────────
        if new_unfunded:
            logger.info("mt5_new_not_funded", email=email, account_id=new_unfunded[0])
            return False, new_unfunded[0], True

        # ── CASE 3: Only old funded accounts ❌ ───────────────────────────────
        if old_funded:
            logger.info("mt5_old_only", email=email, account_id=old_funded[0])
            return False, old_funded[0], False

        # ── CASE 4: Nothing usable ❌ ─────────────────────────────────────────
        logger.info("mt5_nothing_found", email=email)
        return False, None, False

    async def check_reentry_eligibility(
        self, email: str, mt5_account_id: str
    ) -> tuple[bool, str]:
        """
        Check if a previously verified kicked user can re-enter the group.
        Used when removed=1 but mt5_verified=1 already.

        Checks:
        1. Still under partner affiliation
        2. Existing MT5 account still has trading activity

        Returns (can_rejoin, reason_if_not)
        """

        # Check 1: Still affiliated with partner
        affiliation = await self.check_partner_affiliation(email)
        if not isinstance(affiliation, dict) or not affiliation.get("affiliation"):
            logger.info("reentry_denied_not_affiliated", email=email)
            return False, "Partner_Switched"

        # Check 2: Existing MT5 account still has volume
        accounts = await self.get_client_accounts(email)
        for account in accounts:
            account_id = str(account.get("client_account") or "")
            volume_lots = float(account.get("volume_lots") or 0)

            if account_id == mt5_account_id and volume_lots > 0:
                logger.info(
                    "reentry_approved",
                    email=email,
                    account_id=account_id,
                    volume_lots=volume_lots,
                )
                return True, "Ok"

        # MT5 found but no volume = not eligible
        logger.info(
            "reentry_denied_no_trading",
            email=email,
            account_id=mt5_account_id,
        )
        return False, "No_Trading_Volume"

        # async def check_mt5_funded(
        #     self,
        #     email: str,
        #     min_deposit: float = 50.0,
        #     verified_at: str | None = None,
        # ) -> tuple[bool, str | None, bool]:
        #     """
        #     Check if client has a NEW MT5 account with confirmed trading volume.

        #     A funded account MUST have volume_lots > 0.
        #     volume_lots only appears after real trades are placed on a funded account.
        #     An account with no deposit will always have volume_lots = 0.

        #     Returns (is_funded_and_traded, mt5_account_id, is_new_account).
        #     ALL THREE must be satisfied for a True result:
        #     1. MT5 account exists
        #     2. Account created on or after verified_at (new account)
        #     3. volume_lots > 0 (real trades placed = account was funded)
        #     """

        #     from datetime import datetime, timedelta

        #     accounts = await self.get_client_accounts(email)
        # logger.info(
        #     "mt5_debug_inputs",
        #     email=email,
        #     verified_at=verified_at,
        #     verified_at_type=type(verified_at).__name__,
        #     total_accounts=len(accounts),
        #     raw_accounts=str([{
        #         "id": a.get("client_account"),
        #         "platform": a.get("platform"),
        #         "created": a.get("client_account_created"),
        #         "volume_lots": a.get("volume_lots"),
        #         "last_trade": a.get("client_account_last_trade"),
        #     } for a in accounts])[:600],
        # )

        #     if not accounts:
        #         logger.info("mt5_no_accounts_found", email=email)
        #         return False, None, False

        #     new_funded = []  # new MT5 accounts with volume_lots > 0
        #     new_unfunded = []  # new MT5 account with volume_lots == 0
        #     old_funded = []  # old MT5 account with volume_lots > 0
        #     old_unfunded = []  # old MT5 account with volume_lots == 0

        #     for account in accounts:
        #         platform = str(account.get("platform", "")).lower()
        #         if platform != "mt5":
        #             continue

        #         account_id = str(account.get("client_account") or "")
        #         created_date = str(account.get("client_account_created") or "")
        #         volume_lots = float(account.get("volume_lots") or 0)
        #         volume_min_usd = float(account.get("volume_min_usd") or 0)
        #         last_trade = account.get("client_account_last_trade") or ""

        #         if not account_id:
        #             continue

        #         # --- Determine if account is NEW
        #         is_new = False
        #         if verified_at and created_date:
        #             try:
        #                 created_dt = datetime.fromisoformat(created_date[:10]).date()
        #                 verified_dt = datetime.fromisoformat(verified_at[:10]).date()
        #                 # 1-day buffer for timezone edge cases only
        #                 is_new = created_dt >= (verified_dt - timedelta(days=1))
        #             except Exception as e:
        #                 logger.error(
        #                     "date_parse_error",
        #                     created=created_date,
        #                     verified=verified_at,
        #                     error=str(e),
        #                 )
        #                 is_new = False

        #         elif not verified_at:
        #             is_new = True
        #         # ── Funding check ─────────────────────────────────────────────────
        #         # volume_lots > 0 is the only reliable proof of funding via this API.
        #         # Real trades cannot be placed without a funded account.
        #         is_funded = volume_lots > 0

        #         logger.info(
        #             "mt5_account_evaluated",
        #             account_id=account_id,
        #             created=created_date,
        #             volume_lots=volume_lots,
        #             volume_min_usd=volume_min_usd,
        #             last_trade=last_trade,
        #             is_new=is_new,
        #             is_funded=is_funded,
        #             min_deposit_required=min_deposit,
        #         )

        #         # ── Categorize ────────────────────────────────────────────────────
        #         if is_new and is_funded:
        #             new_funded.append(account)
        #         elif is_new and not is_funded:
        #             new_unfunded.append(account)
        #         elif not is_new and is_funded:
        #             old_funded.append(account)
        #         else:
        #             old_unfunded.append(account)

        #     logger.info(
        #         "mt5_categorized",
        #         email=email,
        #         new_funded=len(new_funded),
        #         new_unfunded=len(new_unfunded),
        #         old_funded=len(old_funded),
        #         old_unfunded=len(old_unfunded),
        #     )

        #     # ── Decision — strict priority order ──────────────────────────────────

        #     # CASE 1: New account + funded + traded = FULL PASS ✅
        #     if new_funded:
        #         best = new_funded[0]
        #         account_id = str(best.get("client_account") or "")
        #         volume = float(best.get("volume_lots") or 0)
        #         logger.info(
        #             "mt5_full_pass",
        #             email=email,
        #             account_id=account_id,
        #             volume_lots=volume,
        #             min_deposit_usd=min_deposit,
        #         )
        #         return True, account_id, True

        #     # CASE 2: New account exists but volume is 0 = not yet funded ⏳
        #     if new_unfunded:
        #         account_id = str(new_unfunded[0].get("client_account") or "")
        #         logger.info(
        #             "mt5_not_yet_funded",
        #             email=email,
        #             account_id=account_id,
        #             min_deposit_required=min_deposit,
        #         )
        #         return False, account_id, True

        #     # CASE 3: Only old accounts with trades = wrong partner ❌
        #     if old_funded:
        #         account_id = str(old_funded[0].get("client_account") or "")
        #         logger.info(
        #             "mt5_old_account_funded_only",
        #             email=email,
        #             account_id=account_id,
        #         )
        #         return False, account_id, False

        #     # CASE 4: Old unfunded or nothing at all ❌
        #     if old_unfunded:
        #         account_id = str(old_unfunded[0].get("client_account") or "")
        #         logger.info("mt5_old_account_unfunded", email=email)
        #         return False, account_id, False
        #     logger.info("mt5_no_accounts_found", email=email)
        #     return False, None, False

        # async def _check_account_has_trades(self, account_id: str) -> bool:
        #     """
        #     Check if a specific MT5 account has at least one closed trade.
        #     """
        #     try:
        #         # Try without date filter first — get all orders ever
        #         data = await self._get(
        #             "/reports/orders/", params={"client_account": account_id}
        #         )
        #         logger.info(
        #             "orders_full_response",
        #             account_id=account_id,
        #             response_type=type(data).__name__,
        #             data=str(data)[:500],
        #         )

        #         if data is None:
        #             logger.warning("orders_returned_none", account_id=account_id)
        #             return False

        #         if isinstance(data, dict):
        #             orders = data.get("data") or []
        #             totals = data.get("totals") or {}
        #             total_count = int(totals.get("count") or 0)

        #             logger.info(
        #                 "orders_parsed",
        #                 account_id=account_id,
        #                 orders_count=len(orders),
        #                 totals_count=total_count,
        #             )

        #             if len(orders) > 0 or total_count > 0:
        #                 return True

        #         if isinstance(data, list) and len(data) > 0:
        #             logger.info(
        #                 "orders_list_format", account_id=account_id, count=len(data)
        #             )
        #             return True

        #         logger.info("orders_empty", account_id=account_id)
        #         return False

        #     except Exception as e:
        #         logger.error("orders_check_failed", account_id=account_id, error=str(e))
        #         return False

    async def close(self) -> None:
        """Close the underlying HTTP client and release connection pool."""
        try:
            await self._client.aclose()
            logger.info("exness_http_client_closed")
        except Exception as e:
            logger.error("exness_http_client_close_error", error=str(e))


exness = ExnessClient()
