"""Dump the ThunderAgent router's metrics endpoint as JSON (one line)."""
import asyncio, json, sys
from dynamo.runtime import DistributedRuntime, dynamo_worker


@dynamo_worker()
async def main(runtime: DistributedRuntime):
    ep = runtime.endpoint("dynamo.thunderagent_router.metrics")
    client = await ep.client()
    await asyncio.wait_for(client.wait_for_instances(), 30)
    stream = await client.round_robin({})
    async for item in stream:
        data = item.data() if hasattr(item, "data") else item
        print(json.dumps(data))
        break


asyncio.run(main())
