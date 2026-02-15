import asyncio
from aiocoap import resource, Context
from aiocoap.numbers.codes import Code


class Hello(resource.Resource):
    async def render_get(self, request):
        return resource.Message(
            code=Code.CONTENT,
            payload=b"Hello IoT"
        )


# --- HIDDEN RESOURCES (only adaptive tests will discover these) ---

class SecretResource(resource.Resource):
    """Hidden resource with sensitive data — not in .well-known/core static checks."""
    async def render_get(self, request):
        return resource.Message(
            code=Code.CONTENT,
            payload=b'{"api_key": "secret123", "config": "exposed"}'
        )


class ConfigResource(resource.Resource):
    """Writable config — allows PUT and DELETE (misconfiguration)."""
    async def render_get(self, request):
        return resource.Message(
            code=Code.CONTENT,
            payload=b'{"firmware": "1.0.0", "update_url": "http://internal/update"}'
        )

    async def render_put(self, request):
        return resource.Message(
            code=Code.CHANGED,
            payload=b'Config updated'
        )

    async def render_delete(self, request):
        return resource.Message(
            code=Code.DELETED,
            payload=b'Config deleted'
        )


class FirmwareResource(resource.Resource):
    """Firmware info endpoint with debug build info."""
    async def render_get(self, request):
        return resource.Message(
            code=Code.CONTENT,
            payload=b'{"version": "1.0.0-beta", "build": "DEBUG"}'
        )


async def main():
    root = resource.Site()
    root.add_resource(('.well-known', 'core'), Hello())
    root.add_resource(('hello',), Hello())

    # Hidden resources (adaptive tests discover these)
    root.add_resource(('secret',), SecretResource())
    root.add_resource(('config',), ConfigResource())
    root.add_resource(('firmware',), FirmwareResource())

    # FORÇA IPv4 pelo bind
    await Context.create_server_context(
        root,
        bind=("0.0.0.0", 5683)
    )

    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
