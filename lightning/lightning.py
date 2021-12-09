
import socket
import sys
import json
from .config import Config
import time
from threading import Lock
from typing import List
import logging
import re
from copy import copy
from .pubsub import Pubsub
from .db import DBInvoice, DBUtils
from threading import Thread

LOGGER = logging.Logger(__file__)

class LightningClient:
    def __init__(self, socket_file):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(socket_file)
        except Exception as e:
            LOGGER.warn(
                "LightningClient: Failed to open sock {}".format((str(e))))
            sys.exit(1)

        self.f = self.sock.makefile('r')

        self.id = 0

    def close(self):
        self.sock.close()

    def call(self, method, *args):
        response = self._call(method, *args)
        if response.get("error"):
            LOGGER.warn("LightningClient retry due to error: {}".format(response["error"]))
            time.sleep(0.5)
            response = self._call(method, *args)
            return response
        else:
            return response 

    def _call(self, method, *args):
        params = dict(args[0]) if len(args) == 1 and type(
              args[0]) == dict else list(args)
        request = {'method': method, 'params': params}
        request['id'] = self.id
        request['jsonrpc'] = '2.0'
        self.id += 1

        msg = json.dumps(request) + '\n'
        self.sock.sendall(msg.encode('ascii'))
        response = json.loads(self.f.readline())
        # Each response ends with two new lines, hence this.
        # ref: https://github.com/ElementsProject/lightning/blob/v0.10.1/contrib/pyln-client/pyln/client/lightning.py#L298
        _ = self.f.readline()
        return response

def CreateLightningClient() -> LightningClient:
    '''
        Caller owns the returned LightningClient. 
        LightningClient must be closed when it is not needed.
    '''
    return LightningClient(Config.LightningUnixSocket)

# class LightningOverview():
#     def __init__(self):
#         self.node_id = ""
#         self.alias = ""
#         self.funds_total_amount: int = None

#         self.total_spendable: int = None
#         self.total_receivable: int = None

#         self.num_active_channels: int = None
#         self.num_peers: int = None

# class LightningFund():
#     def __init__(self):
#         self.txid = ""
#         self.output: int = None
#         self.value: int = None
#         self.address = ""
#         self.status = ""

# class LightningChannel():
#     def __init__(self):
#         self.peer_id = ""
#         self.connected: int = None
#         self.funding_local_msat: int = None
#         self.funding_remote_msat: str = None
#         self.receivable_msat: str = None
#         self.spendable_msat: str = None
#         # Number of payment fulfilled that our Node received
#         self.in_payments_fulfilled: int = None
#         self.in_msatoshi_fulfilled: int = None
#         # Number of payment fulfilled that our Node sent
#         self.out_payments_fulfilled: int = None
#         self.out_msatoshi_fulfilled: int = None
#         self.state = ""

class LightningInvoice():
    def __init__(self):
        self.label: str = None
        self.bolt11 = ""
        self.msatoshi = 0
        self.status: str = None
        self.description: str = None
        self.expires_at = 0
        self.paid_at = 0

# class LightningPay():
#     def __init__(self):
#         self.bolt11 = ""
#         self.destination = ""
#         # status of the payment(one of "pending", "failed", "complete")
#         self.status = ""
#         self.created_at = 0
#         # the amount we actually sent, including fees. Example "3000msat"
#         self.amount_sent_msat = ""
#         # the amount the destination received, if known. Example "1000msat"
#         self.amount_msat = ""

class LightningNode():

    def invoice(self, invoice_label, msatoshi, description, expiry):
        """
        @description: should be for human as it is encoded in the invoice. no more than 100 chars.
        @expiry: without a suffix it is interpreted as seconds, otherwise suffixes s, m, h, d, w 
            indicate seconds, minutes, hours, days and weeks respectively. for example 60s = 60 seconds
        @return (bolt11 string, expired_at) where bolt11 string encodes the invoice, and 
            expires_at is an UNIX timestamp of when invoice expires. see here for more on bolt11
            https://github.com/lightningnetwork/lightning-rfc/blob/v1.0/11-payment-encoding.md
        """
        assert len(description) < 100

        client: LightningClient = CreateLightningClient()
        try:
            params = {
                "msatoshi": msatoshi,
                "label": invoice_label,
                "description": description,
                "expiry":  expiry
            }
            invoice_response = client.call("invoice", params)
            assert invoice_response.get(
                "error") is None, invoice_response.get("error")

            # Check for any warnings. Abort if there is any.
            result = invoice_response["result"]
            warnings = []
            for key, value in result.items():
                if key.startswith("warning_"):
                    warnings.append((key, value))
            if warnings:
                LOGGER.warn("Invoice warnings: {}".format(warnings))
                raise Exception("invoice has warnings")

            return result["bolt11"], result["expires_at"]
        finally:    
            client.close()

    def invoice_status(self, invoice_label):
        """
        @return: Whether it's paid, unpaid or unpayable (one of "unpaid", "paid", "expired").
        """
        client = CreateLightningClient()
        try:
            listinvoices_response = client.call("listinvoices", invoice_label)
            assert listinvoices_response.get("error") is None
            invoices = listinvoices_response["result"]["invoices"]
            assert len(invoices) == 1, "Expecting exactly 1 invoice for {}, but got {}".format(
                invoice_label,  len(invoices))

            return invoices[0]["status"]
        finally:
            client.close()

# def get_lightning_overview():
#     client = CreateLightningClient()
#     try:
#         getinfo_response = client.call("getinfo")
#         assert getinfo_response.get("error") is None, "getinfo failed: {}".format(getinfo_response["error"])

#         info = getinfo_response["result"]
#         overview = LightningOverview()
#         overview.node_id = info["id"]
#         overview.alias = info["alias"]
#         overview.num_peers = info["num_peers"]
#         overview.num_active_channels = info["num_active_channels"]

#         listpeers_response = client.call("listpeers")
#         assert listpeers_response.get("error") is None, "listpeers failed: {}".format(listpeers_response["error"])

#         overview.total_receivable = 0
#         overview.total_spendable = 0
#         peers = listpeers_response["result"]["peers"]
#         for peer in peers:
#             for channel in peer["channels"]:
#                 overview.total_receivable += channel["receivable_msatoshi"] // 1000
#                 overview.total_spendable += channel["spendable_msatoshi"] // 1000

#         listfunds_response = client.call("listfunds")
#         assert listfunds_response.get(
#             "error") is None, "listfunds failed: {}".format(listfunds_response["error"])

#         funds = listfunds_response["result"]
#         overview.funds_total_amount = 0
#         for output in funds["outputs"]:
#             overview.funds_total_amount += output["value"]

#         return overview
#     finally:
#         client.close()

# def listfunds() -> List[LightningFund]:
#     client = CreateLightningClient()
#     try:
#         listfunds_response = client.call("listfunds")
#         assert listfunds_response.get(
#             "error") is None, "listfunds failed: {}".format(listfunds_response["error"])

#         funds = listfunds_response["result"]["outputs"]
#         result = []
#         for fund in funds:
#             lightning_fund = LightningFund()
#             lightning_fund.txid = fund["txid"]
#             lightning_fund.output = fund["output"]
#             lightning_fund.value = fund["value"]
#             lightning_fund.address = fund["address"]
#             lightning_fund.status = fund["status"]
#             result.append(lightning_fund)
#         return result
#     finally:
#         client.close()

# def get_channels() ->  List[LightningChannel]:
#     client = CreateLightningClient()
#     try:
#         listpeers_response = client.call("listpeers")
#         assert listpeers_response.get(
#             "error") is None, "listpeers failed: {}".format(listpeers_response["error"])

#         peers = listpeers_response["result"]["peers"]

#         lightning_channels: List[LightningChannel] = []
#         for peer in peers:
#             for channel in peer["channels"]:
#                 lightning_channel = LightningChannel()
#                 lightning_channel.peer_id = peer["id"]
#                 lightning_channel.connected = peer["connected"]
#                 lightning_channel.funding_local_msat = channel["funding"]["local_msat"]
#                 lightning_channel.funding_remote_msat = channel["funding"]["remote_msat"]
#                 lightning_channel.receivable_msat = channel["receivable_msat"]
#                 lightning_channel.spendable_msat = channel["spendable_msat"]
#                 lightning_channel.in_payments_fulfilled = channel["in_payments_fulfilled"]
#                 lightning_channel.in_msatoshi_fulfilled = channel["in_msatoshi_fulfilled"]
#                 lightning_channel.out_payments_fulfilled = channel["out_payments_fulfilled"]
#                 lightning_channel.out_msatoshi_fulfilled = channel["out_msatoshi_fulfilled"]
#                 lightning_channel.state = channel["state"]
#                 lightning_channels.append(lightning_channel)
        
#         return lightning_channels

#     finally:
#         client.close()


# def _listinvoices() -> List[LightningInvoice]:
#     client = CreateLightningClient()
#     try:
#         listinvoices_response = client.call("listinvoices")
#         assert listinvoices_response.get("error") is None

#         invoices: List[LightningInvoice] = []
#         for invoice_json in listinvoices_response["result"]["invoices"]:
#             invoice = LightningInvoice()
#             invoice.label = invoice_json["label"]
#             invoice.bolt11 = invoice_json["bolt11"]
#             invoice.msatoshi = invoice_json["msatoshi"]
#             invoice.status: str = invoice_json["status"]
#             invoice.description: str = invoice_json["description"]
#             invoice.expires_at = invoice_json["expires_at"]
#             if "paid_at" in invoice_json:
#                 invoice.paid_at = invoice_json["paid_at"]
#             invoices.append(invoice)
#         return invoices
#     finally:
#         client.close()

# def decode(invoice) -> LightningInvoice:
#     """
#     @invoice: is a str, bolt11.
#     """
#     client = CreateLightningClient()
#     try:
#         decode_response = client.call("decode", invoice)
#         assert decode_response.get("error") is None

#         result = decode_response["result"]
#         assert result["valid"], "decode is invalid"

#         invoice = LightningInvoice()
#         invoice.msatoshi = result["msatoshi"]
#         invoice.description: str = result["description"]
#         return invoice
#     finally:
#         client.close()

# def pay(invoice) -> int:
#     """
#     @invoice: is a str, bolt11.
#     @return: return msatoshi sent.
#     """
#     client = CreateLightningClient()
#     try:
#         pay_response = client.call("pay", invoice)
#         assert pay_response.get("error") is None, pay_response["error"]

#         return pay_response["result"]["msatoshi_sent"]
#     finally:
#         client.close()


class LightningMonitor(Thread):
    instance = None
    
    LABEL_PREFIX = "OpenLightningWallet"

    def __init__(self, lightning_node: LightningNode = None, polling_interval=0.5):
        Thread.__init__(self)
        # delegate to methods.
        def on_dbinvoice_created(topic:str, invoice: DBInvoice):
            self._create_invoice(topic, invoice)

        Pubsub.instance.subscribe('/invoice/created', on_dbinvoice_created)
        
        self._lightning_node = lightning_node if lightning_node else LightningNode()
        self._pending_labels = {}
        self._lock = Lock()
        self._stop = False
        self._polling_interval = polling_interval
        
    def _create_invoice(self, topic, invoice: DBInvoice):
        assert invoice.invoice_id not in self._pending_labels
        assert topic == '/invoice/created'
        # Ask Lightning to generate an invoice
        label = "{}-{}-{}".format(LightningMonitor.LABEL_PREFIX, invoice.account_id, invoice.invoice_id)
        msatoshi = round(invoice.amount_requested * invoice.exchange_rate * 1000)
        expiry = "10m"
        encoded_invoice, expired_at = self._lightning_node.invoice(label, msatoshi, "", expiry)

        # Update database
        update_invoice = {
            'status': 'pending',
            'encoded_invoice': encoded_invoice,
            'expired_at': expired_at,
        }
        DBUtils.update('invoices', update_invoice, "invoice_id", invoice.invoice_id)

        # Add to watchlist
        self._lock.acquire()
        try:
            self._pending_labels[invoice.invoice_id] = label
        finally:
            self._lock.release()

        # Notify status update for invoice.
        updated_invoice: DBInvoice = copy(invoice)
        updated_invoice.status = update_invoice['status']
        updated_invoice.encoded_invoice = update_invoice['encoded_invoice']
        updated_invoice.expired_at = update_invoice['expired_at']
        Pubsub.instance.publish("/invoice/pending", updated_invoice)

    def _finalize_invoice(self, invoice_id, status):
        assert invoice_id in self._pending_labels
        assert status in ["expired", "paid"], "Invalid status {}".format(status)
        # Update database
        update_invoice = {
            'status': status,
        }
        DBUtils.update('invoices', update_invoice, "invoice_id", invoice_id)

        # Notify the status update
        updated_invoice = DBInvoice()
        updated_invoice.invoice_id = invoice_id
        updated_invoice.status = status
        Pubsub.instance.publish("/invoice/finalized", updated_invoice)

        # Remove it from the watchlist
        self._lock.acquire()
        try:
            del self._pending_labels[invoice_id]
        finally:
            self._lock.release()

    def stop(self):
        self._stop = True

    def run(self):
        LOGGER.debug("LightningMonitor start")
        while not self._stop:
            self._lock.acquire()
            pending_labels = dict(self._pending_labels)
            self._lock.release()

            time.sleep(self._polling_interval)
            try:
                for invoice_id, pending_label in pending_labels.items():
                    status = self._lightning_node.invoice_status(pending_label)
                    if status == 'paid' or status == 'expired':
                        self._finalize_invoice(invoice_id, status)

            except Exception as e:
                LOGGER.debug(str(e))
        
        LOGGER.debug("LightningMonitor has stopped.")



# # The captured group is the ID for the invoice
# _gInvoiceLabelPattern = r"^banana-lightning-([\d]+)$"
# _gLigthningMetadata = {
#     "lastInvoiceId": None
# }
# _gInvoiceIdLock: Lock = Lock()

# def _next_invoice_label(account):
#     if not _gInvoiceIdLock.acquire(True, 30):
#         raise Exception("Deadlock?")
#     _gLigthningMetadata["lastInvoiceId"] += 1
#     invoice_id = _gLigthningMetadata["lastInvoiceId"]
#     _gInvoiceIdLock.release()

#     invoice_label = "banana-lightning-{}".format(invoice_id)
#     assert re.fullmatch(_gInvoiceLabelPattern, invoice_label) is not None
#     return invoice_label

# def _init_ligthning_metadata():
#     client = CreateLightningClient()
#     try:
#         listinvoices_response = client.call("listinvoices")
#         assert listinvoices_response.get("error") is None

#         invoices = listinvoices_response["result"]["invoices"]
#         _gLigthningMetadata["lastInvoiceId"] = 0
#         for invoice in invoices:
#             label = invoice["label"]
#             match = re.fullmatch(_gInvoiceLabelPattern, label)
#             if match:
#                 assert len(match.groups()) == 1
#                 invoice_id = int(match.groups()[0])
#                 if invoice_id > _gLigthningMetadata["lastInvoiceId"]:
#                     _gLigthningMetadata["lastInvoiceId"] = invoice_id
#     finally:
#         client.close()

# _init_ligthning_metadata()
