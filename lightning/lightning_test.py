from .lightning import LightningNode, LightningMonitor
from .pubsub import Pubsub
from .db import DBInvoice, DBAccount, DBUtils
import unittest
import random
import time
import logging
import sys

logging.basicConfig(
    format = '%(asctime)s %(module)s %(levelname)s: %(message)s',
    level = logging.DEBUG,
    stream = sys.stdout)

class TestLightning(unittest.TestCase):

    def setUp(self):
        # TODO create a testing database to avoid poluting the real DB.
        account = DBAccount()
        account.username = "Jack" + str(random.random())
        account.password = "dummypass"
        account.email = "dummyemail"
        account.mailing_address = "Addr"
        self.test_account: DBAccount = DBAccount.create_account(account)

    def tearDown(self):
        DBUtils.delete("accounts", "account_id", self.test_account.account_id)
        
    def test_account(self):
        class DummyLightningNode(LightningNode):
            def invoice(self, invoice_label, msatoshi, description, expiry):
                return "encoded_invoice", 1999209
            def invoice_status(self, invoice_label):
                return "paid"
        
        moniter = LightningMonitor(lightning_node = DummyLightningNode(), polling_interval=0)
        try:
            moniter.start()
            # Subscribe to "invoice/pending" topic which is expected to be published
            # by Lightning moniter
            pending_callback_called = [False]
            def pending_callback(topic, updated_invoice: DBInvoice):
                pending_callback_called[0] = True
                self.assertEqual(topic, "/invoice/pending")
                self.assertEqual(updated_invoice.encoded_invoice, "encoded_invoice")
                self.assertEqual(updated_invoice.expired_at, 1999209)
            Pubsub.instance.subscribe("/invoice/pending", pending_callback)

            finalized_callback_called = [False]
            def finalized_callback(topic, updated_invoice: DBInvoice):
                finalized_callback_called[0] = True
                self.assertEqual(topic, "/invoice/finalized")
                self.assertEqual(updated_invoice.status, "paid")
            Pubsub.instance.subscribe("/invoice/finalized", finalized_callback)

            # Create invoice
            invoice = DBInvoice()
            invoice.account_id = self.test_account.account_id
            invoice.created_at = 239393939
            invoice.amount_requested = 20000
            invoice.exchange_rate = 30030.0
            created_invoice = DBInvoice.create_invoice(invoice)

            # Expect "invoice/pending" topic is going to be published.
            self.assertTrue(pending_callback_called[0])
            time.sleep(0.1)
            self.assertTrue(finalized_callback_called[0])

            DBUtils.delete("invoices", "invoice_id", created_invoice.invoice_id)
        finally:
            moniter.stop()


