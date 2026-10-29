import pytest

from app.domain.constants import GOAL_NODE
from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem

EMPTY = frozenset()


def s(*ids: str) -> frozenset[str]:
    return frozenset(ids)


def edges_of(problem: Problem, state: frozenset[str]) -> dict:
    return {
        (GOAL_NODE if patient_id is None else patient_id): cost
        for _, cost, patient_id in problem.successors(state)
    }


@pytest.fixture
def problem_all(example_patients) -> Problem:
    return Problem(example_patients, Goal(GoalType.ALL))


def test_initial_state_and_lookup(problem_all):
    assert problem_all.initial_state() == EMPTY
    assert problem_all.patient("P2").level == 3
    assert [p.patient_id for p in problem_all.patients] == ["P1", "P2", "P3"]


def test_pending_keeps_capture_order(problem_all):
    assert [p.patient_id for p in problem_all.pending(s("P3"))] == ["P1", "P2"]
    assert problem_all.pending(s("P1", "P2", "P3")) == []


@pytest.mark.parametrize(
    "state, expected",
    [
        (EMPTY, 0),
        (s("P1"), 20),
        (s("P2"), 5),
        (s("P3"), 30),
        (s("P2", "P3"), 35),
        (s("P1", "P2", "P3"), 55),
    ],
)
def test_time_of(problem_all, state, expected):
    assert problem_all.time_of(state) == expected


def test_time_of_ignores_start_attended_durations(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), s("P3"), 30)
    assert problem.time_of(s("P3")) == 30
    assert problem.time_of(s("P2", "P3")) == 35


def test_time_of_uses_cache(problem_all):
    problem_all.time_of(s("P3"))
    problem_all.time_of(s("P3"))
    assert problem_all._time_cache == {s("P3"): 30}


@pytest.mark.parametrize(
    "state, expected",
    [
        (EMPTY, {"P1": 0, "P2": 0, "P3": 0}),
        (s("P1"), {"P2": 0, "P3": 320}),
        (s("P2"), {"P1": 0, "P3": 80}),
        (s("P3"), {"P1": 200, "P2": 40}),
        (s("P1", "P2"), {"P3": 400}),
        (s("P1", "P3"), {"P2": 120}),
        (s("P2", "P3"), {"P1": 240}),
        (s("P1", "P2", "P3"), {GOAL_NODE: 0}),
    ],
)
def test_successors_match_guide_edge_table(problem_all, state, expected):
    assert edges_of(problem_all, state) == expected


def test_successor_states_add_one_patient(problem_all):
    next_states = {next_state for next_state, _, _ in problem_all.successors(s("P3"))}
    assert next_states == {s("P1", "P3"), s("P2", "P3")}


def test_goal_all(problem_all):
    assert not problem_all.is_goal(s("P1", "P2"))
    assert problem_all.is_goal(s("P1", "P2", "P3"))
    assert problem_all.closing_cost(s("P1", "P2", "P3")) == 0


def test_goal_critical(example_patients):
    problem = Problem(example_patients, Goal(GoalType.CRITICAL))
    assert not problem.is_goal(s("P3"))
    assert problem.is_goal(s("P1", "P3"))
    assert edges_of(problem, s("P1", "P3")) == {GOAL_NODE: 120}


def test_goal_k_and_closing_cost(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1))
    assert not problem.is_goal(EMPTY)
    assert problem.is_goal(s("P2"))
    assert [p.patient_id for p in problem.closing_order(s("P2"))] == ["P3", "P1"]
    assert problem.closing_cost(s("P2")) == 320
    assert edges_of(problem, s("P2")) == {GOAL_NODE: 320}


def test_goal_k_counts_only_patients_attended_during_search(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1), s("P3"), 30)
    assert not problem.is_goal(s("P3"))
    assert problem.is_goal(s("P2", "P3"))


def test_goal_horizon_filters_successors(example_patients):
    problem = Problem(example_patients, Goal(GoalType.HORIZON, 30))
    assert edges_of(problem, EMPTY) == {"P1": 0, "P2": 0, "P3": 0}
    assert edges_of(problem, s("P2")) == {"P1": 0}
    assert problem.is_goal(s("P3"))
    assert edges_of(problem, s("P3")) == {GOAL_NODE: 320}


def test_fits_horizon_is_always_true_without_horizon_goal(problem_all, p3):
    assert problem_all.fits_horizon(p3, 1000)


def test_goal_subset(example_patients):
    problem = Problem(example_patients, Goal(GoalType.SUBSET, s("P2")))
    assert not problem.is_goal(s("P1"))
    assert problem.is_goal(s("P2"))


def test_closing_order_breaks_level_ties_by_longer_wait():
    patients = [Patient("A", 3, 10, 5), Patient("B", 3, 50, 5), Patient("C", 1, 0, 5)]
    problem = Problem(patients, Goal(GoalType.K, 1))
    assert [p.patient_id for p in problem.closing_order(EMPTY)] == ["C", "B", "A"]


def test_closing_order_keeps_capture_order_on_full_tie():
    patients = [Patient("A", 3, 10, 5), Patient("B", 3, 10, 5)]
    problem = Problem(patients, Goal(GoalType.K, 1))
    assert [p.patient_id for p in problem.closing_order(EMPTY)] == ["A", "B"]


@pytest.mark.parametrize(
    "patients_factory, goal, start, t0, code, field",
    [
        (
            lambda ps: ps * 6,
            Goal(GoalType.ALL),
            EMPTY,
            0,
            ErrorCode.TOO_MANY_PATIENTS,
            "patients",
        ),
        (
            lambda ps: ps + [Patient("P1", 3, 0, 5)],
            Goal(GoalType.ALL),
            EMPTY,
            0,
            ErrorCode.DUPLICATE_PATIENT_ID,
            "patients",
        ),
        (
            lambda ps: ps,
            Goal(GoalType.ALL),
            s("P9"),
            0,
            ErrorCode.UNKNOWN_PATIENT,
            "start.attended",
        ),
        (
            lambda ps: ps,
            Goal(GoalType.SUBSET, s("P9")),
            EMPTY,
            0,
            ErrorCode.UNKNOWN_PATIENT,
            "goal.value",
        ),
        (
            lambda ps: ps,
            Goal(GoalType.ALL),
            s("P1", "P2", "P3"),
            0,
            ErrorCode.NO_PENDING_PATIENTS,
            "start.attended",
        ),
        (
            lambda ps: ps,
            Goal(GoalType.K, 3),
            s("P3"),
            30,
            ErrorCode.INVALID_GOAL_VALUE,
            "goal.value",
        ),
        (
            lambda ps: [Patient("P4", 3, -20, 5)] + ps,
            Goal(GoalType.ALL),
            EMPTY,
            10,
            ErrorCode.PATIENT_NOT_ARRIVED,
            "patients",
        ),
    ],
)
def test_constructor_validations(
    example_patients, patients_factory, goal, start, t0, code, field
):
    with pytest.raises(DomainError) as error:
        Problem(patients_factory(example_patients), goal, start, t0)
    assert error.value.code == code
    assert error.value.field == field


def test_patient_arriving_after_turn_start_is_valid_once_arrived(example_patients):
    patients = [Patient("P4", 3, -20, 5)] + example_patients
    problem = Problem(patients, Goal(GoalType.ALL), EMPTY, 20)
    assert problem.patient("P4").wait_at(20) == 0


@pytest.mark.parametrize(
    "goal",
    [
        Goal(GoalType.ALL),
        Goal(GoalType.CRITICAL),
        Goal(GoalType.K, 2),
        Goal(GoalType.HORIZON, 40),
        Goal(GoalType.SUBSET, s("P1")),
    ],
)
def test_every_reachable_goal_state_only_closes(example_patients, goal):
    problem = Problem(example_patients, goal)
    seen = {EMPTY}
    stack = [EMPTY]
    while stack:
        state = stack.pop()
        successors = problem.successors(state)
        assert successors
        if problem.is_goal(state):
            assert len(successors) == 1
            assert successors[0][0] == GOAL_NODE
            assert successors[0][2] is None
            continue
        for next_state, cost, _ in successors:
            assert cost >= 0
            if next_state not in seen:
                seen.add(next_state)
                stack.append(next_state)
