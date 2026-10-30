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


@pytest.fixture
def p4() -> Patient:
    return Patient("P4", 2, 8, 10)


@pytest.fixture
def four_patients(example_patients: list[Patient], p4: Patient) -> list[Patient]:
    return [*example_patients, p4]
