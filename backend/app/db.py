"""MongoDB access. `mongomock://` URIs give an in-memory DB for local dev and tests."""
from __future__ import annotations

from pymongo import ASCENDING

from . import config

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        if config.MONGODB_URI.startswith("mongomock://"):
            import mongomock
            _client = mongomock.MongoClient()
        else:
            from pymongo import MongoClient
            _client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=8000)
        _db = _client[config.MONGODB_DB]
        # raw_series: one doc per grid cell; analyses: one doc per (cell, range)
        _db.raw_series.create_index([("key", ASCENDING)], unique=True)
        _db.analyses.create_index([("computed_at", ASCENDING)], expireAfterSeconds=config.ANALYSIS_TTL_S)
    return _db


def reset_for_tests():
    global _client, _db
    _client = _db = None
