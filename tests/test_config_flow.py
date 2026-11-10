from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.play24 import update_listener
from custom_components.play24.api import Play24AuthError, Play24ConnectionError
from custom_components.play24.config_flow import (
    Play24ConfigFlow,
    Play24OptionsFlowHandler,
)
from custom_components.play24.const import (
    CONF_JSESSIONID,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)


@pytest.fixture
def mock_setup_entry():
    with patch(
        "custom_components.play24.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_play24_auth():
    with patch("custom_components.play24.config_flow.Play24Authenticator") as mock:
        instance = mock.return_value
        instance.async_request_sms = AsyncMock()
        instance.async_submit_otp = AsyncMock(return_value="new_mock_jsessionid")
        yield instance


@pytest.mark.asyncio
async def test_config_flow_direct_user_jsessionid_success(
    hass: HomeAssistant, mock_setup_entry
):
    """Test user flow directly accepting JSESSIONID without intermediate selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        instance.async_get_context_msisdns = AsyncMock(return_value=["500123456"])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "my_direct_session"},
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Play24"
        assert result["data"][CONF_JSESSIONID] == "my_direct_session"


@pytest.mark.asyncio
async def test_config_flow_direct_user_jsessionid_errors(hass: HomeAssistant):
    """Test auth and connection errors during direct JSESSIONID entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    # 1. Auth error
    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(
            side_effect=Play24AuthError("Session expired")
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "bad_direct_session"},
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"

    # 2. Connection error
    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(
            side_effect=Play24ConnectionError("Timeout")
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "unreachable_session"},
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_config_flow_legacy_method_selection(
    hass: HomeAssistant, mock_setup_entry
):
    """Test backward compatibility when legacy 'method' input is provided."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"method": "jsessionid"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "jsessionid"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        instance.async_get_context_msisdns = AsyncMock(return_value=["500123456"])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "legacy_valid_session"},
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Play24"
        assert result["data"][CONF_JSESSIONID] == "legacy_valid_session"


@pytest.mark.asyncio
async def test_config_flow_reauth_confirm_jsessionid(
    hass: HomeAssistant, mock_setup_entry
):
    """Test reauth flow using clean reauth_confirm step."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "expired_session"},
        unique_id="play24_500123456",
        entry_id="reauth_entry_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        instance.async_get_context_msisdns = AsyncMock(return_value=["500123456"])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "fresh_session_value"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"

        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].data[CONF_JSESSIONID] == "fresh_session_value"


@pytest.mark.asyncio
async def test_config_flow_reconfigure_flow(hass: HomeAssistant, mock_setup_entry):
    """Test reconfigure flow."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "initial_session"},
        unique_id="play24_500123456",
        entry_id="reconfig_entry_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        instance.async_get_context_msisdns = AsyncMock(return_value=["500123456"])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "updated_session_value"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"

        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].data[CONF_JSESSIONID] == "updated_session_value"


@pytest.mark.asyncio
async def test_config_flow_first_setup_sms(
    hass: HomeAssistant, mock_setup_entry, mock_play24_auth
):
    """Test setup via legacy SMS flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"method": "sms"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "sms"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"msisdn": "123456789"},
    )
    mock_play24_auth.async_request_sms.assert_called_once_with("123456789")
    assert result["type"] == "form"
    assert result["step_id"] == "otp"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock()
        instance.async_get_csrf = AsyncMock()
        instance.async_get_finance_tile = AsyncMock()
        instance.async_get_messages = AsyncMock()
        instance.async_get_context_msisdns = AsyncMock()

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"otp": "1234"},
        )

        mock_play24_auth.async_submit_otp.assert_called_once_with("1234")
        instance.async_test_connection.assert_called_once()

        assert result["type"] == "create_entry"
        assert result["title"] == "Play24"
        assert result["data"][CONF_JSESSIONID] == "new_mock_jsessionid"


@pytest.mark.asyncio
async def test_config_flow_reauth_sms(
    hass: HomeAssistant, mock_setup_entry, mock_play24_auth
):
    """Test reauth flow using SMS method."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "expired_session"},
        unique_id="play24_500123456",
        entry_id="reauth_sms_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"method": "sms"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "sms"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"msisdn": "500123456"},
    )
    mock_play24_auth.async_request_sms.assert_called_with("500123456")
    assert result["type"] == "form"
    assert result["step_id"] == "otp"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock()
        instance.async_get_csrf = AsyncMock()
        instance.async_get_context_msisdns = AsyncMock(return_value=["500123456"])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"otp": "9999"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].data[CONF_JSESSIONID] == "new_mock_jsessionid"


@pytest.mark.asyncio
async def test_config_flow_reconfigure_sms(
    hass: HomeAssistant, mock_setup_entry, mock_play24_auth
):
    """Test reconfigure flow using SMS method."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500123456",
        entry_id="reconfig_sms_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"method": "sms"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "sms"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"msisdn": "500123456"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "otp"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock()
        instance.async_get_csrf = AsyncMock()
        instance.async_get_context_msisdns = AsyncMock(return_value=["500123456"])

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"otp": "8888"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].data[CONF_JSESSIONID] == "new_mock_jsessionid"


@pytest.mark.asyncio
async def test_config_flow_otp_error_handling(hass: HomeAssistant, mock_play24_auth):
    """Test OTP error handling: invalid OTP, expired OTP, limit exceeded."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "sms"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"msisdn": "123456789"}
    )
    assert result["step_id"] == "otp"

    # 1. Invalid OTP
    mock_play24_auth.async_submit_otp = AsyncMock(
        side_effect=Play24AuthError("Błędny kod SMS")
    )
    res = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": "0000"}
    )
    assert res["type"] == "form"
    assert res["errors"]["base"] == "invalid_otp"

    # 2. Expired OTP
    mock_play24_auth.async_submit_otp = AsyncMock(
        side_effect=Play24AuthError("Kod SMS wygasł")
    )
    res = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": "1111"}
    )
    assert res["type"] == "form"
    assert res["errors"]["base"] == "expired_otp"

    # 3. Limit exceeded
    mock_play24_auth.async_submit_otp = AsyncMock(
        side_effect=Play24AuthError("Limit prób przekroczony")
    )
    res = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": "2222"}
    )
    assert res["type"] == "form"
    assert res["errors"]["base"] == "otp_limit_exceeded"


@pytest.mark.asyncio
async def test_config_flow_sms_phone_validation(hass: HomeAssistant, mock_play24_auth):
    """Test validation of phone number in SMS step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "sms"}
    )
    assert result["step_id"] == "sms"

    # Too short
    res = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"msisdn": "12345"}
    )
    assert res["type"] == "form"
    assert res["errors"]["base"] == "invalid_phone_number"


@pytest.mark.asyncio
async def test_config_flow_reauth_wrong_account_aborts(hass: HomeAssistant):
    """Test reauth aborts when a different account MSISDN is provided."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500111222",
        entry_id="reauth_wrong_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        # Returns a different primary MSISDN
        instance.async_get_context_msisdns = AsyncMock(return_value=["500999888"])

        with pytest.raises(Exception, match="wrong_account"):
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_JSESSIONID: "different_account_session"},
            )


@pytest.mark.asyncio
async def test_config_flow_reauth_multi_msisdn_success(
    hass: HomeAssistant, mock_setup_entry
):
    """Test reauth succeeds for multi-MSISDN account when unique_id matches non-first number."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500111222",
        entry_id="reauth_multi_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        # Returns numbers with the entry's unique_id in second position
        instance.async_get_context_msisdns = AsyncMock(
            return_value=["500999888", "500111222"]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "new_valid_session"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "play24_500111222"
        assert entries[0].data[CONF_JSESSIONID] == "new_valid_session"


@pytest.mark.asyncio
async def test_config_flow_reauth_sms_multi_msisdn_success(
    hass: HomeAssistant, mock_setup_entry, mock_play24_auth
):
    """Test reauth via SMS succeeds when unique_id matches non-first MSISDN."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500111222",
        entry_id="reauth_sms_multi_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"method": "sms"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "sms"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"msisdn": "500999888"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "otp"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock()
        instance.async_get_csrf = AsyncMock()
        instance.async_get_context_msisdns = AsyncMock(
            return_value=["500999888", "500111222"]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"otp": "1234"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "play24_500111222"
        assert entries[0].data[CONF_JSESSIONID] == "new_mock_jsessionid"


@pytest.mark.asyncio
async def test_config_flow_reconfigure_multi_msisdn_success(
    hass: HomeAssistant, mock_setup_entry
):
    """Test reconfigure succeeds for multi-MSISDN account when unique_id matches non-first number."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500111222",
        entry_id="reconfigure_multi_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        instance.async_get_context_msisdns = AsyncMock(
            return_value=["500999888", "500111222"]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "reconfigured_session"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "play24_500111222"
        assert entries[0].data[CONF_JSESSIONID] == "reconfigured_session"


@pytest.mark.asyncio
async def test_config_flow_reconfigure_sms_multi_msisdn_success(
    hass: HomeAssistant, mock_setup_entry, mock_play24_auth
):
    """Test reconfigure via SMS succeeds when unique_id matches non-first MSISDN."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500111222",
        entry_id="reconfig_sms_multi_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"method": "sms"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "sms"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"msisdn": "500999888"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "otp"

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock()
        instance.async_get_csrf = AsyncMock()
        instance.async_get_context_msisdns = AsyncMock(
            return_value=["500999888", "500111222"]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"otp": "1234"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "play24_500111222"
        assert entries[0].data[CONF_JSESSIONID] == "new_mock_jsessionid"


@pytest.mark.asyncio
async def test_config_flow_reconfigure_wrong_account_aborts(hass: HomeAssistant):
    """Test reconfigure aborts when a different account MSISDN is provided."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500111222",
        entry_id="reconfig_wrong_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        # Returns a different account's MSISDN
        instance.async_get_context_msisdns = AsyncMock(return_value=["500999888"])

        with pytest.raises(Exception, match="wrong_account"):
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_JSESSIONID: "different_account_session"},
            )


@pytest.mark.asyncio
async def test_config_flow_reauth_multi_msisdn_normalized_prefix(
    hass: HomeAssistant, mock_setup_entry
):
    """Test reauth succeeds when unique_id has country code prefix and matches multi-MSISDN."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_48500111222",
        entry_id="reauth_prefix_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        instance.async_get_context_msisdns = AsyncMock(
            return_value=["500999888", "500111222"]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "new_valid_session"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "play24_48500111222"


@pytest.mark.asyncio
async def test_config_flow_reconfigure_multi_msisdn_with_country_code(
    hass: HomeAssistant, mock_setup_entry
):
    """Test reconfigure succeeds when entry unique_id is in multi-msisdn set with country codes."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500111222",
        entry_id="reconfig_cc_123",
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_entry.entry_id,
        },
        data=mock_entry.data,
    )

    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(return_value=True)
        instance.async_get_csrf = AsyncMock(return_value="token")
        instance.async_get_context_msisdns = AsyncMock(
            return_value=["48500999888", "48500111222"]
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "new_valid_session"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "play24_500111222"


@pytest.mark.asyncio
async def test_get_account_msisdns_variations():
    """Test _async_get_account_msisdns cleans, formats, and deduplicates MSISDNs."""
    from custom_components.play24.config_flow import Play24ConfigFlow

    flow = Play24ConfigFlow()
    client = AsyncMock()

    # 1. Multiple formatted numbers with duplicates
    client.async_get_context_msisdns.return_value = [
        "+48 500 111 222",
        "500 222 333",
        "500111222",
    ]
    res = await flow._async_get_account_msisdns(client)
    assert res == ["500111222", "500222333"]

    # 2. Fallback to get_other_tile
    client.async_get_context_msisdns.return_value = []
    client.async_get_other_tile.return_value = {"msisdn": "+48 600 700 800"}
    res = await flow._async_get_account_msisdns(client)
    assert res == ["600700800"]

    # 3. Primary MSISDN helper
    primary = await flow._async_get_primary_msisdn(client)
    assert primary == "600700800"


@pytest.mark.asyncio
async def test_options_flow_init(hass: HomeAssistant):
    """Test options flow initialization and default form schema with scan_interval_hours."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        entry_id="test_entry_options",
    )
    entry.add_to_hass(hass)

    flow = Play24ConfigFlow.async_get_options_flow(entry)
    flow.hass = hass

    result = await flow.async_step_init(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert "data_schema" in result
    schema = result["data_schema"].schema
    assert any(str(k) == CONF_SCAN_INTERVAL_HOURS for k in schema)
    assert DEFAULT_SCAN_INTERVAL_HOURS == 6


@pytest.mark.asyncio
async def test_options_flow_save(hass: HomeAssistant):
    """Test options flow saving updated options using CONF_SCAN_INTERVAL_HOURS."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        options={},
        entry_id="test_entry_options",
    )
    entry.add_to_hass(hass)

    flow = Play24ConfigFlow.async_get_options_flow(entry)
    flow.hass = hass

    result = await flow.async_step_init(user_input={CONF_SCAN_INTERVAL_HOURS: 1})
    assert result["type"] == "create_entry"
    assert result["title"] == ""
    assert result["data"][CONF_SCAN_INTERVAL_HOURS] == 1
    assert result["data"][CONF_SCAN_INTERVAL] == 1


@pytest.mark.asyncio
async def test_options_flow_save_legacy_key(hass: HomeAssistant):
    """Test options flow saving updated options using legacy CONF_SCAN_INTERVAL."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        options={},
        entry_id="test_entry_options_legacy",
    )
    entry.add_to_hass(hass)

    flow = Play24ConfigFlow.async_get_options_flow(entry)
    flow.hass = hass

    result = await flow.async_step_init(user_input={CONF_SCAN_INTERVAL: 3})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_SCAN_INTERVAL] == 3
    assert result["data"][CONF_SCAN_INTERVAL_HOURS] == 3


@pytest.mark.asyncio
async def test_options_flow_preserves_existing_choice(hass: HomeAssistant):
    """Test options flow uses existing option as default."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        options={CONF_SCAN_INTERVAL_HOURS: 12},
        entry_id="test_entry_options",
    )
    entry.add_to_hass(hass)

    flow = Play24ConfigFlow.async_get_options_flow(entry)
    flow.hass = hass

    result = await flow.async_step_init(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "init"
    schema = result["data_schema"].schema
    key = next(k for k in schema if str(k) == CONF_SCAN_INTERVAL_HOURS)
    assert key.default() == 12


@pytest.mark.asyncio
async def test_options_flow_preserves_legacy_choice(hass: HomeAssistant):
    """Test options flow falls back to legacy CONF_SCAN_INTERVAL for default."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        options={CONF_SCAN_INTERVAL: 24},
        entry_id="test_entry_options",
    )
    entry.add_to_hass(hass)

    flow = Play24ConfigFlow.async_get_options_flow(entry)
    flow.hass = hass

    result = await flow.async_step_init(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "init"
    schema = result["data_schema"].schema
    key = next(k for k in schema if str(k) == CONF_SCAN_INTERVAL_HOURS)
    assert key.default() == 24


@pytest.mark.asyncio
async def test_options_flow_string_coercion(hass: HomeAssistant):
    """Test options flow coerces string intervals to int."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        entry_id="test_entry_options",
    )
    entry.add_to_hass(hass)

    flow = Play24OptionsFlowHandler(entry)
    flow.hass = hass

    result = await flow.async_step_init(user_input={CONF_SCAN_INTERVAL_HOURS: "3"})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_SCAN_INTERVAL_HOURS] == 3
    assert result["data"][CONF_SCAN_INTERVAL] == 3


@pytest.mark.asyncio
async def test_options_flow_add_options_flow_alias(hass: HomeAssistant):
    """Test add_options_flow method as alias to async_get_options_flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        entry_id="test_entry_options",
    )
    flow = Play24ConfigFlow.add_options_flow(entry)
    assert isinstance(flow, Play24OptionsFlowHandler)


@pytest.mark.asyncio
async def test_options_flow_handler_property_fallback(hass: HomeAssistant):
    """Test options flow handler config_entry resolution via hass handler entry_id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        entry_id="test_handler_entry_id",
    )
    entry.add_to_hass(hass)

    flow = Play24OptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id

    assert flow.config_entry == entry


@pytest.mark.asyncio
async def test_options_flow_handler_property_none():
    """Test options flow handler config_entry returns None when unattached."""
    flow = Play24OptionsFlowHandler()
    assert flow.config_entry is None


@pytest.mark.asyncio
async def test_options_flow_via_options_manager(hass: HomeAssistant):
    """Test options flow full lifecycle via hass.config_entries.options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        entry_id="test_entry_options",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL_HOURS: 24},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_SCAN_INTERVAL_HOURS] == 24


@pytest.mark.asyncio
async def test_options_flow_updates_coordinator_via_update_listener(
    hass: HomeAssistant,
):
    """Test options flow updates coordinator update_interval through update_listener."""
    from unittest.mock import MagicMock

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "dummy_session"},
        entry_id="test_entry_listener",
    )
    entry.add_to_hass(hass)
    entry.add_update_listener(update_listener)

    mock_coordinator = MagicMock()
    mock_coordinator.update_interval = timedelta(hours=6)
    hass.data[DOMAIN] = {entry.entry_id: mock_coordinator}

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL_HOURS: 12},
    )
    assert result["type"] == "create_entry"
    assert mock_coordinator.update_interval == timedelta(hours=12)
    assert entry.options[CONF_SCAN_INTERVAL_HOURS] == 12



