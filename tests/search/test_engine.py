import random

import pytest

from app.domain.constants import GOAL_NODE
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem, State
from app.search.engine import (
    NoSolutionError,
    SearchLimitError,
    SearchResult,
    search,
)
from app.search.heuristics import HEURISTICS, AlgorithmName, zero

SCENARIO_12 = [
    ("P1", 2, 5, 18),
    ("P2", 2, 8, 21),
    ("P3", 3, 13, 18),
    ("P4", 2, 25, 23),
    ("P5", 1, 3, 30),
    ("P6", 3, 49, 19),
    ("P7", 5, 190, 10),
    ("P8", 4, 115, 6),
    ("P9", 4, 106, 15),
    ("P10", 2, 12, 31),
    ("P11", 3, 41, 15),
    ("P12", 3, 41, 25),
]


def brute_force(problem: Problem) -> int:
    best = None

    def explore(state: State, cost: int) -> None:
        nonlocal best
        if best is not None and cost >= best:
            return
        for next_state, step, _ in problem.successors(state):
            if next_state == GOAL_NODE:
                total = cost + step
                best = total if best is None else min(best, total)
            else:
                explore(next_state, cost + step)

    explore(problem.initial_state(), 0)
    return best


def random_patients(seed: int, n: int) -> list[Patient]:
    rng = random.Random(seed)
    patients = []
    for i in range(1, n + 1):
        level = rng.choice([1, 2, 2, 3, 3, 3, 4, 4, 5])
        wait = rng.randint(0, 120)
        duration = rng.randint(5, 35)
        patients.append(Patient(f"P{i}", level, wait, duration))
    return patients


def assert_path_is_consistent(problem: Problem, result: SearchResult) -> None:
    assert result.path[0].from_state == problem.initial_state()
    assert result.path[-1].to_state == GOAL_NODE
    assert result.path[-1].patient_id is None
    for previous, current in zip(result.path, result.path[1:]):
        assert previous.to_state == current.from_state
    assert sum(step.cost for step in result.path) == result.cost
    for step in result.path:
        assert step.start == step.from_state.next_start


def test_registry_has_ucs():
    assert HEURISTICS[AlgorithmName.UCS] is zero
    assert AlgorithmName.UCS.value == "ucs"


def test_ucs_example_matches_guide(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), critical_first=False)
    result = search(problem, trace_limit=20)
    assert result.cost == 280
    assert result.order == ["P3", "P2", "P1"]
    assert result.expanded == 9
    assert [row.g for row in result.trace] == [0, 0, 0, 0, 0, 40, 200, 280, 280]
    assert result.trace[-1].state == GOAL_NODE
    assert all(row.h == 0 for row in result.trace)
    assert_path_is_consistent(problem, result)


def test_ucs_with_critical_first_expands_less(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    result = search(problem)
    assert result.cost == 280
    assert result.order == ["P3", "P2", "P1"]
    assert result.expanded == 6


def test_ucs_with_modified_start(example_patients):
    problem = Problem(
        example_patients,
        Goal(GoalType.ALL),
        frozenset({"P3"}),
        30,
        critical_first=False,
    )
    result = search(problem)
    assert result.cost == 280
    assert result.order == ["P2", "P1"]
    assert result.expanded == 5
    assert result.path[0].start == 30


def test_ucs_two_doctors_example(four_patients):
    problem = Problem(four_patients, Goal(GoalType.ALL), doctors=2)
    result = search(problem)
    assert result.cost == 80
    assert result.order == ["P3", "P4", "P2", "P1"]
    assert [step.start for step in result.path[:-1]] == [0, 0, 10, 15]
    assert result.final_state.free_at == (30, 35)
    assert_path_is_consistent(problem, result)


def test_ucs_k_goal_includes_closing_cost(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1), critical_first=False)
    result = search(problem)
    assert result.cost == 320
    assert len(result.order) == 1
    assert result.path[-1].cost == result.cost - sum(s.cost for s in result.path[:-1])


def test_trace_is_limited(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), critical_first=False)
    assert search(problem).trace == []
    assert len(search(problem, trace_limit=3).trace) == 3


def test_metrics_are_reported(example_patients):
    result = search(Problem(example_patients, Goal(GoalType.ALL)))
    assert result.max_frontier >= 1
    assert result.elapsed_ms >= 0


def test_search_uses_given_heuristic(example_patients):
    calls = []

    def spy(problem, state):
        calls.append(state)
        return 0

    result = search(Problem(example_patients, Goal(GoalType.ALL)), spy)
    assert result.cost == 280
    assert calls


def test_no_solution_raises(example_patients, monkeypatch):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    monkeypatch.setattr(problem, "successors", lambda state: [])
    with pytest.raises(NoSolutionError):
        search(problem)


def test_expansion_limit_stops_search(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), critical_first=False)
    with pytest.raises(SearchLimitError) as error:
        search(problem, max_expanded=4)
    assert error.value.expanded == 4
    assert error.value.max_frontier >= 1


def test_expansion_limit_not_reached_returns_solution(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), critical_first=False)
    assert search(problem, max_expanded=9).cost == 280


def test_time_limit_stops_search(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    with pytest.raises(SearchLimitError):
        search(problem, time_limit_ms=0)


def test_no_limits_by_default(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert search(problem).cost == 280


@pytest.mark.parametrize("extra", [1, 5, 40])
@pytest.mark.parametrize("seed", range(1, 6))
def test_more_doctors_than_patients_equals_one_doctor_each(seed, extra):
    patients = random_patients(seed, 5)
    exact = search(Problem(patients, Goal(GoalType.ALL), doctors=5))
    many = search(Problem(patients, Goal(GoalType.ALL), doctors=5 + extra))
    assert many.cost == exact.cost
    assert many.expanded == exact.expanded


def test_more_doctors_than_patients_costs_only_current_delay(example_patients):
    result = search(Problem(example_patients, Goal(GoalType.ALL), doctors=10))
    expected = sum(p.penalty_at(0) for p in example_patients)
    assert result.cost == expected


def test_large_room_is_accepted_and_limit_keeps_it_bounded():
    patients = random_patients(99, 60)
    problem = Problem(patients, Goal(GoalType.ALL), doctors=8)
    with pytest.raises(SearchLimitError) as error:
        search(problem, max_expanded=2000)
    assert error.value.expanded == 2000


@pytest.mark.parametrize("seed", range(1, 16))
@pytest.mark.parametrize("doctors", [1, 2, 3])
@pytest.mark.parametrize("critical_first", [True, False])
@pytest.mark.parametrize(
    "goal",
    [
        Goal(GoalType.ALL),
        Goal(GoalType.CRITICAL),
        Goal(GoalType.K, 3),
        Goal(GoalType.HORIZON, 45),
        Goal(GoalType.SUBSET, frozenset({"P1", "P4"})),
    ],
    ids=["all", "critical", "k3", "horizon45", "subset"],
)
def test_ucs_matches_brute_force(seed, doctors, critical_first, goal):
    problem = Problem(
        random_patients(seed, 6), goal, doctors=doctors, critical_first=critical_first
    )
    result = search(problem)
    assert result.cost == brute_force(problem)
    assert_path_is_consistent(problem, result)


@pytest.mark.parametrize(
    "doctors, critical_first, expected_cost",
    [(1, False, 4893), (1, True, 4893), (2, True, 1938)],
)
def test_scenario_12_regression(doctors, critical_first, expected_cost):
    patients = [Patient(*row) for row in SCENARIO_12]
    problem = Problem(
        patients, Goal(GoalType.ALL), doctors=doctors, critical_first=critical_first
    )
    result = search(problem)
    assert result.cost == expected_cost
    assert len(result.order) == 12
