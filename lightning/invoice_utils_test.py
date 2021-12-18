from .invoice_utils import InvoiceGenerator
from .pubsub import Pubsub
from copy import copy
import unittest
from .db import DBInvoice
from threading import Timer
from .auth import JwtTokenUtils, JwtTokenPayload

class InvoiceGeneratorTest(unittest.TestCase):
    def test_generate(self):
        class InvoiceGeneratorUnderTest(InvoiceGenerator):
            def __init__(self):
                InvoiceGenerator.__init__(self)

            def _exchange_info(self):
                return {"sat_per_usd": 2000}

            def _db_create_invoice(self, new_invoice: DBInvoice):
                new_invoice.invoice_id = 1
                def pending_invoice_ready():
                    print("pending_invoice_ready")
                    pending_invoice = copy(new_invoice)
                    pending_invoice.encoded_invoice = "encode-invoice"
                    pending_invoice.state = "pending"
                    pending_invoice.expired_at = 1023508393
                    Pubsub.instance.publish("/invoice/pending", pending_invoice)
                t = Timer(0.5, pending_invoice_ready)
                t.start()
                
                return new_invoice

        generator = InvoiceGeneratorUnderTest()
        invoice = generator.generate(10, 1000)
        self.assertEqual(invoice["invoice_id"], 1)
        self.assertEqual(invoice["encoded_invoice"], "encode-invoice")
        self.assertEqual(invoice["expired_at"], 1023508393)
        self.assertEqual(invoice["amount_requested"], 1000)
        self.assertEqual(invoice["exchange_rate"], 2000)
