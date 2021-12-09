
import sqlite3
import os

DB_PATH = os.path.dirname(os.path.realpath(__file__)) + "/../.database.db"

def create_table_sql(table_spec):
    sql = "CREATE TABLE {0} ( {1} )".format(table_spec[0], ", ".join(table_spec[1:]))
    return sql

def main(db_path):
    assert not os.path.exists(db_path)
    account_table_spec = [
        "accounts",
        "account_id INTEGER PRIMARY KEY",
        "username TEXT NOT NULL UNIQUE",
        "password TEXT NOT NULL",
        "email TEXT NOT NULL",
        "mailing_address TEXT NULL",
    ]

    payout_table_spec = [
        "payouts",
        "payoutId INTEGER PRIMARY KEY",
        "account_id INTEGER NOT NULL",
        "status TEXT NOT NULL",
        "method TEXT NOT NULL",
        "amount INTEGER NOT NULL",

        "FOREIGN KEY(account_id) REFERENCES accounts(account_id)"
    ]

    invoice_table_spec = [        
        "invoices",
        "invoice_id INTEGER PRIMARY KEY",
        "status TEXT NOT NULL",
        "encoded_invoice TEXT NULL",
        "account_id INTEGER NOT NULL",
        "created_at INTEGER NOT NULL",
        "amount_requested INTEGER NOT NULL",
        "exchange_rate INTEGER NOT NULL",
        "expired_at INTEGER NULL",

        "FOREIGN KEY(account_id) REFERENCES accounts(account_id)"
    ]

    create_statements = []
    create_statements.append(create_table_sql(account_table_spec))
    create_statements.append(create_table_sql(payout_table_spec))
    create_statements.append(create_table_sql(invoice_table_spec))

    with sqlite3.connect(DB_PATH) as conn:
        for create_statement in create_statements:
            print("Executing Create statement: " + create_statement)
            cursor = conn.cursor()
            cursor.execute(create_statement)
            conn.commit()



if __name__ == '__main__':
    main(DB_PATH)
