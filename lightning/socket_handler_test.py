from .socket_handler import Feed
from copy import copy
import asyncio
from .pubsub import Pubsub
import random
import unittest
from .db import DBInvoice, DBAccount, DBUtils
import time
from .auth import JwtTokenUtils, JwtTokenPayload

class FeedTest(unittest.TestCase):

    def test_getFinalizedInvoices(self):
        feed = Feed()

        # Mock the feed as authenticated.
        feed.exp = int(time.time()) + 60*60*24
        feed.account_id = 1

        # Select the type of the feed
        feed.select(Feed.FEED_FINALIZED_INVOICES)

        self.assertEqual(feed.get(), [])
        
        # Publish a unrelated invoice
        finalized_invoice = DBInvoice()
        finalized_invoice.account_id = 12
        finalized_invoice.invoice_id = 19
        finalized_invoice.status = "paid" 
        Pubsub.instance.publish("/invoice/finalized", finalized_invoice)
        self.assertEqual(feed.get(), [])

        # Publish a related invoices
        finalized_invoice.account_id = 1
        Pubsub.instance.publish("/invoice/finalized", finalized_invoice)
        result = feed.get()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["invoice_id"], 19)
        self.assertEqual(result[0]["status"], "paid")
        self.assertEqual(feed.finalized_invoices, [])

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
        feed = Feed()
        feed.authenticate(token)
        self.assertEqual(feed.exp, payload.exp)
        self.assertEqual(feed.account_id, created_account.account_id)
        
        DBUtils.delete("accounts", "account_id", created_account.account_id)

        





