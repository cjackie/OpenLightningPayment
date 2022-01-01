import asyncio
import websockets
from lightning.jsonrpc_over_websocket import JsonRpc, WebSocketServerProtocolWrapper

_NUMBER_OF_HANDLERS = 10

async def _entry(websocket):
    jsonrpc = JsonRpc(WebSocketServerProtocolWrapper(websocket))
    handlers = [asyncio.create_task(jsonrpc.handle()) for _ in range(_NUMBER_OF_HANDLERS)]
    await asyncio.gather(*handlers)

async def _main():
    async with websockets.serve(_entry, "localhost", 8000):
        await asyncio.Future()  # run forever

if __name__ == '__main__':
    asyncio.run(_main())
