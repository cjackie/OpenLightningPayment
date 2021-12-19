from .jsonrpc_over_websocket import JsonRpc, WebSocketServerProtocolWrapper, JsonRpcHandlerImpl, JsonRpcSession
import websockets
from copy import copy
import asyncio
import random
import json
import unittest
from .db import DBInvoice, DBAccount, DBUtils
import time
from .auth import JwtTokenUtils, JwtTokenPayload, JwtTokenDecodeError

class JsonRpcHandlerTest(unittest.TestCase):

    def test_jsonrpc(self):
        class MockWebSocket():
            def __init__(self):
                self.messages = []
                self.sent = []
            def mock_received_data(self, data):
                self.messages.append(data)
            async def send(self, data:str):
                self.sent.append(data)
                raise websockets.exceptions.ConnectionClosedError(None, None)
            async def recv(self):
                return self.messages.pop(0)
            async def close():
                pass

        mock_websocket = MockWebSocket()
        jsonrpc = JsonRpc(WebSocketServerProtocolWrapper(mock_websocket))        
        mock_websocket.mock_received_data('{"id": 2, "jsonrpc": "2.0", "params": ["hello from client request 2"], "method": "echo"}')
        def disconnect():
            jsonrpc.stop()
        loop = asyncio.new_event_loop()
        loop.call_later(1, disconnect)
        loop.run_until_complete(jsonrpc.handle())
        self.assertEqual(len(mock_websocket.sent), 1)
        response = json.loads(mock_websocket.sent[0])
        print(mock_websocket.sent)
        self.assertEqual(response["id"], 2)
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["result"], "hello from client request 2")

    def test_authenticate(self):
        # Create the account for the token creation
        account = DBAccount()
        account.username = "Jack" + str(random.randint(0, 10e12))
        account.password = "dsafdsafdsaf"
        account.email = account.username + "@gmail.com"
        account.mailing_address = "Addr" + str(random.randint(0, 10e12))
        created_account = DBAccount.create_account(account)

        # Create token
        payload = JwtTokenPayload()
        payload.sub = account.username 
        payload.iat = int(time.time())
        payload.exp = int(time.time()) + 60*60*24
        token = JwtTokenUtils().sign_and_build_jwt_token(payload)

        # Test
        class MockWebSocket():
            def __init__(self):
                self.messages = []
        session = JsonRpcSession()
        impl = JsonRpcHandlerImpl(None, session)
        self.assertEqual(asyncio.run(impl._jsonrpc_authenticate(token)), "ok")
        self.assertEqual(session.exp, payload.exp)
        self.assertEqual(session.account_id, created_account.account_id)
        
        DBUtils.delete("accounts", "account_id", created_account.account_id)

        
