import asyncio
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_JSESSIONID
from .api import Play24Client, Play24AuthError, Play24ConnectionError
from .authenticator import Play24Authenticator

_LOGGER = logging.getLogger(__name__)

STEP_JSESSIONID_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_JSESSIONID): str,
})

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("method", default="sms"): vol.In({
        "sms": "Numer telefonu i kod SMS",
        "jsessionid": "Ciasteczko JSESSIONID",
    }),
    vol.Optional(CONF_JSESSIONID): str,
})

STEP_SMS_DATA_SCHEMA = vol.Schema({
    vol.Required("msisdn"): str,
})

STEP_OTP_DATA_SCHEMA = vol.Schema({
    vol.Required("otp"): str,
})


class Play24ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Play24."""

    VERSION = 1

    def __init__(self):
        self._auth = Play24Authenticator()

    async def _async_get_primary_msisdn(self, client: Play24Client) -> str | None:
        """Fetch MSISDN to anchor unique_id."""
        try:
            msisdns = await client.async_get_context_msisdns()
            if msisdns:
                return msisdns[0]
            other = await client.async_get_other_tile()
            raw = other.get("msisdn")
            if raw:
                clean = re.sub(r"\D", "", str(raw))
                if len(clean) >= 9:
                    return clean[-9:]
        except Exception as ex:
            _LOGGER.debug("Could not resolve primary MSISDN for unique_id: %s", ex)
        return None

    def _create_or_update_entry(self, jsessionid: str) -> config_entries.ConfigFlowResult:
        if self.source in (config_entries.SOURCE_REAUTH, config_entries.SOURCE_RECONFIGURE):
            entry_id = self.context.get("entry_id")
            entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
            if entry:
                reason = "reconfigure_successful" if self.source == config_entries.SOURCE_RECONFIGURE else "reauth_successful"
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_JSESSIONID: jsessionid},
                    reason=reason,
                )
        
        return self.async_create_entry(
            title="Play24",
            data={CONF_JSESSIONID: jsessionid}
        )

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
            session = async_get_clientsession(self.hass)
            client = Play24Client(jsessionid, session)
            try:
                _LOGGER.debug("Testing connection...")
                await client.async_test_connection()
                await client.async_get_csrf()
                primary_msisdn = await self._async_get_primary_msisdn(client)
                if primary_msisdn:
                    await self.async_set_unique_id(f"play24_{primary_msisdn}")
                    if self.source not in (config_entries.SOURCE_REAUTH, config_entries.SOURCE_RECONFIGURE):
                        self._abort_if_unique_id_configured()
                return self._create_or_update_entry(jsessionid)
            except Play24AuthError as e:
                _LOGGER.warning("Play24AuthError during connection test: %s", e)
                errors["base"] = "invalid_auth"
            except Play24ConnectionError as e:
                _LOGGER.warning("Play24ConnectionError during connection test: %s", e)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id=step_id, data_schema=data_schema, errors=errors
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if CONF_JSESSIONID in user_input and user_input[CONF_JSESSIONID]:
                return await self._async_process_jsessionid("user", user_input)
            method = user_input.get("method")
            if method == "sms":
                return await self.async_step_sms()
            if method == "jsessionid":
                return await self.async_step_jsessionid()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA
        )

    async def async_step_jsessionid(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        return await self._async_process_jsessionid("jsessionid", user_input)

    async def async_step_sms(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
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
                    _LOGGER.warning("Play24AuthError requesting SMS: %s", type(e).__name__)
                    errors["base"] = "invalid_auth"
                except Play24ConnectionError as e:
                    _LOGGER.warning("Play24ConnectionError requesting SMS: %s", type(e).__name__)
                    errors["base"] = "cannot_connect"
                except Exception as e:
                    _LOGGER.error("Error requesting SMS: %s", type(e).__name__)
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="sms", data_schema=STEP_SMS_DATA_SCHEMA, errors=errors
        )
        
    async def async_step_otp(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
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
                primary_msisdn = await self._async_get_primary_msisdn(client)
                if primary_msisdn:
                    await self.async_set_unique_id(f"play24_{primary_msisdn}")
                    if self.source not in (config_entries.SOURCE_REAUTH, config_entries.SOURCE_RECONFIGURE):
                        self._abort_if_unique_id_configured()
                
                return self._create_or_update_entry(jsessionid)
            except Play24AuthError as e:
                err_str = str(e).lower()
                _LOGGER.warning("Play24AuthError during OTP verification: %s", type(e).__name__)
                if "błędny kod" in err_str or "nieprawidłowy kod" in err_str or "invalid" in err_str:
                    errors["base"] = "invalid_otp"
                elif "wygasł" in err_str or "expired" in err_str:
                    errors["base"] = "expired_otp"
                elif "limit" in err_str or "zablokowan" in err_str:
                    errors["base"] = "otp_limit_exceeded"
                else:
                    errors["base"] = "invalid_auth"
            except (Play24ConnectionError, asyncio.TimeoutError) as e:
                _LOGGER.warning("Play24ConnectionError during OTP verification: %s", type(e).__name__)
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.warning("Exception during OTP verification: %s", type(e).__name__)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="otp", data_schema=STEP_OTP_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if CONF_JSESSIONID in user_input and user_input[CONF_JSESSIONID]:
                return await self._async_process_jsessionid("reauth_confirm", user_input)
            if "method" in user_input:
                if user_input["method"] == "sms":
                    return await self.async_step_sms()
                return await self.async_step_jsessionid()

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_DATA_SCHEMA
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if CONF_JSESSIONID in user_input and user_input[CONF_JSESSIONID]:
                return await self._async_process_jsessionid("reconfigure", user_input)
            if "method" in user_input:
                if user_input["method"] == "sms":
                    return await self.async_step_sms()
                return await self.async_step_jsessionid()

        return self.async_show_form(
            step_id="reconfigure", data_schema=STEP_USER_DATA_SCHEMA
        )
