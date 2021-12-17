import asyncio
import websockets
import json
from websockets.server import WebSocketServerProtocol
import logging
from .config import Config
from .db import DBAccount, DBInvoice
import os
import lightning.market
from .pubsub import Pubsub
import time
from .auth import Auth, JwtTokenDecodeError, JwtTokenUtils
from threading import Lock
from asyncio import Task
import typing

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

class _JsonRpcHandler():
    '''
    The names of JSON RPC method in this class have the form "jsonrpc_{method_name}". "method_name"
    is the name that exposed to outside. For example def jsonrpc_echo(self), "echo" is the method callable
    by websocket_handler.

    Each websocket must have an unqiue instance of _JsonRpcHandler, since _JsonRpcHandler is stateful.
    '''
    def __init__(self):
        self.echo_state = None

        # Auth related
        self.account_id = None
        self.exp = 0

        # id -> DBInvoice
        self.pending_invoices = {}
        self.finalized_invoices = {}
        self.lock = Lock()

    def _get_account_id(self):
        if self.account_id is None:
            raise JsonRpcException("Not authenticated", JSONRPC_ERROR_CODE_INVALID_REQUEST, "Please authenticate first")
        if self.exp < int(time.time()):
            raise JsonRpcException("JWT Token has expired", JSONRPC_ERROR_CODE_INVALID_REQUEST, "JWT Token has expired")
        return self.account_id

    def _add_pending_invoice_to_state_callback(self):
        def on_topic(topic, pending_invoice):
            assert topic == "/invoice/pending"
            if self._get_account_id() == pending_invoice.account_id:
                self.lock.acquire()
                self.pending_invoices[pending_invoice.invoice_id] = pending_invoice
                self.lock.release()
        return on_topic

    async def _exchange_info(self):
        return market.exchange_info()

    async def _db_create_invoice(self, new_invoice: DBInvoice):
        return DBInvoice.create_invoice(new_invoice)

    async def jsonrpc_create_invoice(self, amount_requested: int):
        account_id = self._get_account_id()

        # Build the invoice
        new_invoice = DBInvoice()
        new_invoice.amount_requested = amount_requested
        try:
            exchange_info_task: asyncio.Task = asyncio.create_task(self._exchange_info())
            await exchange_info_task
            exchange_info = exchange_info_task.result()
        except Exception as e:
            raise JsonRpcException(str(e), JSONRPC_ERROR_CODE_INTERNAL_ERROR)

        new_invoice.exchange_rate = exchange_info["sat_per_usd"]
        new_invoice.created_at = int(time.time())
        new_invoice.account_id = account_id
        
        # Subcribe to pending invoice topic which would add the pending invoice to our state.
        subscriber_id = Pubsub.instance.subscribe("/invoice/pending", self._add_pending_invoice_to_state_callback())
        try:
            # Insert the invoice into DB.
            created_invoice_task: asyncio.Task = asyncio.create_task(self._db_create_invoice(new_invoice))
            await created_invoice_task
            created_invoice = created_invoice_task.result()

            # Keeping polling the pending invoice until found or timeout.
            start = time.time()
            while created_invoice.invoice_id not in self.pending_invoices:
                if time.time() - start > 60:
                    raise JsonRpcException("Waiting for the pending invoice timeout")
                await asyncio.sleep(0.5)
            
            # Found
            pending_invoice = self.pending_invoices[created_invoice.invoice_id]
            return {
                "invoice_id": pending_invoice.invoice_id,
                "encoded_invoice": pending_invoice.encoded_invoice,
                "amount_requested": pending_invoice.amount_requested,
                "exchange_rate": pending_invoice.exchange_rate,
                "expired_at": pending_invoice.expired_at
            }
        except JsonRpcException as e:
            raise e
        except Exception as e:
            raise JsonRpcException(str(e), JSONRPC_ERROR_CODE_INTERNAL_ERROR)
        finally:
            Pubsub.instance.unsubscribe(subscriber_id)
    
    async def jsonrpc_authenticate(self, jwt_token: str):
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
    async def jsonrpc_echo(self, msg: str):
        print("echo before asyncio.sleep")
        await asyncio.sleep(3)
        self.echo_state = "state is set"
        print("echo after asyncio.sleep")
        return msg


# Protocol request and response format is JSONRPC: https://www.jsonrpc.org/specification
async def websocket_handler(websocket: WebSocketServerProtocol):
    running = True
    jsonrpc_handler = _JsonRpcHandler()
    jsonrpc_methods = {}
    for maybe_jsonrpc_method_name in jsonrpc_handler.__dir__():
        maybe_method = jsonrpc_handler.__getattribute__(maybe_jsonrpc_method_name)
        if maybe_jsonrpc_method_name.startswith("jsonrpc_"):
            assert maybe_method and typing.types.MethodType == type(maybe_method)
            jsonrpc_methods[maybe_jsonrpc_method_name[len("jsonrpc_"):]] = maybe_method
        
    LOGGER.debug("There are {} number of methods: {}".format(len(jsonrpc_methods), ",".join(jsonrpc_methods.keys())))

    while running:
        request_id = None
        try:
            request_str = await websocket.recv()
            LOGGER.debug("request_str: {}".format(request_str))

            # TODO: how to surface json parsing error
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
async def _test_echo_client():
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
        # async with websockets.server.serve(websocket_handler, "localhost", 8001):
        #     await asyncio.Future()  # run forever

    asyncio.run(main())

    # # WS client example that correspond to the above.
    # asyncio.run(_echo_client())

