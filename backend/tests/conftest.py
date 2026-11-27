from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from app.db import get_session, get_today, make_engine
from app.main import app

TODAY = date(2026, 6, 1)


@pytest.fixture
def client():
    engine = make_engine("sqlite://", poolclass=StaticPool)

    def session_override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
