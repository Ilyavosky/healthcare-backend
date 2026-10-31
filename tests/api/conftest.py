import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, search_time_limit_ms=10000, max_csv_bytes=5000)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def example_body() -> dict:
    return {
        "patients": [
            {"id": "P1", "level": 2, "wait": 5, "duration": 20},
            {"id": "P2", "level": 3, "wait": 40, "duration": 5},
            {"id": "P3", "level": 1, "wait": 0, "duration": 30},
        ]
    }


@pytest.fixture
def four_body(example_body: dict) -> dict:
    return {
        "patients": [
            *example_body["patients"],
            {"id": "P4", "level": 2, "wait": 8, "duration": 10},
        ]
    }
