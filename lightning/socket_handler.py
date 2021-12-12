import asyncio
import websockets
import json
from websockets.server import WebSocketServerProtocol
import logging
from .config import Config
import os

# TODO: Move this to a top level code.
logging.basicConfig(format='%(filename)s:%(funcName)s:%(levelname)s:%(message)s')

LOGGER = logging.getLogger(__file__)
LOGGER.setLevel(Config.LoggingLevel)

JSONRPC_ERROR_CODE_PARSE_ERROR = -32700
JSONRPC_ERROR_CODE_INVALID_REQUEST = -32600
JSONRPC_ERROR_CODE_METHOD_NOT_FOUND = -32601
JSONRPC_ERROR_CODE_INVALID_PARAMS = -32602
JSONRPC_ERROR_CODE_INTERNAL_ERROR = -32603

class JsonRpcException(Exception):
    def __init__(self, error_message, code, message_to_client: str = ""):
        Exception.__init__(self, error_message)
        self.code = code
        # Surface to the client.
        self.message_to_client = message_to_client

class _WebsocketHandlerState():
    def __init__(self):
        '''
        State that persists for a websocket.
        '''
        self.echo_state = None

def _echo(state: _WebsocketHandlerState, msg: str):
    state.echo_state = "state is set"
    return msg

_registry = {}
_registry['echo'] = _echo

# Protocl request and response format is JSONRPC: https://www.jsonrpc.org/specification
async def websocket_handler(websocket: WebSocketServerProtocol):
    running = True
    state = _WebsocketHandlerState()
    while running:
        request_id = None
        try:
            request_str = await websocket.recv()
            LOGGER.debug("request_str: {}".format(request_str))

            # TODO: how to surface json parsing error
            try:
                jsonrpc_request = json.loads(request_str)
            except JSONDecodeError as e:
                raise JsonRpcException(str(e), JSONRPC_ERROR_CODE_PARSE_ERROR, 
                    "Failed to parse the json request")

            request_id = jsonrpc_request["id"] if jsonrpc_request["id"] else None
            params = jsonrpc_request["params"] if jsonrpc_request["params"] else []

            if "method" not in jsonrpc_request or jsonrpc_request["method"] not in _registry:
                raise JsonRpcException("method not found", JSONRPC_ERROR_CODE_METHOD_NOT_FOUND)

            if jsonrpc_request["jsonrpc"] is None or jsonrpc_request["jsonrpc"] != "2.0":
                raise JsonRpcException("Unsupported version", JSONRPC_ERROR_CODE_INVALID_REQUEST, 
                    "Only support JSONRPC 2.0")

            # TODO: how to surface the error that the params does not match with the method signature.
            if type(params) == dict:
                result = _registry[jsonrpc_request["method"]](state, **params)
            else:
                result = _registry[jsonrpc_request["method"]](state, *params)
            response = {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
            await websocket.send(json.dumps(response))    

        except JsonRpcException as e:
            LOGGER.debug("websocket_handler JsonRpcException: {}".format(str(e)))
            response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": e.code,
                    "message": e.message_to_client
                },
                "id": request_id
            }
            await websocket.send(json.dumps(response))
        except websockets.exceptions.ConnectionClosedOK as e:
            running = False
        except websockets.exceptions.ConnectionClosedError as e:
            LOGGER.debug("websocket_handler closing due to error: {}".format(str(e)))
        except Exception as e:
            LOGGER.debug("websocket_handler Exception: {}".format(str(e)))
            response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": JSONRPC_ERROR_CODE_INTERNAL_ERROR
                },
                "id": None
            }
            await websocket.send(json.dumps(response))


############ Testing  ############
async def _echo_client():
    socket_path = os.path.join(os.path.dirname(__file__), "socket")
    async with websockets.unix_connect(socket_path) as websocket:
        request = {
            "id": 1,
            "jsonrpc": "2.0",
            "params": ["hello from client"],
            "method": "echo"
        }
        await websocket.send(json.dumps(request))

        response = await websocket.recv()
        print(f"<<< {response}")


if __name__ == '__main__':
    # WS server example listening on a Unix socket
    import asyncio
    import os.path
    import websockets

    async def main():
        socket_path = os.path.join(os.path.dirname(__file__), "socket")
        async with websockets.unix_serve(websocket_handler, socket_path):
            await asyncio.Future()  # run forever

    asyncio.run(main())

    # # WS client example that correspond to the above.
    # asyncio.run(_echo_client())

