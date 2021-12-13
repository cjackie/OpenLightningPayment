. venv/bin/activate
python -m unittest lightning/db_test.py
python -m unittest lightning/pubsub_test.py
python -m unittest lightning/lightning_test.py
python -m unittest lightning/auth_test.py