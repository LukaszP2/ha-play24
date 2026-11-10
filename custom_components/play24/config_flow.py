import contextlib
import logging
import re
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    Play24AuthError,
    Play24Client,
    Play24ConnectionError,
    Play24DataError,
)
from .authenticator import Play24Authenticator
from .const import (
    CONF_DWRSESSIONID,
    CONF_JSESSIONID,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    SCAN_INTERVAL_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_JSESSIONID_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JSESSIONID): str,
        vol.Optional(CONF_DWRSESSIONID): str,
    }
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("method", default="sms"): vol.In(
            {
                "sms": "Numer telefonu i kod SMS",
                "jsessionid": "Ciasteczko JSESSIONID",
            }
        ),
        vol.Optional(CONF_JSESSIONID): str,
        vol.Optional(CONF_DWRSESSIONID): str,
    }
)

STEP_SMS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("msisdn"): str,
    }
)

STEP_OTP_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("otp"): str,
    }
)


class Play24ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # pyright: ignore[reportCallIssue, reportGeneralTypeIssues] # type: ignore[call-arg]
    """Handle a config flow for Play24."""

    VERSION = 1

    def __init__(self):
        self._auth = Play24Authenticator()

    async def _async_get_account_msisdns(self, client: Play24Client) -> list[str]:
        """Fetch all account MSISDNs to identify account and anchor unique_id."""
        try:
            msisdns = await client.async_get_context_msisdns()
            cleaned: list[str] = []
            if isinstance(msisdns, (list, tuple, set)):
                for num in msisdns:
                    clean = re.sub(r"\D", "", str(num))
                    if len(clean) >= 9:
                        cleaned.append(clean[-9:])
                    elif clean:
                        cleaned.append(clean)
                    else:
                        cleaned.append(str(num))
            elif msisdns and not isinstance(msisdns, bool):
                try:
                    for num in msisdns:
                        clean = re.sub(r"\D", "", str(num))
                        if len(clean) >= 9:
                            cleaned.append(clean[-9:])
                        elif clean:
                            cleaned.append(clean)
                except TypeError:
                    pass
                if not cleaned:
                    try:
                        first = msisdns[0]
                        cleaned.append(str(first))
                    except Exception:
                        pass
            if cleaned:
                return list(dict.fromkeys(cleaned))

            other = await client.async_get_other_tile()
            raw = other.get("msisdn")
            if raw:
                clean = re.sub(r"\D", "", str(raw))
                if len(clean) >= 9:
                    return [clean[-9:]]
                if clean:
                    return [clean]
                return [str(raw)]
        except Play24AuthError:
            raise
        except (
            Play24ConnectionError,
            Play24DataError,
            aiohttp.ClientError,
            TimeoutError,
            KeyError,
            ValueError,
        ) as ex:
            _LOGGER.debug("Could not resolve account MSISDNs for unique_id: %s", ex)
        return []

    async def _async_get_primary_msisdn(self, client: Play24Client) -> str | None:
        """Fetch MSISDN to anchor unique_id."""
        msisdns = await self._async_get_account_msisdns(client)
        return msisdns[0] if msisdns else None

    def _get_target_entry(self) -> config_entries.ConfigEntry | None:
        """Get the existing config entry for reauth or reconfigure."""
        if (
            hasattr(self, "_get_reauth_entry")
            and self.source == config_entries.SOURCE_REAUTH
        ):
            try:
                entry = self._get_reauth_entry()
                if entry:
                    return entry
            except Exception:
                pass
        if (
            hasattr(self, "_get_reconfigure_entry")
            and self.source == config_entries.SOURCE_RECONFIGURE
        ):
            try:
                entry = self._get_reconfigure_entry()
                if entry:
                    return entry
            except Exception:
                pass
        entry_id = self.context.get("entry_id")
        if entry_id and hasattr(self, "hass") and hasattr(self.hass, "config_entries"):
            return self.hass.config_entries.async_get_entry(entry_id)
        return None

    async def _async_validate_or_set_unique_id(self, msisdns: list[str]) -> None:
        """Validate or set unique_id for the config entry."""
        if not msisdns:
            return

        primary_msisdn = msisdns[0]

        if self.source in (
            config_entries.SOURCE_REAUTH,
            config_entries.SOURCE_RECONFIGURE,
        ):
            entry = self._get_target_entry()
            if entry and entry.unique_id:
                entry_digits = re.sub(
                    r"\D", "", entry.unique_id.removeprefix("play24_")
                )
                entry_last9 = (
                    entry_digits[-9:] if len(entry_digits) >= 9 else entry_digits
                )
                msisdn_last9_set = {
                    (
                        re.sub(r"\D", "", m)[-9:]
                        if len(re.sub(r"\D", "", m)) >= 9
                        else re.sub(r"\D", "", m)
                    )
                    for m in msisdns
                }
                is_member = (
                    any(entry.unique_id in (f"play24_{m}", m) for m in msisdns)
                    or bool(entry_last9 and entry_last9 in msisdns)
                    or bool(entry_last9 and entry_last9 in msisdn_last9_set)
                )
                if is_member:
                    await self.async_set_unique_id(entry.unique_id)
                else:
                    await self.async_set_unique_id(f"play24_{primary_msisdn}")
            else:
                await self.async_set_unique_id(f"play24_{primary_msisdn}")
            self._abort_if_unique_id_mismatch(reason="wrong_account")
        else:
            matched_unique_id = None
            if hasattr(self, "hass") and hasattr(self.hass, "config_entries"):
                for existing_entry in self.hass.config_entries.async_entries(DOMAIN):
                    if existing_entry.unique_id:
                        ex_digits = re.sub(
                            r"\D", "", existing_entry.unique_id.removeprefix("play24_")
                        )
                        ex_last9 = ex_digits[-9:] if len(ex_digits) >= 9 else ex_digits
                        if any(
                            existing_entry.unique_id in (f"play24_{m}", m)
                            for m in msisdns
                        ) or bool(ex_last9 and ex_last9 in msisdns):
                            matched_unique_id = existing_entry.unique_id
                            break
            await self.async_set_unique_id(
                matched_unique_id or f"play24_{primary_msisdn}"
            )
            self._abort_if_unique_id_configured()

    def _create_or_update_entry(
        self, jsessionid: str, dwrsessionid: str | None = None
    ) -> config_entries.ConfigFlowResult:
        data = {CONF_JSESSIONID: jsessionid}
        if isinstance(dwrsessionid, str) and dwrsessionid:
            data[CONF_DWRSESSIONID] = dwrsessionid

        if self.source in (
            config_entries.SOURCE_REAUTH,
            config_entries.SOURCE_RECONFIGURE,
        ):
            entry = self._get_target_entry()
            if entry:
                reason = (
                    "reconfigure_successful"
                    if self.source == config_entries.SOURCE_RECONFIGURE
                    else "reauth_successful"
                )
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data,
                    reason=reason,
                )
            return self.async_abort(reason="reauth_failed")

        return self.async_create_entry(title="Play24", data=data)

    async def _async_process_jsessionid(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        data_schema: vol.Schema = STEP_JSESSIONID_DATA_SCHEMA,
    ) -> config_entries.ConfigFlowResult:
        errors = {}
        if user_input is not None:
            raw_session = user_input.get(CONF_JSESSIONID, "")
            jsessionid = str(raw_session).strip()
            raw_dwr = user_input.get(CONF_DWRSESSIONID)
            dwrsessionid = str(raw_dwr).strip() if raw_dwr else None
            session = async_get_clientsession(self.hass)
            client = Play24Client(jsessionid, session, dwrsessionid=dwrsessionid)
            try:
                _LOGGER.debug("Testing connection...")
                await client.async_test_connection()
                await client.async_get_csrf()
                account_msisdns = await self._async_get_account_msisdns(client)
            except Play24AuthError as e:
                _LOGGER.warning("Play24AuthError during connection test: %s", e)
                errors["base"] = "invalid_auth"
            except Play24ConnectionError as e:
                _LOGGER.warning("Play24ConnectionError during connection test: %s", e)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self._async_validate_or_set_unique_id(account_msisdns)
                resolved_jsessionid = (
                    client.jsessionid
                    if isinstance(client.jsessionid, str)
                    else jsessionid
                )
                resolved_dwrsess = (
                    client.dwrsessionid
                    if isinstance(client.dwrsessionid, str)
                    else None
                )
                return self._create_or_update_entry(
                    resolved_jsessionid, resolved_dwrsess
                )

        return self.async_show_form(
            step_id=step_id, data_schema=data_schema, errors=errors
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if user_input.get(CONF_JSESSIONID):
                return await self._async_process_jsessionid("user", user_input)
            method = user_input.get("method")
            if method == "sms":
                return await self.async_step_sms()
            if method == "jsessionid":
                return await self.async_step_jsessionid()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def async_step_jsessionid(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return await self._async_process_jsessionid("jsessionid", user_input)

    async def async_step_sms(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors = {}
        if user_input is not None:
            raw_msisdn = user_input.get("msisdn", "")
            clean_msisdn = re.sub(r"\D", "", str(raw_msisdn))
            if len(clean_msisdn) < 9:
                errors["base"] = "invalid_phone_number"
            else:
                try:
                    _LOGGER.info("SMS authentication requested")
                    await self._auth.async_request_sms(clean_msisdn)
                    return await self.async_step_otp()
                except Play24AuthError as e:
                    _LOGGER.warning(
                        "Play24AuthError requesting SMS: %s", type(e).__name__
                    )
                    errors["base"] = "invalid_auth"
                except Play24ConnectionError as e:
                    _LOGGER.warning(
                        "Play24ConnectionError requesting SMS: %s", type(e).__name__
                    )
                    errors["base"] = "cannot_connect"
                except (aiohttp.ClientError, TimeoutError, OSError) as e:
                    _LOGGER.error("Error requesting SMS: %s", type(e).__name__)
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="sms", data_schema=STEP_SMS_DATA_SCHEMA, errors=errors
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                _LOGGER.info("OTP submitted")
                jsessionid = await self._auth.async_submit_otp(user_input["otp"])
                _LOGGER.info("Play24 session established")

                session = async_get_clientsession(self.hass)
                client = Play24Client(jsessionid, session)
                _LOGGER.debug("Testing connection...")
                await client.async_test_connection()
                await client.async_get_csrf()
                account_msisdns = await self._async_get_account_msisdns(client)
            except Play24AuthError as e:
                err_str = str(e).lower()
                _LOGGER.warning(
                    "Play24AuthError during OTP verification: %s", type(e).__name__
                )
                if (
                    "błędny kod" in err_str
                    or "nieprawidłowy kod" in err_str
                    or "invalid" in err_str
                ):
                    errors["base"] = "invalid_otp"
                elif "wygasł" in err_str or "expired" in err_str:
                    errors["base"] = "expired_otp"
                elif "limit" in err_str or "zablokowan" in err_str:
                    errors["base"] = "otp_limit_exceeded"
                else:
                    errors["base"] = "invalid_auth"
            except (TimeoutError, Play24ConnectionError) as e:
                _LOGGER.warning(
                    "Play24ConnectionError during OTP verification: %s",
                    type(e).__name__,
                )
                errors["base"] = "cannot_connect"
            except (aiohttp.ClientError, OSError) as e:
                _LOGGER.warning(
                    "Exception during OTP verification: %s", type(e).__name__
                )
                errors["base"] = "cannot_connect"
            else:
                await self._async_validate_or_set_unique_id(account_msisdns)
                resolved_jsessionid = (
                    client.jsessionid
                    if isinstance(client.jsessionid, str)
                    else jsessionid
                )
                resolved_dwrsess = (
                    client.dwrsessionid
                    if isinstance(client.dwrsessionid, str)
                    else None
                )
                return self._create_or_update_entry(
                    resolved_jsessionid, resolved_dwrsess
                )

        return self.async_show_form(
            step_id="otp", data_schema=STEP_OTP_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if user_input.get(CONF_JSESSIONID):
                return await self._async_process_jsessionid(
                    "reauth_confirm", user_input
                )
            if "method" in user_input:
                if user_input["method"] == "sms":
                    return await self.async_step_sms()
                return await self.async_step_jsessionid()

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_DATA_SCHEMA
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if user_input.get(CONF_JSESSIONID):
                return await self._async_process_jsessionid("reconfigure", user_input)
            if "method" in user_input:
                if user_input["method"] == "sms":
                    return await self.async_step_sms()
                return await self.async_step_jsessionid()

        return self.async_show_form(
            step_id="reconfigure", data_schema=STEP_USER_DATA_SCHEMA
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "Play24OptionsFlowHandler":
        """Get the options flow for this handler."""
        return Play24OptionsFlowHandler(config_entry)

    @classmethod
    @callback
    def add_options_flow(
        cls,
        config_entry: config_entries.ConfigEntry,
    ) -> "Play24OptionsFlowHandler":
        """Create and return the options flow for this handler."""
        return cls.async_get_options_flow(config_entry)


class Play24OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Play24 options."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        if config_entry is not None:
            self._config_entry = config_entry

    @property
    def config_entry(self) -> config_entries.ConfigEntry | None:
        """Return the config entry."""
        if hasattr(self, "_config_entry") and self._config_entry is not None:
            return self._config_entry
        try:
            return super().config_entry
        except (AttributeError, KeyError):
            pass
        if (
            hasattr(self, "handler")
            and hasattr(self, "hass")
            and hasattr(self.hass, "config_entries")
        ):
            entry = self.hass.config_entries.async_get_entry(self.handler)
            if entry is not None:
                return entry
        return getattr(self, "_config_entry", None)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            for key in (CONF_SCAN_INTERVAL_HOURS, CONF_SCAN_INTERVAL):
                if key in user_input:
                    with contextlib.suppress(ValueError, TypeError):
                        user_input[key] = int(user_input[key])
            if (
                CONF_SCAN_INTERVAL_HOURS in user_input
                and CONF_SCAN_INTERVAL not in user_input
            ):
                user_input[CONF_SCAN_INTERVAL] = user_input[CONF_SCAN_INTERVAL_HOURS]
            elif (
                CONF_SCAN_INTERVAL in user_input
                and CONF_SCAN_INTERVAL_HOURS not in user_input
            ):
                user_input[CONF_SCAN_INTERVAL_HOURS] = user_input[CONF_SCAN_INTERVAL]
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry
        current_interval = DEFAULT_SCAN_INTERVAL_HOURS
        if entry and getattr(entry, "options", None):
            current_interval = entry.options.get(
                CONF_SCAN_INTERVAL_HOURS,
                entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS),
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_HOURS,
                        default=current_interval,
                    ): vol.In(SCAN_INTERVAL_OPTIONS),
                },
                extra=vol.ALLOW_EXTRA,
            ),
        )

