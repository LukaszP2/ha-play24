import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from custom_components.play24.const import DOMAIN, CONF_JSESSIONID
from custom_components.play24.api import Play24AuthError, Play24ConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

@pytest.fixture
def mock_setup_entry():
    with patch("custom_components.play24.async_setup_entry", return_value=True) as mock_setup:
        yield mock_setup

@pytest.fixture
def mock_play24_auth():
    with patch("custom_components.play24.config_flow.Play24Authenticator") as mock:
        instance = mock.return_value
        instance.async_request_sms = AsyncMock()
        instance.async_submit_otp = AsyncMock(return_value="new_mock_jsessionid")
        yield instance

@pytest.mark.asyncio
async def test_config_flow_direct_user_jsessionid_success(hass: HomeAssistant, mock_setup_entry):
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
        instance.async_test_connection = AsyncMock(side_effect=Play24AuthError("Session expired"))

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "bad_direct_session"},
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"

    # 2. Connection error
    with patch("custom_components.play24.config_flow.Play24Client") as mock_client:
        instance = mock_client.return_value
        instance.async_test_connection = AsyncMock(side_effect=Play24ConnectionError("Timeout"))

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_JSESSIONID: "unreachable_session"},
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"

@pytest.mark.asyncio
async def test_config_flow_legacy_method_selection(hass: HomeAssistant, mock_setup_entry):
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
async def test_config_flow_reauth_confirm_jsessionid(hass: HomeAssistant, mock_setup_entry):
    """Test reauth flow using clean reauth_confirm step."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "expired_session"},
        unique_id="play24_500123456",
        entry_id="reauth_entry_123"
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": mock_entry.entry_id},
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
        entry_id="reconfig_entry_123"
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
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
async def test_config_flow_first_setup_sms(hass: HomeAssistant, mock_setup_entry, mock_play24_auth):
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
async def test_config_flow_reauth_sms(hass: HomeAssistant, mock_setup_entry, mock_play24_auth):
    """Test reauth flow using SMS method."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "expired_session"},
        unique_id="play24_500123456",
        entry_id="reauth_sms_123"
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": mock_entry.entry_id},
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
async def test_config_flow_reconfigure_sms(hass: HomeAssistant, mock_setup_entry, mock_play24_auth):
    """Test reconfigure flow using SMS method."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Play24",
        data={CONF_JSESSIONID: "old_session"},
        unique_id="play24_500123456",
        entry_id="reconfig_sms_123"
    )
    mock_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": mock_entry.entry_id},
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
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"method": "sms"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"msisdn": "123456789"})
    assert result["step_id"] == "otp"

    # 1. Invalid OTP
    mock_play24_auth.async_submit_otp = AsyncMock(side_effect=Play24AuthError("Błędny kod SMS"))
    res = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": "0000"})
    assert res["type"] == "form"
    assert res["errors"]["base"] == "invalid_otp"

    # 2. Expired OTP
    mock_play24_auth.async_submit_otp = AsyncMock(side_effect=Play24AuthError("Kod SMS wygasł"))
    res = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": "1111"})
    assert res["type"] == "form"
    assert res["errors"]["base"] == "expired_otp"

    # 3. Limit exceeded
    mock_play24_auth.async_submit_otp = AsyncMock(side_effect=Play24AuthError("Limit prób przekroczony"))
    res = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": "2222"})
    assert res["type"] == "form"
    assert res["errors"]["base"] == "otp_limit_exceeded"


@pytest.mark.asyncio
async def test_config_flow_sms_phone_validation(hass: HomeAssistant, mock_play24_auth):
    """Test validation of phone number in SMS step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"method": "sms"})
    assert result["step_id"] == "sms"

    # Too short
    res = await hass.config_entries.flow.async_configure(result["flow_id"], {"msisdn": "12345"})
    assert res["type"] == "form"
    assert res["errors"]["base"] == "invalid_phone_number"

