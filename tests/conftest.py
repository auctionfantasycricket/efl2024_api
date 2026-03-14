import os
import sys

# Add project root to path so test modules can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set dummy MONGO_URI before config is imported
os.environ.setdefault('MONGO_URI', 'mongodb://localhost:27017/')

# Patch MongoClient with mongomock BEFORE config.py is imported by any test module.
# This module-level patch is intentional — it must run before pytest collects tests.
import mongomock
from unittest.mock import patch


def _mock_mongo_client_factory(*args, **kwargs):
    """Create a mongomock client, ignoring real connection args (URI, tlsCAFile, etc.)."""
    return mongomock.MongoClient()


_patcher = patch('pymongo.MongoClient', side_effect=_mock_mongo_client_factory)
_patcher.start()

import pytest


@pytest.fixture
def mock_db():
    """Return the mongomock-backed db instance used by the app."""
    from config import db
    return db
