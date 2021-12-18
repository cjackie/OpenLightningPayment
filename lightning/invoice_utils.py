
from werkzeug.exceptions import BadRequest, InternalServerError
from .db import DBInvoice
import lightning.market
import time
import logging
from .pubsub import Pubsub
from .config import Config

# TODO: Move this to a top level code.
logging.basicConfig(format='%(filename)s:%(funcName)s:%(levelname)s:%(message)s')

LOGGER = logging.getLogger(__file__)
LOGGER.setLevel(Config.LoggingLevel)

class InvoiceGenerator():
    def __init__(self):
        self.pending_invoice = None
        self.created_invoice = None

    def _exchange_info(self):
        return market.exchange_info()

    def _db_create_invoice(self, new_invoice: DBInvoice):
        try:
            return DBInvoice.create_invoice(new_invoice)
        except Exception as e:
            LOGGER.debug("Failed to create invoice: " + str(e))

    def _add_pending_invoice_to_state_callback(self):
        def on_topic(topic, pending_invoice):
            assert topic == "/invoice/pending"
            if self.created_invoice.invoice_id == pending_invoice.invoice_id:
                self.pending_invoice = pending_invoice
        return on_topic

    def generate(self, account_id: int, amount_requested: int):
        """
        Call once per instance.
        """
        # Build the invoice
        new_invoice = DBInvoice()
        new_invoice.amount_requested = amount_requested
        try:
            exchange_info = self._exchange_info()
        except Exception as e:
            LOGGER.debug("Failed to get exchange info: {}".format(str(e)))
            raise InternalServerError()

        new_invoice.exchange_rate = exchange_info["sat_per_usd"]
        new_invoice.created_at = int(time.time())
        new_invoice.account_id = account_id
        
        # Subcribe to pending invoice topic which would add the pending invoice to our state.
        subscriber_id = Pubsub.instance.subscribe("/invoice/pending", self._add_pending_invoice_to_state_callback())
        try:
            # Insert the invoice into DB.
            self.created_invoice = self._db_create_invoice(new_invoice)
            if self.created_invoice is None:
                raise InternalServerError("Failed to generate invoice.")

            # Keeping polling the pending invoice until found or timeout.
            start = time.time()
            while self.pending_invoice is None:
                if time.time() - start > 2.5:
                    LOGGER.debug("Waiting for the pending invoice timeout: invoice_id={}".format(self.created_invoice.invoice_id))
                    raise InternalServerError("Waiting for the pending invoice timeout")
                time.sleep(0.1)
        
            # Ready
            return {
                "invoice_id": self.pending_invoice.invoice_id,
                "encoded_invoice": self.pending_invoice.encoded_invoice,
                "amount_requested": self.pending_invoice.amount_requested,
                "exchange_rate": self.pending_invoice.exchange_rate,
                "expired_at": self.pending_invoice.expired_at
            }
        finally:
            Pubsub.instance.unsubscribe(subscriber_id)
