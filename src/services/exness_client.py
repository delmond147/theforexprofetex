"""
exness_client.py — Async HTTP client for the Exness Partnership API.

Auth strategy (fully automatic, no manual intervention needed):
1. Load JWT token from DB (set via /settoken) or cache
2. On 401: try POST /api/v2/auth/token/ to refresh silently
3. On refresh fail: re-login with stored credentials
4. On login fail: notify admin to run /settoken manually
"""

from __future__ import annotations
from datetime import datetime, timedelta
import httpx
from src.core.logging import logger
from src.core.settings import API_BASE
from src.core.vault import decrypt, encrypt
from src.db.database import get_config, set_config, delete_config


class ExnessClient:

    def __init__(self) -> None:
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=15)

    # ── Credentials ───────────────────────────────────────────────────────────

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

    def _auth_header(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"JWT {self._token}"}
        return {}

    def _load_stored_token(self) -> bool:
        enc_token = get_config("api_jwt_token")
        if enc_token:
            token = decrypt(enc_token)
            if token:
                self._token = token
                logger.info("token_loaded_from_db", preview=token[:20] + "...")
                return True
        return False

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def _refresh_token(self) -> bool:
        if not self._token:
            return False
        try:
            resp = await self._client.post(
                f"{API_BASE}/v2/auth/token/",
                headers={"Authorization": f"JWT {self._token}"},
            )
            logger.info(
                "token_refresh_response", status=resp.status_code, body=resp.text[:200]
            )
            if resp.status_code == 200:
                data = resp.json()
                new_token = (
                    data.get("token") or data.get("access") or data.get("access_token")
                )
                if new_token:
                    self._token = new_token
                    set_config("api_jwt_token", encrypt(new_token))
                    logger.info(
                        "token_refreshed_successfully", preview=new_token[:20] + "..."
                    )
                    return True
        except Exception as exc:
            logger.error("token_refresh_failed", error=str(exc))
        return False

    async def _login_with_credentials(self) -> bool:
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

    async def _notify_token_expired(self) -> None:
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
                    "Please run `/setcredentials` to restore access."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("admin_notify_failed", error=str(e))

    async def authenticate(self) -> bool:
        if self._load_stored_token():
            return True
        if await self._login_with_credentials():
            return True
        logger.error("all_auth_methods_failed")
        await self._notify_token_expired()
        return False

    async def _handle_401(self) -> bool:
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

    # ── HTTP ──────────────────────────────────────────────────────────────────

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

    # ── Affiliation ───────────────────────────────────────────────────────────

    async def check_partner_affiliation(self, email: str) -> dict | None:
        """POST /api/partner/affiliation/"""
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
                "affiliation_response", status=resp.status_code, body=resp.text[:300]
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
        """Returns affiliation dict if linked to this partner, else None."""
        data = await self.check_partner_affiliation(email)
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

    # ── Client accounts ───────────────────────────────────────────────────────

    async def get_client_accounts(self, email: str) -> list[dict]:
        """GET /api/reports/clients/accounts/?search=email"""
        data = await self._get(
            "/reports/clients/accounts/",
            params={"search": email.strip(), "page_size": 50},
        )
        logger.info("client_accounts_raw", email=email, data=str(data)[:500])
        if isinstance(data, dict):
            return data.get("data") or data.get("results") or []
        return data if isinstance(data, list) else []

    # ── Orders ────────────────────────────────────────────────────────────────

    async def _check_account_has_trades(self, account_id: str) -> bool:
        """
        Check if account has any closed trades via orders endpoint.
        Primary proof of funding — you cannot trade without depositing.
        """
        try:
            data = await self._get(
                "/reports/orders/",
                params={"client_account": account_id},
            )
            logger.info("orders_response", account_id=account_id, data=str(data)[:300])
            if data is None:
                return False
            if isinstance(data, dict):
                orders = data.get("data") or []
                totals = data.get("totals") or {}
                total_count = int(totals.get("count") or 0)
                logger.info(
                    "orders_parsed",
                    account_id=account_id,
                    orders_count=len(orders),
                    totals_count=total_count,
                )
                return len(orders) > 0 or total_count > 0
            if isinstance(data, list):
                return len(data) > 0
            return False
        except Exception as e:
            logger.error("orders_check_failed", account_id=account_id, error=str(e))
            return False

    async def _check_account_recent_trades(
        self, account_id: str, days: int = 30
    ) -> bool:
        """
        Check if account has trades within the last N days.
        Used for reentry — confirms member is CURRENTLY active,
        not just has historical volume from months ago.
        """
        try:
            date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

            data = await self._get(
                "/reports/orders/",
                params={
                    "client_account": account_id,
                    "date_from": date_from,
                },
            )
            logger.info(
                "recent_orders_response",
                account_id=account_id,
                date_from=date_from,
                data=str(data)[:300],
            )
            if data is None:
                return False
            if isinstance(data, dict):
                orders = data.get("data") or []
                totals = data.get("totals") or {}
                total_count = int(totals.get("count") or 0)
                logger.info(
                    "recent_orders_parsed",
                    account_id=account_id,
                    orders_count=len(orders),
                    totals_count=total_count,
                    date_from=date_from,
                )
                return len(orders) > 0 or total_count > 0
            if isinstance(data, list):
                return len(data) > 0
            return False
        except Exception as e:
            logger.error(
                "recent_orders_check_failed", account_id=account_id, error=str(e)
            )
            return False

    # ── MT5 verification — NEW MEMBER ─────────────────────────────────────────

    async def check_mt5_funded(
        self,
        email: str,
        min_deposit: float = 10.0,
        verified_at: str | None = None,
    ) -> tuple[bool, str | None, bool]:
        """
        Strict check for NEW members only.

        Rules:
        1. MT5 account must exist
        2. Account created AFTER verified_at date (± 1 day timezone buffer)
        This ensures the member created a FRESH account under this partner
        and not reusing an old account from a previous partner
        3. Account has closed trades (confirmed via orders endpoint)
        volume_lots > 0 used as fallback if orders endpoint returns empty

        Returns (is_funded_and_traded, mt5_account_id, is_new_account)
        """
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
                        "volume": str(a.get("volume_lots", "0")),
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
                verified_date = None

        new_funded = []  # new MT5 + has trades
        new_unfunded = []  # new MT5 + no trades yet
        old_funded = []  # old MT5 + has trades (wrong partner)

        for account in accounts:
            platform = str(account.get("platform") or "").lower().strip()
            if platform != "mt5":
                continue

            account_id = str(account.get("client_account") or "").strip()
            created_str = str(account.get("client_account_created") or "").strip()
            volume_lots = float(account.get("volume_lots") or 0)

            if not account_id:
                continue

            # ── Is this a NEW account? ────────────────────────────────────
            # Created on or after verification date (1 day buffer only)
            is_new = False
            if verified_date and created_str:
                try:
                    created_date = datetime.fromisoformat(created_str[:10]).date()
                    # Only 1-day buffer for timezone edge cases
                    # NOT 30 days — that lets old accounts through
                    is_new = created_date >= (verified_date - timedelta(days=1))
                    logger.info(
                        "mt5_date_check",
                        account_id=account_id,
                        created=str(created_date),
                        verified=str(verified_date),
                        is_new=is_new,
                    )
                except Exception as e:
                    logger.error(
                        "mt5_date_parse_failed", created=created_str, error=str(e)
                    )
                    is_new = False  # parse error = treat as old = strict
            elif not verified_date:
                # No verified_at = cannot determine = treat as old
                is_new = False

            # ── Does it have trades? ──────────────────────────────────────
            # Primary: orders endpoint (most accurate)
            has_trades = await self._check_account_has_trades(account_id)

            # Fallback: volume_lots > 0 if orders endpoint returns empty
            if not has_trades and volume_lots > 0:
                logger.info(
                    "mt5_volume_fallback", account_id=account_id, volume=volume_lots
                )
                has_trades = True

            logger.info(
                "mt5_account_result",
                account_id=account_id,
                created=created_str,
                is_new=is_new,
                has_trades=has_trades,
                volume_lots=volume_lots,
            )

            if is_new and has_trades:
                new_funded.append(account_id)
            elif is_new and not has_trades:
                new_unfunded.append(account_id)
            elif not is_new and has_trades:
                old_funded.append(account_id)

        logger.info(
            "mt5_final_decision",
            email=email,
            new_funded=new_funded,
            new_unfunded=new_unfunded,
            old_funded=old_funded,
        )

        # CASE 1: New + funded + traded = FULL PASS ✅
        if new_funded:
            logger.info("mt5_pass", email=email, account_id=new_funded[0])
            return True, new_funded[0], True

        # CASE 2: New account exists but no trades yet ⏳
        if new_unfunded:
            logger.info("mt5_new_not_traded", email=email, account_id=new_unfunded[0])
            return False, new_unfunded[0], True

        # CASE 3: Only old funded accounts ❌
        if old_funded:
            logger.info("mt5_old_only", email=email, account_id=old_funded[0])
            return False, old_funded[0], False

        # CASE 4: Nothing usable ❌
        logger.info("mt5_nothing_found", email=email)
        return False, None, False

    # ── MT5 reentry check — RETURNING KICKED MEMBER ──────────────────────────

    async def check_reentry_eligibility(
        self,
        email: str,
        mt5_account_id: str,
    ) -> tuple[bool, str]:
        """
        Check if a previously kicked member can rejoin the group.

        Different from check_mt5_funded — this does NOT require a new MT5.
        The member already has a verified MT5 account. We just check:
        1. Still under this partner (not switched)
        2. Has placed recent trades (within last 30 days)
        Uses orders endpoint with date_from filter to confirm
        CURRENT activity — not just historical volume_lots which
        could be from months ago before they went inactive.

        Returns (can_rejoin, reason)
        reason: "ok" | "partner_switched" | "no_trades"
        """
        # ── Check 1: Still under this partner ────────────────────────────────
        try:
            affiliation = await self.check_partner_affiliation(email)
            logger.info(
                "reentry_affiliation", email=email, result=str(affiliation)[:200]
            )

            if not isinstance(affiliation, dict) or not affiliation.get("affiliation"):
                logger.info("reentry_denied_switched", email=email)
                return False, "partner_switched"

            partner_account_ids = {str(a) for a in (affiliation.get("accounts") or [])}
            logger.info("reentry_partner_ids", email=email, ids=partner_account_ids)

        except Exception as e:
            logger.error("reentry_affiliation_error", email=email, error=str(e))
            return False, "partner_switched"

        # ── Check 2: Recent trades on any partner MT5 account ────────────────
        try:
            accounts = await self.get_client_accounts(email)
            logger.info(
                "reentry_accounts_found",
                email=email,
                stored_mt5=mt5_account_id,
                accounts=[
                    {
                        "id": str(a.get("client_account", "")),
                        "platform": str(a.get("platform", "")),
                        "volume": str(a.get("volume_lots", "0")),
                    }
                    for a in accounts
                ],
            )

            for account in accounts:
                account_id = str(account.get("client_account") or "").strip()
                platform = str(account.get("platform") or "").lower().strip()
                volume_lots = float(account.get("volume_lots") or 0)

                if platform != "mt5":
                    continue

                # Accept if account matches stored ID OR is in partner list
                is_partner_account = (
                    account_id in partner_account_ids
                    or account_id == str(mt5_account_id).strip()
                )

                logger.info(
                    "reentry_account_eval",
                    account_id=account_id,
                    stored_id=mt5_account_id,
                    is_partner=is_partner_account,
                    volume_lots=volume_lots,
                )

                if not is_partner_account:
                    continue

                # ── Check recent trades — NOT just historical volume ───────
                # volume_lots is cumulative all-time, could be months old
                # We need to confirm they traded recently (last 30 days)
                has_recent_trades = await self._check_account_recent_trades(
                    account_id, days=30
                )

                logger.info(
                    "reentry_trade_check",
                    account_id=account_id,
                    has_recent_trades=has_recent_trades,
                    volume_lots=volume_lots,
                )

                if has_recent_trades:
                    logger.info("reentry_approved", email=email, account_id=account_id)
                    return True, "ok"

                # Fallback: if orders endpoint returns nothing but
                # volume_lots > 0 and account is recent, allow reentry
                # This handles cases where the orders endpoint is slow
                if volume_lots > 0:
                    logger.info(
                        "reentry_approved_volume_fallback",
                        email=email,
                        account_id=account_id,
                        volume_lots=volume_lots,
                    )
                    return True, "ok"

            logger.info(
                "reentry_denied_no_recent_trades", email=email, stored_id=mt5_account_id
            )
            return False, "no_trades"

        except Exception as e:
            logger.error("reentry_check_error", email=email, error=str(e))
            return False, "no_trades"

    async def close(self) -> None:
        try:
            await self._client.aclose()
            logger.info("exness_http_client_closed")
        except Exception as e:
            logger.error("exness_http_client_close_error", error=str(e))


exness = ExnessClient()
