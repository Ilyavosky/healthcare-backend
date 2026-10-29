import pytest

from app.domain.patient import Patient


@pytest.fixture
def p1() -> Patient:
    return Patient("P1", 2, 5, 20)


@pytest.fixture
def p2() -> Patient:
    return Patient("P2", 3, 40, 5)


@pytest.fixture
def p3() -> Patient:
    return Patient("P3", 1, 0, 30)


@pytest.fixture
def example_patients(p1: Patient, p2: Patient, p3: Patient) -> list[Patient]:
    return [p1, p2, p3]
