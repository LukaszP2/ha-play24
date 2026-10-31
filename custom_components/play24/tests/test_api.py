import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import aiohttp
from custom_components.play24.api import Play24Client, Play24AuthError, Play24ConnectionError, Play24DataError

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
    mock_resp.text.return_value = 'dwr.engine._remoteHandleCallback("0","0",["111111111", "222222222"]);'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"
    
    data = await client.async_get_context_msisdns()
    assert data == ["111111111", "222222222"]

@pytest.mark.asyncio
async def test_get_components_list(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = 'view:"<h3>Darmowe minuty do PLAY</h3>\n<h3>Poczta glosowa</h3>",'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"
    
    data = await client.async_get_components_list("PLAY24_ACTIVE_COMPONENTS_SECTION")
    assert "Darmowe minuty do PLAY" in data
    assert "Poczta glosowa" in data

@pytest.mark.asyncio
async def test_get_context_msisdns_har_response(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine._remoteHandleCallback("0","0",{view:"<li data-id=\\\"111111111\\\"></li><li data-id=\\\"222222222\\\"></li>"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"
    
    data = await client.async_get_context_msisdns()
    assert data == ["111111111", "222222222"]

@pytest.mark.asyncio
async def test_get_context_msisdns_html_spaced(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine._remoteHandleCallback("0","0",{view:"<div class=\\\"num\\\"> 123 456 789 </div>"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"
    
    data = await client.async_get_context_msisdns()
    assert data == ["123456789"]

@pytest.mark.asyncio
async def test_get_context_msisdns_duplicates(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine._remoteHandleCallback("0","0",{view:"<div data-msisdn=\\\"333333333\\\">...</div><div data-msisdn=\\\"333333333\\\">...</div><div data-msisdn=\\\"444444444\\\">...</div>"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"
    
    data = await client.async_get_context_msisdns()
    assert data == ["333333333", "444444444"]

@pytest.mark.asyncio
async def test_get_context_msisdns_ignore_non_msisdn(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    # Response includes batchId, some JS variable that is 9 digits, but HTML only has the actual MSISDN
    mock_resp.text.return_value = '//#DWR-INSERT\nvar someId="999999999";\ndwr.engine._remoteHandleCallback("0","0",{view:"<div data-id=\\\"555555555\\\"></div>",batchId:"123456789"});'
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    client._csrf_token = "mock"
    
    data = await client.async_get_context_msisdns()
    assert data == ["555555555"]

@pytest.mark.asyncio
async def test_get_context_msisdns_live_play24_structure(client, mock_session):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = '//#DWR-INSERT\ndwr.engine.remote.handleCallback("0","0",{view:"<li><a class=\\\"selected\\\"><input class=\\\"msisdn\\\" type=\\\"hidden\\\" value=\\\"500123456\\\"/><span>48 500 123 456</span></a></li>"});'
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
        '//#DWR-INSERT\n'
        'dwr.engine.remote.handleCallback("0","0",{'
        'view:"<ul class=\\\"msisdnsList\\\">'
        '<li><a class=\\\"selected\\\"><input class=\\\"msisdn\\\" type=\\\"hidden\\\" value=\\\"500123456\\\"/><span>48 500 123 456</span></a></li>'
        '<li><a class=\\\"item\\\"><input type=\\\"hidden\\\" value=\\\"501234567\\\" class=\\\"msisdn\\\"/><span>48 501 234 567</span></a></li>'
        '<li><a href=\\\"#\\\" onclick=\\\"changeAccountContext(\'502345678\', \'ADMIN_CONTEXT\')\\\"><span>502 345 678</span></a></li>'
        '<li><div data-msisdn=\\\"48503456789\\\"><span>Kolejny numer</span></div></li>'
        '</ul>"'
        '});'
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
        '//#DWR-INSERT\n'
        'dwr.engine.remote.handleCallback("0","0",{'
        'view:"<li><input class=&quot;msisdn&quot; value=&quot;504111222&quot; title=&quot;Firma, biuro&quot;/></li>'
        '<li><input class=\\\"msisdn\\\" value=\\\"505222333\\\" data-extra=\\\"a,b,c\\\"/></li>"'
        '});'
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
        '//#DWR-INSERT\n'
        'var s0=[];\n'
        'var s1={};\n'
        's1.name="Darmowe minuty do Play";\n'
        's1.code="FREE_MIN";\n'
        's1.status="ACTIVE";\n'
        'var s2={};\n'
        's2.componentName="Pakiet 10 GB";\n'
        's2.status="ACTIVE";\n'
        'var s3={};\n'
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
