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
from queue import SimpleQueue, Empty
from collections import defaultdict
from .jsonrpc_handler import JsonRpcException, WebSocketSend, JsonRpcRequest, JsonRpcHandler, JsonRpcSession
from .jsonrpc_handler import JSONRPC_ERROR_CODE_PARSE_ERROR, JSONRPC_ERROR_CODE_INVALID_REQUEST, JSONRPC_ERROR_CODE_METHOD_NOT_FOUND, JSONRPC_ERROR_CODE_INVALID_PARAMS, JSONRPC_ERROR_CODE_INTERNAL_ERROR

# TODO: Move this to a top level code.
logging.basicConfig(format='%(filename)s:%(funcName)s:%(levelname)s:%(message)s')

LOGGER = logging.getLogger(__file__)
LOGGER.setLevel(Config.LoggingLevel)

class _FeedMetadata():
    def __init__(self):
        self.feed_id = 0
        self.feed_type = None
        # True when the remote signals "cancel" is closed and the feed is terminated.
        self.cancelled = False

class FeedHandler(JsonRpcHandler):
    FEED_FINALIZED_INVOICES = "finalized_invoices"

    FEED_MAX_NUMBER_OF_ITEMS = 100

    def __init__(self, websocket_send: WebSocketSend, jsonrpc_session: JsonRpcSession, max_feeds_allowed=1):
        self._websocket_send = websocket_send
        self._jsonrpc_session = jsonrpc_session
        self._max_feeds_allowed = max_feeds_allowed
        self._last_feed_id = 0
        self._feeds: typing.Dict[int, _FeedMetadata]= {}

    def _feed_type_exists(self, feed_type):
        for feed_metadata in self._feeds.values():
            if feed_metadata.feed_type == feed_type:
                return True
        return False
    
    def can_handle(self, request: JsonRpcRequest):
        return request.method in ["select_feed", "cancel_feed"]

    async def _start_feed(self, feed: _FeedMetadata):
        queue = SimpleQueue()
        subscriber_id = 0
        try:
            if feed.feed_type == FeedHandler.FEED_FINALIZED_INVOICES:
                def on_finalized_invoice(topic, invoice):
                    assert topic == "/invoice/finalized"
                    if invoice.account_id == self._jsonrpc_session.account_id:
                        queue.put({
                            "invoice_id": invoice.invoice_id,
                            "status": invoice.status
                        })
                subscriber_id = Pubsub.instance.subscribe("/invoice/finalized", on_finalized_invoice)
            else:
                raise JsonRpcException("Unknown feed_type: {}".format(feed.feed_type))

            # Given queue where we feed items will be put into, send them to the remote.
            while not feed.cancelled:
                self._jsonrpc_session.check_auth()
                items = []
                for _ in range(FeedHandler.FEED_MAX_NUMBER_OF_ITEMS):
                    try:
                        item = queue.get_nowait()
                    except Empty:
                        break
                    items.append(item)
                if items:
                    await self._websocket_send.send(json.dumps({
                        "jsonrpc": "2.0", 
                        "method": "feed", 
                        "params": {
                            "feed_id": feed.feed_id,
                            "feed": items
                        }
                    }))
                await asyncio.sleep(0)
            
        finally:
            if subscriber_id:
                Pubsub.instance.unsubscribe(subscriber_id)
            del self._feeds[feed.feed_id]

    async def _send_ok(self, request_id):
        await self._websocket_send.send(json.dumps({
            "jsonrpc": "2.0",
            "result": "ok",
            "id": request_id
        }))

    async def handle(self, request: JsonRpcRequest):
        '''
        Protocol: The format of the request and response are JSONRPC. 
        Pre-condition: The websocket has been authenticated indicated by self.jsonrpc_session
        Case: Start receiving a feed
            1) The remote sends a requets indicating the type of Feed that it want to receive, {"method": "select_feed", "params": {"feed_type": "finalized_invoices"}}
                2a) Handler responds with error {"error": "error message"}, possible errors: 1) not authenicated, 2) self.max_feeds_allowed is reached.
                2b) Handler responds with {"result": 1} where 1 is the feed ID
            2) Handler starts to send the feed indefinitely until the remote closes the socket, token expired, the local encounter an error, or the remote cancels it.
                The format of the feed is {"jsonrpc": "2.0", "method": "feed", "params": {"feed_id": 1,"feed": []}}
        Case: Cancel a feed
            1) The remote sends a requets indicating the type of Feed that it want to cancel, {"method": "cancel_feed", "params": {"feed_id": 1}}
                1) The remote respond {"result": "ok"}

        Note: the websocket handler must have more than self.max_feeds_allowed, otherwise when the self.max_feeds_allowed number
            of feeds are reach or before, socket hangs and no more requests can be processed. Maybe a FIXME?
        '''
        assert self.can_handle(request)
        self._jsonrpc_session.check_auth()
        
        if len(self._feeds) > self._max_feeds_allowed:
            raise JsonRpcException("Max number of feeds reached", JSONRPC_ERROR_CODE_INVALID_REQUEST, "You have reached the max number of feeds")

        if request.method == "select_feed":
            feed_type = request.params.get("feed_type", None)
            if self._feed_type_exists(feed_type):
                msg = "Feed type {} already exists".format(feed_type)
                raise JsonRpcException(msg, JSONRPC_ERROR_CODE_INVALID_REQUEST, msg)

            self._last_feed_id += 1
            feed_id = self._last_feed_id
            feed_metadata = _FeedMetadata()
            feed_metadata.feed_id = feed_id
            feed_metadata.feed_type = feed_type
            self._feeds[feed_id] = feed_metadata 
            await self._websocket_send.send(json.dumps({
                "jsonrpc": "2.0",
                "result": feed_id,
                "id": request.id
            }))
            await self._start_feed(feed_metadata)
        elif request.method == "cancel_feed":
            feed_id = request.params.get("feed_id", 0)
            if feed_id in self._feeds:
                self._feeds[feed_id].cancelled = True
                await self._send_ok(request.id)
            else:
                msg = "Feed ID {} is not found".format(feed_id)
                raise JsonRpcException(msg, JSONRPC_ERROR_CODE_INVALID_REQUEST, msg)
        else:
            msg = "JSONRPC method {} is unknown".format(request.method)
            raise JsonRpcException(msg, JSONRPC_ERROR_CODE_INVALID_REQUEST, msg)

