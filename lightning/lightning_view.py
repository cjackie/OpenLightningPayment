from lightning import LightningChannel, LightningFund, LightningOverview, LightningInvoice, LightningPay
import lightning
from datetime import datetime
from view_utils import Satcomma, with_thousands_separators, omitted_txid, omitted_bitcoin_address, with_thousands_separators_msat_str


def _unix_time_to_str(utc_seconds):
    return str(datetime.utcfromtimestamp(utc_seconds))

class LightningOverviewView():
    def __init__(self, lightning_overview: LightningOverview):
        self.node_id = lightning_overview.node_id
        self.alias = lightning_overview.alias
        self.num_active_channels: int = lightning_overview.num_active_channels
        self.num_peers: int = lightning_overview.num_peers

        self.funds_total_amount_satcomma = Satcomma.from_sats(lightning_overview.funds_total_amount)
        self.total_spendable_satcomma = Satcomma.from_sats(
            lightning_overview.total_spendable)
        self.total_receivable_satcomma = Satcomma.from_sats(
            lightning_overview.total_receivable)
        self.total_receivable_msat = with_thousands_separators_msat_str(str(
            lightning_overview.total_receivable*1000) + "msat")

class LightningFundView():
    def __init__(self, lightning_fund: LightningFund):
        self.txid = lightning_fund.txid
        self.output: int = lightning_fund.output
        self.address = lightning_fund.address
        self.status = lightning_fund.status

        self.value_satcomma = Satcomma.from_sats(lightning_fund.value)
        self.omitted_txid = omitted_txid(lightning_fund.txid)
        self.omitted_address = omitted_bitcoin_address(lightning_fund.address)

class LightningChannelView():
    def __init__(self, lightning_channel: LightningChannel):
        self.peer_id = lightning_channel.peer_id
        self.funding_local_msat = lightning_channel.funding_local_msat
        self.funding_remote_msat = lightning_channel.funding_remote_msat
        self.connected: int = lightning_channel.connected
        # Number of payment fulfilled that our Node received
        self.in_payments_fulfilled: int = lightning_channel.in_payments_fulfilled
        # Number of payment fulfilled that our Node sent
        self.out_payments_fulfilled: int = lightning_channel.out_payments_fulfilled
        self.state = lightning_channel.state

        self.omitted_peer_id = lightning_channel.peer_id[0:4] + \
            "..." + lightning_channel.peer_id[-4:]
        self.formatted_in_msatoshi_fulfilled = with_thousands_separators(
            lightning_channel.in_msatoshi_fulfilled)
        self.formatted_out_msatoshi_fulfilled = with_thousands_separators(
            lightning_channel.out_msatoshi_fulfilled)
        self.formatted_funding_local_msat = with_thousands_separators_msat_str(lightning_channel.funding_local_msat)
        self.formatted_funding_remote_msat = with_thousands_separators_msat_str(lightning_channel.funding_remote_msat)
        self.formatted_receivable_msat = with_thousands_separators_msat_str(lightning_channel.receivable_msat)
        self.formatted_spendable_msat = with_thousands_separators_msat_str(lightning_channel.spendable_msat)
    
class LightningInvoiceView():
    def __init__(self, lightning_invoice: LightningInvoice):
        self.label = lightning_invoice.label
        self.bolt11 = lightning_invoice.bolt11
        self.msatoshi = lightning_invoice.msatoshi
        self.status = lightning_invoice.status
        self.description = lightning_invoice.description
        self.expires_at = lightning_invoice.expires_at
        self.paid_at = lightning_invoice.paid_at

        self.formatted_msatoshi = with_thousands_separators(
            lightning_invoice.msatoshi)
        self.formatted_paid_at = "" if self.paid_at == 0 else _unix_time_to_str(
            self.paid_at)
        self.formatted_expires_at = "" if self.expires_at == 0 else _unix_time_to_str(
            self.expires_at)
        self.omitted_bolt11 = self.bolt11[0:5]  + "..." + self.bolt11[-5:]    

class LightningPayView():
    def __init__(self, lightning_pay: LightningPay):
        self.bolt11 = lightning_pay.bolt11
        self.destination = lightning_pay.destination
        self.status = lightning_pay.status
        self.created_at = lightning_pay.created_at

        self.formatted_amount_sent_msat = with_thousands_separators_msat_str(
            lightning_pay.amount_sent_msat)
        self.formatted_amount_msat = with_thousands_separators_msat_str(
            lightning_pay.amount_msat)
        self.formatted_fee_msat = with_thousands_separators_msat_str(
            str(lightning_pay.fee_msatoshi) + "msat")
        self.formatted_created_at = _unix_time_to_str(lightning_pay.created_at)
        self.omitted_bolt11 = lightning_pay.bolt11[0:5] + \
            "..." + lightning_pay.bolt11[-5:]

def get_lightning_overview_view():
    lightning_overview = lightning.get_lightning_overview()
    return LightningOverviewView(lightning_overview)

def get_fund_views():
    return [LightningFundView(lightning_fund) for lightning_fund in lightning.listfunds()]

def get_channel_views():
    return [LightningChannelView(lightning_channel) for lightning_channel in lightning.get_channels()]

def get_invoice_views():
    return [LightningInvoiceView(lightning_invoice) for lightning_invoice in lightning.listinvoices()]

def get_payviews():
    return [LightningPayView(lightning_pay) for lightning_pay in lightning.listpays()]
