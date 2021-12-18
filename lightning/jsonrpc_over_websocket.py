import asyncio
from .config import Config
import websockets
import json
from websockets.server import WebSocketServerProtocol
import logging
import os
import typing
from .auth import JwtTokenDecodeError, JwtTokenUtils, JwtTokenPayload
import time
from .db import DBAccount

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

class WebSocketServerProtocolWrapper:
    def __init__(self, websocket: WebSocketServerProtocol):
        self.websocket = websocket
        self.messages = websocket.messages

    async def send(self, data:str):
        return await self.websocket.send(data)
    
    async def recv(self):
        return await self.websocket.recv()
    
    async def close():
        return await self.websocket.close()

class JsonRpc():
    '''
    The names of JSON RPC method in this class have the form "_jsonrpc_{method_name}". "method_name"
    is the name that exposed to outside. For example def _jsonrpc_echo(self), "echo" is the method callable
    by websocket_handler.
    Each websocket must have an unqiue instance of JsonRpc, since JsonRpc is stateful.

    How to use it:
        jsonrpc = JsonRpc(WebSocketServerProtocolWrapper(websocket))
        handlers = [asyncio.create_task(jsonrpc.handle()) for _ in range(3)]
        await asyncio.gather([handlers])
    where 3 is the number of handlers for the websocket i.e the max "concurrent" request processing for the websoecket.
    '''
    def __init__(self, websocket: WebSocketServerProtocolWrapper):
        self.echo_state = None
        self.running = True
        self.websocket = websocket

        # Auth related
        self.account_id = None
        self.exp = 0

    async def _jsonrpc_authenticate(self, jwt_token: str):
        '''
        This should be the frist RPC call to establish the identity with the websocket.
        This is option 1 in https://websockets.readthedocs.io/en/stable/topics/authentication.html#sending-credentials
        '''
        try:
            payload = JwtTokenUtils().verify_and_extract_payload(jwt_token)
            if payload.exp < int(time.time()):
                raise JsonRpcException("Token has expired: {}".format(exp), JSONRPC_ERROR_CODE_INVALID_REQUEST, "Token has expired")

            account = DBAccount.get_account_by_username(payload.sub)
        except JwtTokenDecodeError as decode_error:
            raise JsonRpcException("JwtTokenDecodeError: " + decode_error.error_message, JSONRPC_ERROR_CODE_INVALID_REQUEST, "Invalid JWT Token")
        except JsonRpcException as jsonrpc_error:
            raise jsonrpc_error
        except Exception as e:
            raise JsonRpcException(str(e), JSONRPC_ERROR_CODE_INTERNAL_ERROR)
        
        self.account_id = account.account_id
        self.exp = payload.exp
        return "ok"

    '''
    Knowledge on `await` (ref https://www.python.org/dev/peps/pep-0492/#await-expression):
    The following new await expression is used to obtain a result of coroutine execution:
    ```
    async def read_data(db):
        data = await db.fetch('SELECT ...')
        ...
    ```
    await, similarly to yield from, suspends execution of read_data coroutine until db.fetch awaitable completes and returns the result data.
    When the execution of read_data is suspended, event loop switches to other coroutines to execute.
    '''
    async def _jsonrpc_echo(self, msg: str):
        print("echo before asyncio.sleep")
        await asyncio.sleep(0)
        self.echo_state = "state is set"
        print("echo after asyncio.sleep")
        return msg

    def stop(self):
        self.running = False

    async def handle(self):
        jsonrpc_methods = {}
        for maybe_jsonrpc_method_name in self.__dir__():
            maybe_method = self.__getattribute__(maybe_jsonrpc_method_name)
            if maybe_jsonrpc_method_name.startswith("_jsonrpc_"):
                assert maybe_method and typing.types.MethodType == type(maybe_method)
                jsonrpc_methods[maybe_jsonrpc_method_name[len("_jsonrpc_"):]] = maybe_method
            
        LOGGER.debug("There are {} number of methods: {}".format(len(jsonrpc_methods), ",".join(jsonrpc_methods.keys())))

        while self.running:
            request_id = None
            try:
                request_str = None
                while self.running and not request_str:
                    if self.websocket.messages:
                        request_str = await self.websocket.recv()
                    await asyncio.sleep(0)
                LOGGER.debug("request_str: {}".format(request_str))

                try:
                    jsonrpc_request = json.loads(request_str)
                except json.JSONDecodeError as e:
                    raise JsonRpcException(str(e), JSONRPC_ERROR_CODE_PARSE_ERROR, 
                        "Failed to parse the json request")

                request_id = jsonrpc_request["id"] if jsonrpc_request["id"] else None
                params = jsonrpc_request["params"] if jsonrpc_request["params"] else []

                if "method" not in jsonrpc_request or jsonrpc_request["method"] not in jsonrpc_methods:
                    raise JsonRpcException("method not found", JSONRPC_ERROR_CODE_METHOD_NOT_FOUND)

                if jsonrpc_request["jsonrpc"] is None or jsonrpc_request["jsonrpc"] != "2.0":
                    raise JsonRpcException("Unsupported version", JSONRPC_ERROR_CODE_INVALID_REQUEST, 
                        "Only support JSONRPC 2.0")

                # TODO: how to surface the error that the params does not match with the method signature.
                if type(params) == dict:
                    result = await jsonrpc_methods[jsonrpc_request["method"]](**params)
                else:
                    result = await jsonrpc_methods[jsonrpc_request["method"]](*params)
                response = {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": request_id
                }
                await self.websocket.send(json.dumps(response))    

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
                await self.websocket.send(json.dumps(response))
            except websockets.exceptions.ConnectionClosedOK as e:
                self.running = False
            except websockets.exceptions.ConnectionClosedError as e:
                self.running = False
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
                await self.websocket.send(json.dumps(response))

async def websocket_handler(websocket: WebSocketServerProtocol):
    jsonrpc = JsonRpc(WebSocketServerProtocolWrapper(websocket))
    handlers = [asyncio.create_task(jsonrpc.handle()) for _ in range(3)]
    await asyncio.gather(*handlers)

############ Testing  ############
async def _test_echo_client():
    socket_path = os.path.join(os.path.dirname(__file__), "socket")
    async with websockets.unix_connect(socket_path) as websocket:
        request1 = {
            "id": 1,
            "jsonrpc": "2.0",
            "params": ["hello from client"],
            "method": "echo"
        }
        request2 = {
            "id": 2,
            "jsonrpc": "2.0",
            "params": ["hello from client request 2"],
            "method": "echo"
        }
        asyncio.gather(websocket.send(json.dumps(request1)), websocket.send(json.dumps(request2)))
        response = await websocket.recv()
        print(f"<<< {response}")
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
        # async with websockets.server.serve(websocket_handler, "localhost", 8001):
        #     await asyncio.Future()  # run forever

    asyncio.run(main())

    # # WS client example that correspond to the above.
    # asyncio.run(_echo_client())