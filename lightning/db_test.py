from .db import DBInvoice, DBAccount, DBUtils
from pprint import pprint
import unittest

class TestDB(unittest.TestCase):

    def test_account(self):
        account = DBAccount()
        account.username = "Jack1433123"
        account.password = "dsafdsafdsaf"
        account.email = "dsafdsaf"
        account.mailing_address = "Addr"
        created_account = DBAccount.create_account(account)
        pprint(vars(created_account))
        self.assertIsNotNone(created_account)
        self.assertEquals(created_account.username, account.username)
        self.assertEquals(created_account.password, account.password)
        self.assertEquals(created_account.email, account.email)
        self.assertEquals(created_account.mailing_address, account.mailing_address)

        select_account = DBAccount.get_account_by_username(account.username)
        pprint(vars(select_account))
        self.assertIsNotNone(select_account)

        DBUtils.delete("accounts", "account_id", account.account_id)
        deleted_account = DBAccount.get_account_by_username(account.username)
        self.assertIsNone(deleted_account)

if __name__ == '__main__':
    unittest.main()

