import os

# Tests must never touch a real database: set before app.config loads .env (real env vars win over .env).
os.environ["MONGODB_URI"] = "mongomock://tests"
