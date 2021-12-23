from copy import copy
import asyncio
from .pubsub import Pubsub
import random
import unittest
from .db import DBInvoice, DBAccount, DBUtils
import time
from .auth import JwtTokenUtils, JwtTokenPayload
from .feed_handler import FeedHandler, _FeedMetadata
from .jsonrpc_handler import JsonRpcRequest, WebSocketSend, JsonRpcSession
import json

class FeedTest(unittest.TestCase):

    def test_selectFeed(self):
        this = self
        class FeedHandlerWithMocks(FeedHandler):
            def __init__(self, websocket_send, jsonrpc_session):
                FeedHandler.__init__(self, websocket_send, jsonrpc_session)
            async def _start_feed(self, feed):
                return 

        class MockWebSocketSend(WebSocketSend):
            async def send(self, data: str):
                resp = json.loads(data)
                this.assertEqual(resp.get("result", ""), 1)
                this.assertEqual(resp.get("id", 0), 2)
        
        session = JsonRpcSession()
        session.account_id = 1
        session.exp = int(time.time()) + 60*60*24

        feed_handler = FeedHandlerWithMocks(MockWebSocketSend(), session)
        request = JsonRpcRequest("2.0", "select_feed", {"feed_type": FeedHandler.FEED_FINALIZED_INVOICES}, 2)
        _ = asyncio.run(feed_handler.handle(request))

    def test_cancel(self):
        this = self
        class MockWebSocketSend(WebSocketSend):
            async def send(self, data: str):
                resp = json.loads(data)
                this.assertEqual(resp.get("result", ""), "ok")
                this.assertEqual(resp.get("id", 0), 3)

        session = JsonRpcSession()
        session.account_id = 1
        session.exp = int(time.time()) + 60*60*24

        feed_handler = FeedHandler(MockWebSocketSend(), session)
        # Mock internal feeds
        feed_handler._feeds[2] = _FeedMetadata()
        request = JsonRpcRequest("2.0", "cancel_feed", {"feed_id": 2}, 3)
        _ = asyncio.run(feed_handler.handle(request))

    def test_startFeed(self):
        this = self
        class MockPubsub(Pubsub):
            def subscribe(self, topic: str, callback):
                this.assertEqual(topic, "/invoice/finalized")
                finalized_invoice = DBInvoice()
                finalized_invoice.account_id = 5
                finalized_invoice.invoice_id = 7
                finalized_invoice.status = "paid"
                callback(topic, finalized_invoice)
                return 19

            def unsubscribe(self, callback_id):
                this.assertEqual(callback_id, 19)

        Pubsub.instance = MockPubsub()

        feed_metadata = _FeedMetadata()
        feed_metadata.feed_id = 23
        feed_metadata.feed_type = FeedHandler.FEED_FINALIZED_INVOICES
        class MockWebSocketSend(WebSocketSend):
            async def send(self, data: str):
                resp = json.loads(data)
                this.assertEqual(resp["jsonrpc"], "2.0")
                this.assertEqual(resp["method"], "feed")
                this.assertEqual(resp["params"]["feed_id"], 23)
                this.assertEqual(len(resp["params"]["feed"]), 1)
                this.assertEqual(resp["params"]["feed"][0]["status"], "paid")
                this.assertEqual(resp["params"]["feed"][0]["invoice_id"], 7)

                feed_metadata.cancelled = True

        session = JsonRpcSession()
        session.account_id = 5
        session.exp = int(time.time()) + 60*60*24

        feed_handler = FeedHandler(MockWebSocketSend(), session)
        feed_handler._feeds[feed_metadata.feed_id] = feed_metadata

        _ = asyncio.run(feed_handler._start_feed(feed_metadata))
