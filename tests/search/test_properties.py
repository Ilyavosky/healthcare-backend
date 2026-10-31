import pytest

from app.domain.constants import GOAL_NODE
from app.domain.goal import Goal, GoalType
from app.domain.problem import Problem, State
from app.search.engine import search
from app.search.generator import generate_patients
from app.search.heuristics import full, simple, zero


def optimum(problem: Problem) -> int:
    memo: dict[State, int] = {}

    def solve(state: State | str) -> int:
        if state == GOAL_NODE:
            return 0
        if state not in memo:
            memo[state] = min(
                cost + solve(next_state)
                for next_state, cost, _ in problem.successors(state)
            )
        return memo[state]

    return solve(problem.initial_state())


def goals_for(patients) -> list[Goal]:
    return [
        Goal(GoalType.ALL),
        Goal(GoalType.CRITICAL),
        Goal(GoalType.K, 3),
        Goal(GoalType.HORIZON, 50),
        Goal(
            GoalType.SUBSET,
            frozenset({patients[0].patient_id, patients[-1].patient_id}),
        ),
    ]


@pytest.mark.parametrize("seed", range(1, 21))
@pytest.mark.parametrize("doctors", [1, 2, 3, 4])
@pytest.mark.parametrize("critical_first", [True, False])
def test_all_algorithms_reach_brute_force_optimum(seed, doctors, critical_first):
    patients = generate_patients(7, seed)
    for goal in goals_for(patients):
        problem = Problem(
            patients, goal, doctors=doctors, critical_first=critical_first
        )
        expected = optimum(problem)
        for heuristic in (zero, simple, full):
            result = search(problem, heuristic)
            assert result.cost == expected
            assert sum(step.cost for step in result.path) == result.cost
            assert result.path[-1].to_state == GOAL_NODE


@pytest.mark.parametrize("seed", range(1, 11))
@pytest.mark.parametrize("doctors", [1, 2, 3])
def test_modified_start_reaches_optimum(seed, doctors):
    patients = generate_patients(7, seed)
    start = frozenset({patients[1].patient_id, patients[2].patient_id})
    free_at = tuple(20 + 7 * k for k in range(doctors))
    problem = Problem(
        patients,
        Goal(GoalType.ALL),
        start,
        t0=20,
        doctors=doctors,
        doctors_free_at=free_at,
    )
    expected = optimum(problem)
    assert search(problem, zero).cost == expected
    assert search(problem, full).cost == expected


@pytest.mark.parametrize("seed", range(1, 11))
@pytest.mark.parametrize("doctors", [1, 2, 3])
def test_full_heuristic_never_expands_more_than_ucs(seed, doctors):
    problem = Problem(generate_patients(9, seed), Goal(GoalType.ALL), doctors=doctors)
    assert search(problem, full).expanded <= search(problem, zero).expanded


@pytest.mark.parametrize("seed", range(1, 11))
@pytest.mark.parametrize("weight", [1.5, 2])
def test_weighted_astar_bound_on_random_rooms(seed, weight):
    problem = Problem(generate_patients(9, seed), Goal(GoalType.ALL), doctors=2)
    expected = search(problem, full).cost
    assert expected <= search(problem, full, weight=weight).cost <= weight * expected


@pytest.mark.parametrize("seed", range(1, 6))
def test_path_respects_list_scheduling(seed):
    problem = Problem(generate_patients(8, seed), Goal(GoalType.ALL), doctors=3)
    result = search(problem, full)
    starts = [step.start for step in result.path if step.patient_id is not None]
    assert starts == sorted(starts)
    assert sorted(result.order) == sorted(p.patient_id for p in problem.patients)
