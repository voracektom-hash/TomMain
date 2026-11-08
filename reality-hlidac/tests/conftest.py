import json
from pathlib import Path

import pytest

from hlidac import db

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    yield connection
    connection.close()
