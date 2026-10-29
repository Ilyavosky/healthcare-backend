from dataclasses import FrozenInstanceError

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.domain.patient import Patient


@pytest.mark.parametrize(
    "level, weight, limit",
    [(1, 16, 0), (2, 8, 10), (3, 4, 60), (4, 2, 120), (5, 1, 240)],
)
def test_weight_and_limit_follow_triage_table(level, weight, limit):
    patient = Patient("X", level, 0, 10)
    assert patient.weight == weight
    assert patient.limit == limit


def test_example_patients_weight_and_limit(p1, p2, p3):
    assert (p1.weight, p1.limit) == (8, 10)
    assert (p2.weight, p2.limit) == (4, 60)
    assert (p3.weight, p3.limit) == (16, 0)


def test_wait_at_adds_turn_minutes(p2):
    assert p2.wait_at(0) == 40
    assert p2.wait_at(30) == 70


def test_wait_at_supports_patient_arriving_after_turn_start():
    patient = Patient("X", 3, -10, 15)
    assert patient.wait_at(10) == 0
    assert patient.wait_at(25) == 15


@pytest.mark.parametrize("t, expected", [(0, 0), (19, 0), (20, 0), (21, 1), (30, 10)])
def test_delay_at_is_never_negative(p2, t, expected):
    assert p2.delay_at(t) == expected


@pytest.mark.parametrize(
    "patient_fixture, t, expected",
    [
        ("p2", 30, 40),
        ("p3", 5, 80),
        ("p3", 0, 0),
        ("p1", 35, 240),
        ("p1", 0, 0),
        ("p1", 5, 0),
    ],
)
def test_penalty_at_matches_guide_examples(request, patient_fixture, t, expected):
    patient = request.getfixturevalue(patient_fixture)
    assert patient.penalty_at(t) == expected


def test_penalty_is_weight_times_delay(example_patients):
    for patient in example_patients:
        for t in range(0, 120, 7):
            assert patient.penalty_at(t) == patient.weight * patient.delay_at(t)


@pytest.mark.parametrize(
    "patient_fixture, t, expected",
    [
        ("p2", 19, False),
        ("p2", 20, True),
        ("p2", 30, True),
        ("p1", 4, False),
        ("p1", 5, True),
        ("p1", 35, True),
        ("p3", 0, True),
        ("p3", 5, True),
    ],
)
def test_is_late_at_before_at_and_after_limit(request, patient_fixture, t, expected):
    patient = request.getfixturevalue(patient_fixture)
    assert patient.is_late_at(t) is expected


def test_late_with_zero_penalty_exactly_at_limit(p1):
    assert p1.is_late_at(5) is True
    assert p1.penalty_at(5) == 0


@pytest.mark.parametrize("level", [0, 6, -1, 10])
def test_invalid_level_is_rejected(level):
    with pytest.raises(DomainError) as error:
        Patient("X", level, 0, 10)
    assert error.value.code == ErrorCode.INVALID_PATIENT
    assert error.value.field == "level"


@pytest.mark.parametrize("duration", [0, -5])
def test_non_positive_duration_is_rejected(duration):
    with pytest.raises(DomainError) as error:
        Patient("X", 3, 0, duration)
    assert error.value.code == ErrorCode.INVALID_PATIENT
    assert error.value.field == "duration"


def test_domain_error_is_a_value_error():
    with pytest.raises(ValueError):
        Patient("X", 0, 0, 10)


def test_patient_is_immutable(p1):
    with pytest.raises(FrozenInstanceError):
        p1.level = 3


def test_patients_with_same_data_are_equal_and_hashable():
    a = Patient("P1", 2, 5, 20)
    b = Patient("P1", 2, 5, 20)
    assert a == b
    assert len({a, b}) == 1
