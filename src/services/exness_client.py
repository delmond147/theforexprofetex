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
        self, email: str, min_deposit: float = 10.0
    ) -> tuple[bool, str | None]:
        """
        Check if client has an MT5 account with trading activity
        (implies funded with at least the minimum deposit and traded).

        Returns (is_funded, mt5_account_id).
        Uses volume_lots > 0 as proxy for funded + active account.
        """
        accounts = await self.get_client_accounts(email)

        for account in accounts:
            platform = account.get("platform", "").lower()
            volume_lots = float(account.get("volume_lots") or 0)
            account_id = str(account.get("client_account") or "")

            if platform == "mt5" and volume_lots > 0:
                logger.info(
                    "mt5_funded_account_found",
                    email=email,
                    account_id=account_id,
                    volume_lots=volume_lots,
                )
                return True, account_id

        # Check if MT5 exist but not yet funded
        has_mt5 = any(a.get("platform", "").lower() == "mt5" for a in accounts)
        logger.info(
            "mt5_check_result",
            email=email,
            has_mt5=has_mt5,
            funded=False,
            account_count=len(accounts),
        )
        return False, None


exness = ExnessClient()
