import os
import shutil
import tempfile

_root = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_root}/test.db"
os.environ["STORAGE_DIR"] = f"{_root}/storage"
os.environ["BATCH_SIZE"] = "2"
os.environ["MAX_RECIPIENTS"] = "50"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def payload():
    return {
        "event_name": "Python Bootcamp 2026",
        "issuer": "Acme Academy",
        "recipients": [
            {"name": "Asha Rao", "email": "asha@acme.in"},
            {"name": "Ravi Kumar", "email": "ravi@acme.in"},
            {"name": "Meera Iyer", "email": "meera@acme.in"},
        ],
    }
