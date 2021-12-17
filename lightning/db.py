
import os
import sqlite3
from copy import deepcopy
from .pubsub import Pubsub
import logging

LOGGER = logging.Logger(__file__)

class DatabaseParams():
    _DBPath = os.path.dirname(os.path.realpath(__file__)) + "/.database.db"

    @classmethod
    def set_db_path(cls, path):
        cls._DBPath = path

class DBUtils():
    def update(table_name, field_values: dict, id_column, id_column_value):
        with sqlite3.connect(DatabaseParams._DBPath) as conn:
            cursor = conn.cursor()
            field_value_strs = []
            args = []
            for field in field_values:
                field_value_strs.append("{} = ?".format(field))
                args.append(field_values[field])

            args.append(id_column_value)
            update_statement = "UPDATE {} SET {} WHERE {} = ?".format(table_name, ", ".join(field_value_strs), id_column)

            LOGGER.debug("update_statement: {}".format(update_statement))

            cursor.execute(update_statement, tuple(args))

    def delete(table_name, id_column, id_column_value):
        with sqlite3.connect(DatabaseParams._DBPath) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM {} WHERE {} = ?".format(table_name, id_column), (id_column_value, ))
            cursor.close()

    def select(obj_template, select_template, args):
        """
        select rows according to @select_template and @args and turn them into list of copies of @obj_template.
        @precondition: table column name must be present in obj_template.__dict__ i.e field of obj_template.
        @select_template: string
        @args: tuple
        """
        with sqlite3.connect(DatabaseParams._DBPath) as conn:
            cursor = conn.cursor()
            cursor.execute(select_template, args)
            field_names = [d[0] for d in cursor.description]
            result = []
            for row in cursor:
                obj = deepcopy(obj_template)
                # Map each column in the table into field in the object. Raise an exception if not found.
                for i, col in enumerate(field_names):
                    if col not in obj.__dict__:
                        raise Exception("column {} is not find in obejct {} from statement {}".format(col, obj, select_template))
                    obj.__dict__[col] = row[i]           
                result.append(obj)
            return result

    def insert(obj, table_name, id_column_name = ""):
        """
        Map each non-default field of @obj into columns in table_name. Each field names of @obj must have a 
        column with the same name in @table_name.
        @id_column_name, if available the ID for the inserted object is populated in @id_column_name field of @obj.
        """
        with sqlite3.connect(DatabaseParams._DBPath) as conn:
            # Prepare INSERT statement.
            columns = list(obj.__dict__.keys())
            # Kepp columns with non default values
            columns = list(filter(lambda c: obj.__dict__[c], columns))
            n_question_marsk = ["?"]*len(columns)
            create_statement_template = "INSERT INTO {0} ({1}) VALUES ({2})".format(table_name, ", ".join(columns), ", ".join(n_question_marsk))
            LOGGER.info("INSERT statement template: " + create_statement_template)

            # Prepare column values.
            values = []
            for column in columns:
                values.append(obj.__dict__[column])
            
            # Insert into database.
            cursor = conn.cursor()
            cursor.execute(create_statement_template, tuple(values))
            if id_column_name:
                obj.__dict__[id_column_name] = cursor.lastrowid
            conn.commit()
            return obj

class DBAccount():
    def __init__(self):
        # Merchant account ID
        self.account_id: int = 0
        self.username: str = ""
        self.password: str = ""
        self.email: str = ""
        self.mailing_address = ""

    @classmethod
    def create_account(cls, account): 
        """
        @account: DBAccount
        @return: DBAccount
        """
        return DBUtils.insert(account, "accounts", id_column_name = "account_id")
    
    @classmethod
    def get_account_by_username(cls, username):
        """
        @return: None on not found.
        """
        select_template = "SELECT account_id, username, password, email, mailing_address FROM accounts WHERE username = ?"
        args = (username, )
        accounts: DBAccount = DBUtils.select(DBAccount(), select_template, args)
        assert len(accounts) <= 1
        return accounts[0] if accounts else None

class DBPayout():
    def __init__(self):
        '''
        An entry representing merchant want to initiate a receiving a payment on USD.
        '''
        # Merchant account who initiated the payout
        self.account_id: int = 0
        # Status is one of following "initiated", "pending", "sent", "completed", "failed"
        # "initiated" is the default which means merchant requested for receiving USD.
        # "pending" means the pay process started
        # "sent" means pay is considered on the way to merchant
        # "completed" means the pay considered successful and no actions are needed.
        self.status = "initiated"
        # only support "mail"
        self.method = ""
        # In USD
        self.amount = 0        

class DBInvoice():
    def __init__(self):
        # Unique ID per invoice.
        self.invoice_id: int = 0
        # Status of the invoice(one of "created", "pending", "expired", "complete")
        # "created" is the efault value. 
        # "pending" means the invoice has been picked up by Lightning.
        # "expired" means the invoice has expired.
        # "paid" means successful.
        self.status = "created"
        # e.g Bolt11
        self.encoded_invoice: str = ""
        # Merchant who holds generated this invoice.
        self.account_id: int = 0
        # Unix time in seconds.
        self.created_at = 0
        # Amount requested in USD in cents. 1 dollar = 100 cents
        self.amount_requested = 0
        # The echange rate SAT/USD.
        self.exchange_rate = 0
        # Unix time in seconds when the invoice is considered expired.
        self.expired_at = 0

    @classmethod
    def get_invoice_by_id(cls, invoice_id: int):        
        select_template = '''
            SELECT (invoice_id, status, encoded_invoice, account_id, created_at,
                    amount_requested, exchange_rate, expired_at) 
            FROM accounts WHERE (invoice_id = ?)
        '''
        args = (invoice_id ,)
        invoices: DBInvoice = DBUtils.select(DBInvoice(), select_template, args)
        assert invoices <= 1
        return invoices[0] if invoices else None
    
    @classmethod
    def create_invoice(cls, invoice):
        """
        @invoice: DBInvoice
        @invoice: DBInvoice
        """
        created_invoice = DBUtils.insert(invoice, "invoices", id_column_name="invoice_id")
        Pubsub.instance.publish("/invoice/created", created_invoice)
        return created_invoice

    @classmethod
    def from_row(cls, row):
        invoice = DBInvoice()
        invoice.invoice_id: int = row.invoice_id
        invoice.status = row.status
        invoice.encoded_invoice: str = row.encoded_invoice
        invoice.account_id: int = row.account_id
        invoice.created_at = row.created_at
        invoice.amount_requested = row.amount_requested
        invoice.exchange_rate = row.exchange_rate
        invoice.expired_at = row.expired_at
        return invoice
