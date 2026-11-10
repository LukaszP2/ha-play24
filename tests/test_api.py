from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.play24.api import (
    Play24AuthError,
    Play24Client,
    Play24ConnectionError,
    Play24DataError,
    _parse_retry_after,
)


@pytest.fixture
def mock_session():
    return AsyncMock(spec=aiohttp.ClientSession)


@pytest.fixture
def client(mock_session):
    return Play24Client("mock_jsessionid", mock_session)


@pytest.mark.asyncio
async def test_api_csrf(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = "P24_CSRFTOKEN: mock_token"
    mock_session.post.return_value.__aenter__.return_value = mock_resp

    token = await client.async_get_csrf()
    assert token == "mock_token"


@pytest.mark.asyncio
async def test_api_dwr_auth_error(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = "java.lang.SecurityException: CSRF Security Error"
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    with pytest.raises(Play24AuthError):
        await client._async_dwr_request("script", "method")


@pytest.mark.asyncio
async def test_messages(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = 'view:"Masz <span>5</span> nieprzeczytane",'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_messages()
    assert data["unread_messages"] == 5


@pytest.mark.asyncio
async def test_get_context_msisdns(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = (
        'dwr.engine._remoteHandleCallback("0","0",["111111111", "222222222"]);'
    )
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["111111111", "222222222"]


@pytest.mark.asyncio
async def test_get_components_list(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = (
        'view:"<h3>Darmowe minuty do PLAY</h3>\n<h3>Poczta glosowa</h3>",'
    )
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_components_list("PLAY24_ACTIVE_COMPONENTS_SECTION")
    assert "Darmowe minuty do PLAY" in data
    assert "Poczta glosowa" in data


@pytest.mark.asyncio
async def test_get_context_msisdns_har_response(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine._remoteHandleCallback("0","0",{view:"<li data-id=\\"111111111\\"></li><li data-id=\\"222222222\\"></li>"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["111111111", "222222222"]


@pytest.mark.asyncio
async def test_get_context_msisdns_html_spaced(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine._remoteHandleCallback("0","0",{view:"<div class=\\"num\\"> 123 456 789 </div>"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["123456789"]


@pytest.mark.asyncio
async def test_get_context_msisdns_duplicates(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine._remoteHandleCallback("0","0",{view:"<div data-msisdn=\\"333333333\\">...</div><div data-msisdn=\\"333333333\\">...</div><div data-msisdn=\\"444444444\\">...</div>"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["333333333", "444444444"]


@pytest.mark.asyncio
async def test_get_context_msisdns_ignore_non_msisdn(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    # Response includes batchId, some JS variable that is 9 digits, but HTML only has the actual MSISDN
    mock_resp.text.return_value = '//#DWR-INSERT\nvar someId="999999999";\ndwr.engine._remoteHandleCallback("0","0",{view:"<div data-id=\\"555555555\\"></div>",batchId:"123456789"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["555555555"]


@pytest.mark.asyncio
async def test_get_context_msisdns_live_play24_structure(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine.remote.handleCallback("0","0",{view:"<li><a class=\\"selected\\"><input class=\\"msisdn\\" type=\\"hidden\\" value=\\"500123456\\"/><span>48 500 123 456</span></a></li>"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["500123456"]


@pytest.mark.asyncio
async def test_get_context_msisdns_multi_li_varying_attributes(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    # Multiple <li> elements, differing attribute ordering, onclick callback with comma, escaped quotes
    mock_resp.text.return_value = (
        "//#DWR-INSERT\n"
        'dwr.engine.remote.handleCallback("0","0",{'
        'view:"<ul class=\\"msisdnsList\\">'
        '<li><a class=\\"selected\\"><input class=\\"msisdn\\" type=\\"hidden\\" value=\\"500123456\\"/><span>48 500 123 456</span></a></li>'
        '<li><a class=\\"item\\"><input type=\\"hidden\\" value=\\"501234567\\" class=\\"msisdn\\"/><span>48 501 234 567</span></a></li>'
        "<li><a href=\\\"#\\\" onclick=\\\"changeAccountContext('502345678', 'ADMIN_CONTEXT')\\\"><span>502 345 678</span></a></li>"
        '<li><div data-msisdn=\\"48503456789\\"><span>Kolejny numer</span></div></li>'
        '</ul>"'
        "});"
    )
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["500123456", "501234567", "502345678", "503456789"]


@pytest.mark.asyncio
async def test_get_context_msisdns_escaped_html_and_commas(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    # Commas inside attributes, &quot; entities, and trailing quotes
    mock_resp.text.return_value = (
        "//#DWR-INSERT\n"
        'dwr.engine.remote.handleCallback("0","0",{'
        'view:"<li><input class=&quot;msisdn&quot; value=&quot;504111222&quot; title=&quot;Firma, biuro&quot;/></li>'
        '<li><input class=\\"msisdn\\" value=\\"505222333\\" data-extra=\\"a,b,c\\"/></li>"'
        "});"
    )
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_context_msisdns()
    assert data == ["504111222", "505222333"]


@pytest.mark.asyncio
async def test_get_components_list_dwr_js_objects(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    # Typical DWR response for list of services with JS property assignments and exclusions
    mock_resp.text.return_value = (
        "//#DWR-INSERT\n"
        "var s0=[];\n"
        "var s1={};\n"
        's1.name="Darmowe minuty do Play";\n'
        's1.code="FREE_MIN";\n'
        's1.status="ACTIVE";\n'
        "var s2={};\n"
        's2.componentName="Pakiet 10 GB";\n'
        's2.status="ACTIVE";\n'
        "var s3={};\n"
        's3.title="Poczta głosowa standard";\n'
        'dwr.engine.remote.handleCallback("0","0",dwr.engine.remote.newObject("BaseDwrTransferData",{responseStatus:dwr.engine.remote.newObject("ServiceDwrResponse",{code:"0",message:null})}));'
    )
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"

    data = await client.async_get_components_list("PLAY24_ACTIVE_COMPONENTS_SECTION")
    assert "Darmowe minuty do Play" in data
    assert "Pakiet 10 GB" in data
    assert "Poczta głosowa standard" in data
    # Excluded keywords must not appear
    assert "BaseDwrTransferData" not in data
    assert "ServiceDwrResponse" not in data


def test_parse_dwr_html_preserves_polish_unicode():
    client = Play24Client("synthetic-session", MagicMock())
    parsed = client._parse_dwr_html(r'var s0={view:"<div>Łódź i Pocz\u0105tek</div>"};')
    assert "Łódź" in parsed
    assert "Początek" in parsed


def test_parse_currency_amount():
    from custom_components.play24.api import _parse_currency_amount

    assert _parse_currency_amount("245,28 zł") == 245.28
    assert _parse_currency_amount("1 250,50 zł") == 1250.50
    assert _parse_currency_amount("1\u00a0000,00 PLN") == 1000.00
    assert _parse_currency_amount("0,00 zł") == 0.0
    assert _parse_currency_amount("") is None
    assert _parse_currency_amount(None) is None


def test_dwrsess_deterministic(mock_session):
    client1 = Play24Client("my_test_session_123", mock_session)
    client2 = Play24Client("my_test_session_123", mock_session)
    assert client1.dwrsessionid == client2.dwrsessionid
    assert client1._script_session_id.startswith(f"{client1.dwrsessionid}/")
    assert client1._cookies["DWRSESSIONID"] == client1.dwrsessionid


def test_dwrsess_explicit(mock_session):
    client = Play24Client("sess_123", mock_session, dwrsessionid="explicit_dwr_token")
    assert client.jsessionid == "sess_123"
    assert client.dwrsessionid == "explicit_dwr_token"
    assert client._cookies["DWRSESSIONID"] == "explicit_dwr_token"


def test_dwrsess_extracted_from_cookie_header(mock_session):
    raw_cookies = "JSESSIONID=sess_abc123.SelfCare01; DWRSESSIONID=dwr_xyz789; other=1"
    client = Play24Client(raw_cookies, mock_session)
    assert client.jsessionid == "sess_abc123.SelfCare01"
    assert client.dwrsessionid == "dwr_xyz789"
    assert client._cookies["JSESSIONID"] == "sess_abc123.SelfCare01"
    assert client._cookies["DWRSESSIONID"] == "dwr_xyz789"


def _make_mock_cm(status: int, text: str = "", headers: dict | None = None):
    resp = AsyncMock()
    resp.status = status
    resp.text.return_value = text
    resp.headers = headers or {}
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_api_dwr_rate_limit_retry_after(client, mock_session):
    """Test handling of HTTP 429 response with Retry-After: 2 header."""
    cm_429 = _make_mock_cm(429, headers={"Retry-After": "2"})
    cm_200 = _make_mock_cm(200, text='view:"Success"')
    mock_session.post.side_effect = [cm_429, cm_200]
    client._csrf_token = "mock_token"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        res = await client._async_dwr_request("script", "method")

    assert res == 'view:"Success"'
    assert mock_session.post.call_count == 2
    mock_sleep.assert_awaited_once_with(2.0)


@pytest.mark.asyncio
async def test_api_dwr_rate_limit_exponential_backoff(client, mock_session):
    """Test fallback to exponential backoff when Retry-After is absent."""
    cm_429 = _make_mock_cm(429, headers={})
    cm_200 = _make_mock_cm(200, text='view:"Success"')
    mock_session.post.side_effect = [cm_429, cm_200]
    client._csrf_token = "mock_token"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        res = await client._async_dwr_request("script", "method", backoff_base=1.5)

    assert res == 'view:"Success"'
    assert mock_session.post.call_count == 2
    mock_sleep.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_api_dwr_rate_limit_max_retries_exceeded(client, mock_session):
    """Test that exhausting retries raises Play24DataError."""
    cm_429_1 = _make_mock_cm(429, headers={"Retry-After": "1"})
    cm_429_2 = _make_mock_cm(429, headers={"Retry-After": "1"})
    cm_429_3 = _make_mock_cm(429, headers={"Retry-After": "1"})
    mock_session.post.side_effect = [cm_429_1, cm_429_2, cm_429_3]
    client._csrf_token = "mock_token"

    with (
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        pytest.raises(Play24DataError, match="HTTP 429"),
    ):
        await client._async_dwr_request("script", "method", max_retries=3)

    assert mock_session.post.call_count == 3
    assert mock_sleep.await_count == 2


def test_parse_retry_after_unit():
    assert _parse_retry_after({"Retry-After": "2"}) == 2.0
    assert _parse_retry_after({"retry-after": "5"}) == 5.0
    assert _parse_retry_after({"Retry-After": 10}) == 10.0
    assert _parse_retry_after({"Retry-After": "invalid"}) is None
    assert _parse_retry_after(None) is None
    assert _parse_retry_after({}) is None


def test_parse_retry_after_http_date():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    future_dt = datetime.now(UTC) + timedelta(seconds=20)
    date_str = format_datetime(future_dt)

    val = _parse_retry_after({"Retry-After": date_str})
    assert val is not None
    assert 18.0 <= val <= 22.0

    past_dt = datetime.now(UTC) - timedelta(seconds=20)
    past_date_str = format_datetime(past_dt)
    assert _parse_retry_after({"Retry-After": past_date_str}) == 0.0


def test_parse_retry_after_extended_formats():
    assert _parse_retry_after({"RETRY-AFTER": "7"}) == 7.0
    assert _parse_retry_after({"Retry-after": "8.5"}) == 8.5
    assert _parse_retry_after({"Retry-After": "12; comment=test"}) == 12.0
    assert _parse_retry_after({"Retry-After": "-5"}) == 0.0


@pytest.mark.asyncio
async def test_api_dwr_rate_limit_capped_at_max(client, mock_session):
    """Test that retry delay does not exceed backoff_max."""
    cm_429 = _make_mock_cm(429, headers={"Retry-After": "100"})
    cm_200 = _make_mock_cm(200, text='view:"Success"')
    mock_session.post.side_effect = [cm_429, cm_200]
    client._csrf_token = "mock_token"

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        res = await client._async_dwr_request("script", "method", backoff_max=10.0)

    assert res == 'view:"Success"'
    mock_sleep.assert_awaited_once_with(10.0)


@pytest.mark.asyncio
async def test_api_get_csrf_rate_limit_retry(client, mock_session):
    """Test async_get_csrf handles HTTP 429 with Retry-After and succeeds."""
    cm_429 = _make_mock_cm(429, headers={"Retry-After": "3"})
    cm_200 = _make_mock_cm(200, text="P24_CSRFTOKEN: delayed_token")
    mock_session.post.side_effect = [cm_429, cm_200]

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        token = await client.async_get_csrf()

    assert token == "delayed_token"
    assert mock_session.post.call_count == 2
    mock_sleep.assert_awaited_once_with(3.0)


@pytest.mark.asyncio
async def test_api_get_csrf_rate_limit_max_retries_exceeded(client, mock_session):
    """Test async_get_csrf raises Play24DataError after exhausting 429 retries."""
    cm_429 = _make_mock_cm(429, headers={})
    mock_session.post.side_effect = [cm_429, cm_429, cm_429]

    with (
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        pytest.raises(Play24DataError, match="HTTP 429"),
    ):
        await client.async_get_csrf(max_retries=3)

    assert mock_session.post.call_count == 3
    assert mock_sleep.await_count == 2


@pytest.mark.asyncio
async def test_api_test_connection_rate_limit_retry(client, mock_session):
    """Test async_test_connection handles HTTP 429 and retries successfully."""
    cm_429 = _make_mock_cm(429, headers={"Retry-After": "1.5"})
    cm_200 = _make_mock_cm(200, text="OK")
    mock_session.get.side_effect = [cm_429, cm_200]

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        res = await client.async_test_connection()

    assert res is True
    assert mock_session.get.call_count == 2
    mock_sleep.assert_awaited_once_with(1.5)


@pytest.mark.asyncio
async def test_api_test_connection_rate_limit_max_retries_exceeded(
    client, mock_session
):
    """Test async_test_connection raises Play24ConnectionError after exhausting 429 retries."""
    cm_429 = _make_mock_cm(429, headers={})
    mock_session.get.side_effect = [cm_429, cm_429, cm_429]

    with (
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        pytest.raises(Play24ConnectionError, match="HTTP 429"),
    ):
        await client.async_test_connection(max_retries=3)

    assert mock_session.get.call_count == 3
    assert mock_sleep.await_count == 2

