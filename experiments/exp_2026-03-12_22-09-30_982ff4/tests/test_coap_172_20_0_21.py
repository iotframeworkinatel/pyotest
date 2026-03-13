"""Auto-generated CoAP vulnerability tests for 172.20.0.21"""
import pytest
import asyncio
from aiocoap import Context, Message, GET, PUT, DELETE

TIMEOUT = 5

@pytest.mark.vuln_id("COAP_CORE_DISCOVERY")
def test_coap_core_discovery():
    ip = "172.20.0.21"
    port = 5683

    async def _test():
        ctx = await Context.create_client_context()
        request = Message(code=GET, uri=f"coap://{ip}:{port}/.well-known/core")
        try:
            response = await asyncio.wait_for(ctx.request(request).response, timeout=TIMEOUT)
            if response.payload:
                assert True  # Resource discovery exposed
                return
        except Exception:
            pass
        pytest.fail("CoAP core discovery not accessible")

    asyncio.get_event_loop().run_until_complete(_test())


@pytest.mark.vuln_id("COAP_OPEN_RESOURCE")
def test_coap_open_resource():
    ip = "172.20.0.21"
    port = 5683

    async def _test():
        ctx = await Context.create_client_context()
        for path in ["/hello", "/sensor", "/data"]:
            request = Message(code=GET, uri=f"coap://{ip}:{port}{path}")
            try:
                response = await asyncio.wait_for(ctx.request(request).response, timeout=TIMEOUT)
                if response.payload:
                    assert True
                    return
            except Exception:
                continue
        pytest.fail("No open CoAP resources found")

    asyncio.get_event_loop().run_until_complete(_test())


@pytest.mark.vuln_id("COAP_HIDDEN_RESOURCE")
def test_coap_hidden_resource():
    ip = "172.20.0.21"
    port = 5683

    async def _test():
        ctx = await Context.create_client_context()
        for path in ["/secret", "/config", "/firmware", "/debug"]:
            request = Message(code=GET, uri=f"coap://{ip}:{port}{path}")
            try:
                response = await asyncio.wait_for(ctx.request(request).response, timeout=TIMEOUT)
                if response.payload:
                    assert True
                    return
            except Exception:
                continue
        pytest.fail("No hidden CoAP resources found")

    asyncio.get_event_loop().run_until_complete(_test())


@pytest.mark.vuln_id("COAP_GET")
def test_coap_get():
    ip = "172.20.0.21"
    port = 5683

    async def _test():
        ctx = await Context.create_client_context()
        for path in ["/temperature", "/sensor", "/data", "/hello", "/status"]:
            request = Message(code=GET, uri=f"coap://{ip}:{port}{path}")
            try:
                response = await asyncio.wait_for(ctx.request(request).response, timeout=TIMEOUT)
                if response.payload:
                    assert True
                    return
            except Exception:
                continue
        pytest.fail("No CoAP GET endpoints accessible")

    asyncio.get_event_loop().run_until_complete(_test())


@pytest.mark.vuln_id("COAP_PUT_ALLOWED")
def test_coap_put_allowed():
    ip = "172.20.0.21"
    port = 5683

    async def _test():
        ctx = await Context.create_client_context()
        request = Message(code=PUT, uri=f"coap://{ip}:{port}/config", payload=b"test")
        try:
            response = await asyncio.wait_for(ctx.request(request).response, timeout=TIMEOUT)
            if response.code.is_successful():
                assert True
                return
        except Exception:
            pass
        pytest.fail("CoAP PUT not allowed")

    asyncio.get_event_loop().run_until_complete(_test())


@pytest.mark.vuln_id("COAP_DELETE_ALLOWED")
def test_coap_delete_allowed():
    ip = "172.20.0.21"
    port = 5683

    async def _test():
        ctx = await Context.create_client_context()
        for path in ["/config", "/data", "/sensor"]:
            request = Message(code=DELETE, uri=f"coap://{ip}:{port}{path}")
            try:
                response = await asyncio.wait_for(ctx.request(request).response, timeout=TIMEOUT)
                if response.code.is_successful():
                    assert True
                    return
            except Exception:
                continue
        pytest.fail("CoAP DELETE not allowed")

    asyncio.get_event_loop().run_until_complete(_test())