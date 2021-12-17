from .socket_handler import _JsonRpcHandler
from copy import copy
import asyncio
from .pubsub import Pubsub
import random
import unittest
from .db import DBInvoice, DBAccount, DBUtils
import time
from .auth import JwtTokenUtils, JwtTokenPayload

class JsonRpcHandlerTest(unittest.TestCase):

    def test_createInvoice(self):
        class JsonRpcHandlerUnderTest(_JsonRpcHandler):
            def __init__(self):
                _JsonRpcHandler.__init__(self)

            def _get_account_id(self):
                return 10

            async def _exchange_info(self):
                return {"sat_per_usd": 2000}

            async def _db_create_invoice(self, new_invoice: DBInvoice):
                new_invoice.invoice_id = 1
                def pending_invoice_ready():
                    pending_invoice = copy(new_invoice)
                    pending_invoice.encoded_invoice = "encode-invoice"
                    pending_invoice.state = "pending"
                    pending_invoice.expired_at = 1023508393
                    Pubsub.instance.publish("/invoice/pending", pending_invoice)
                asyncio.get_event_loop().call_later(0.5, pending_invoice_ready)
                
                return new_invoice

        handler = JsonRpcHandlerUnderTest()
        invoice = asyncio.run(handler.jsonrpc_create_invoice(1000))
        self.assertEqual(invoice["invoice_id"], 1)
        self.assertEqual(invoice["encoded_invoice"], "encode-invoice")
        self.assertEqual(invoice["expired_at"], 1023508393)
        self.assertEqual(invoice["amount_requested"], 1000)
        self.assertEqual(invoice["exchange_rate"], 2000)

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
        handler = _JsonRpcHandler()
        self.assertEqual(asyncio.run(handler.jsonrpc_authenticate(token)), "ok")
        self.assertEqual(handler.exp, payload.exp)
        self.assertEqual(handler.account_id, created_account.account_id)
        
        DBUtils.delete("accounts", "account_id", created_account.account_id)

        





