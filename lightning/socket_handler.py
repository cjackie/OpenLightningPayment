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

class Feed():
    FEED_FINALIZED_INVOICES = "finalized_invoices"

    def __init__(self):
        self.account_id = None
        self.exp = 0
        self.feed_type = None
        self.subscriber_id = 0
        self.finalized_invoices = []
        self.lock = Lock()

    def _on_finalized_invoice(self, topic, finalized_invoice: DBInvoice):
        assert topic == "/invoice/finalized"
        if self.account_id == finalized_invoice.account_id and self.exp > int(time.time()):
            self.lock.acquire()
            self.finalized_invoices.append(finalized_invoice)
            self.lock.release()
    
    def authenticate(self, jwt_token: str):
        '''
        This should be the frist RPC call to establish the identity with the websocket.
        This is option 1 in https://websockets.readthedocs.io/en/stable/topics/authentication.html#sending-credentials

        Client must call this method again before jwt_token expired, if the client want to maintain the socket.
        '''
        payload = JwtTokenUtils().verify_and_extract_payload(jwt_token)
        if payload.exp < int(time.time()):
            raise Exception("Token has expired: {}".format(exp), JSONRPC_ERROR_CODE_INVALID_REQUEST, "Token has expired")
        
        account = DBAccount.get_account_by_username(payload.sub)
        self.account_id = account.account_id
        self.exp = payload.exp

    def select(self, feed_type: str):
        if self.subscriber_id:
            Pubsub.instance.unsubscribe(self.subscriber_id)
            self.subscriber_id = None

        if feed_type == Feed.FEED_FINALIZED_INVOICES:
            self.subscriber_id = Pubsub.instance.subscribe("/invoice/finalized", self._on_finalized_invoice)
            self.feed_type = feed_type
            return True
        else:
            return False

    def close(self):
        if self.subscriber_id:
            Pubsub.instance.unsubscribe(self.subscriber_id)
            self.subscriber_id = None

    def get(self) -> typing.List:
        if self.feed_type == Feed.FEED_FINALIZED_INVOICES:
            self.lock.acquire()
            finalized_invoices = self.finalized_invoices
            self.finalized_invoices = []
            self.lock.release()

            result = []
            for finalized_invoice in finalized_invoices:
                result.append({
                    "invoice_id": finalized_invoice.invoice_id,
                    "status": finalized_invoice.status
                })
            return result
        else:
            raise Exception("Unrecoginzed feed type: {}".format(self.feed_type))

async def websocket_feed_handler(websocket: WebSocketServerProtocol):
    '''
    The feed for the client to assume. 
    
    Protocol: The format of the request and response are JSON. 
        1) Client sends the authentication request {"jwt_token": "token"}
            1a) Handler responds with error {"error": "error message"}
            1b) Handler responds with {"result": "ok"}
        2) Client sends a requets indicating the type of Feed that it want to receive, {"feed_type": "finalized_invoices"}
            2a) Handler responds with error {"error": "error message"}
            2b) Handler responds with {"result": "ok"}
        3) Handler starts to send the feed indefinitely until client close the socket, token expired, or server encounter an error.
    '''
    feed = Feed()
    try:
        req = await websocket.recv()
        auth_req = json.loads(req)
        _ = feed.authenticate(auth_req.get("jwt_token", ""))
        await websocket.send(json.dumps({"result": "ok"}))

        req = await websocket.recv()
        select_req = json.loads(req)
        feed.select(select_req["feed_type"])
        await websocket.send(json.dumps({"result": "ok"}))

        while not websocket.closed:
            result = feed.get()
            if result:
                await websocket.send(json.dumps(result))
            await asyncio.sleep(0.1)
    except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError) as e:
        LOGGER.debug("websocket_handler closing: {}".format(str(e)))
    except Exception as e:
        LOGGER.debug("websocket_feed_handler Exception: " +  str(e))
        error_response = {"error": "error"}
        await websocket.send(json.dumps(error_response))
    finally:
        feed.close()


############ Testing  ############
async def _test_feed():
    socket_path = os.path.join(os.path.dirname(__file__), "socket")
    async with websockets.unix_connect(socket_path) as websocket:
        await websocket.send(json.dumps({
            "jwt_token": "???"
        }))

        response = await websocket.recv()
        print(f"<<< {response}")
        response = json.loads(response)
        assert response["result"] == "ok"

        # =======
        await websocket.send(json.dumps({
            "feed_type": "finalized_invoices"
        }))
        response = await websocket.recv()
        print(f"<<< {response}")
        response = json.loads(response)
        assert response["result"] == "ok"

        finalized_invoice = DBInvoice()
        finalized_invoice.account_id = 12
        finalized_invoice.invoice_id = 19
        finalized_invoice.status = "paid" 
        Pubsub.instance.publish("/invoice/finalized", finalized_invoice)

        data = await websocket.recv()
        print(f"<<< {data}")

if __name__ == '__main__':
    # WS server example listening on a Unix socket
    import asyncio
    import os.path
    import websockets

    async def main():
        socket_path = os.path.join(os.path.dirname(__file__), "socket")
        async with websockets.unix_serve(websocket_feed_handler, socket_path):
            await asyncio.Future()  # run forever
        # async with websockets.server.serve(websocket_handler, "localhost", 8001):
        #     await asyncio.Future()  # run forever

    asyncio.run(main())

