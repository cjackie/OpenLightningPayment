. venv/bin/activate
python -m unittest lightning/db_test.py
python -m unittest lightning/pubsub_test.py
python -m unittest lightning/lightning_test.py
python -m unittest lightning/auth_test.py
python -m unittest lightning/socket_handler_test.py
python -m unittest lightning/invoice_utils_test.py
python -m unittest lightning/jsonrpc_over_websocket_test.py