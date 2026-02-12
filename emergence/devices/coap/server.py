import asyncio
from aiocoap import resource, Context
from aiocoap.numbers.codes import Code


class Hello(resource.Resource):
    async def render_get(self, request):
        return resource.Message(
            code=Code.CONTENT,
            payload=b"Hello IoT"
        )


async def main():
    root = resource.Site()
    root.add_resource(('.well-known', 'core'), Hello())
    root.add_resource(('hello',), Hello())

    # FORÇA IPv4 pelo bind
    await Context.create_server_context(
        root,
        bind=("0.0.0.0", 5683)
    )

    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
