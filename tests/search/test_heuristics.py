import pytest

from app.domain.constants import GOAL_NODE
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem, State
from app.search.engine import search
from app.search.heuristics import (
    HEURISTICS,
    AlgorithmName,
    full,
    minimum_extra_wait,
    simple,
    zero,
)
from tests.search.test_engine import SCENARIO_12, random_patients

GOALS = [
    Goal(GoalType.ALL),
    Goal(GoalType.CRITICAL),
    Goal(GoalType.K, 2),
    Goal(GoalType.HORIZON, 45),
    Goal(GoalType.SUBSET, frozenset({"P1", "P4"})),
]


def cost_to_go(problem: Problem) -> dict[State, int]:
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

    solve(problem.initial_state())
    return memo


def state(*ids: str, free_at: tuple[int, ...]) -> State:
    return State(frozenset(ids), free_at)


def test_registry_maps_each_algorithm():
    assert HEURISTICS == {
        AlgorithmName.UCS: zero,
        AlgorithmName.ASTAR_SIMPLE: simple,
        AlgorithmName.ASTAR: full,
    }
    assert [a.value for a in AlgorithmName] == ["ucs", "astar_simple", "astar"]


@pytest.mark.parametrize("heuristic", [zero, simple, full])
def test_goal_node_is_zero(example_patients, heuristic):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert heuristic(problem, GOAL_NODE) == 0


@pytest.mark.parametrize(
    "ids, t, expected_simple, expected_full",
    [
        ((), 0, 0, 0),
        (("P1",), 20, 320, 340),
        (("P2",), 5, 80, 240),
        (("P3",), 30, 240, 260),
        (("P1", "P2"), 25, 400, 400),
        (("P1", "P3"), 50, 120, 120),
        (("P2", "P3"), 35, 240, 240),
        (("P1", "P2", "P3"), 55, 0, 0),
    ],
)
def test_one_doctor_table_matches_guide(
    example_patients, ids, t, expected_simple, expected_full
):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    current = state(*ids, free_at=(t,))
    assert simple(problem, current) == expected_simple
    assert full(problem, current) == expected_full


def test_full_worked_example(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    current = state("P3", free_at=(30,))
    assert simple(problem, current) == 200 + 40
    assert full(problem, current) == 200 + 40 + 4 * 5


def test_full_with_two_doctors_uses_second_doctor_free_time(four_patients):
    problem = Problem(four_patients, Goal(GoalType.ALL), doctors=2)
    current = state("P3", free_at=(20, 25))
    late = [p.patient_id for p in problem.pending(current) if p.is_late_at(20)]
    assert late == ["P1", "P2", "P4"]
    assert simple(problem, current) == 8 * 15 + 0 + 8 * 18
    assert full(problem, current) == 8 * 15 + 0 + 8 * 18 + 8 * 5 + 4 * 5


def test_minimum_extra_wait_positions():
    current = state(free_at=(10, 12, 40))
    sums = [0, 5, 12, 20, 30]
    assert minimum_extra_wait(current, 10, 0, 3, sums) == 0
    assert minimum_extra_wait(current, 10, 1, 3, sums) == 2
    assert minimum_extra_wait(current, 10, 2, 3, sums) == 5
    assert minimum_extra_wait(current, 10, 3, 3, sums) == 5
    assert minimum_extra_wait(current, 10, 6, 3, sums) == 12


def test_one_doctor_extra_wait_is_sum_of_shortest():
    current = state(free_at=(0,))
    sums = [0, 5, 12, 20]
    assert [minimum_extra_wait(current, 0, k, 1, sums) for k in range(4)] == [
        0,
        5,
        12,
        20,
    ]


def test_no_late_patients_gives_base():
    patients = [Patient("A", 5, 0, 10), Patient("B", 4, 0, 10)]
    problem = Problem(patients, Goal(GoalType.ALL))
    assert full(problem, problem.initial_state()) == 0


@pytest.mark.parametrize("seed", range(1, 13))
@pytest.mark.parametrize("doctors", [1, 2, 3, 5])
@pytest.mark.parametrize("critical_first", [True, False])
@pytest.mark.parametrize("goal", GOALS)
def test_heuristics_are_admissible_and_ordered(seed, doctors, critical_first, goal):
    problem = Problem(
        random_patients(seed, 6),
        goal,
        doctors=doctors,
        critical_first=critical_first,
    )
    for current, remaining in cost_to_go(problem).items():
        assert 0 <= simple(problem, current) <= full(problem, current) <= remaining


@pytest.mark.parametrize("seed", range(1, 13))
@pytest.mark.parametrize("goal", GOALS)
def test_heuristics_are_consistent_with_one_doctor(seed, goal):
    problem = Problem(random_patients(seed, 6), goal, critical_first=False)
    for current in cost_to_go(problem):
        for next_state, cost, _ in problem.successors(current):
            for heuristic in (simple, full):
                assert heuristic(problem, current) <= cost + heuristic(
                    problem, next_state
                )


def test_astar_example_matches_guide(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), critical_first=False)
    result = search(problem, full, trace_limit=20)
    assert result.cost == 280
    assert result.order == ["P3", "P2", "P1"]
    assert result.expanded == 6
    assert [row.f for row in result.trace] == [0, 240, 260, 280, 280, 280]
    assert [row.h for row in result.trace] == [0, 240, 260, 240, 0, 0]


def test_astar_never_expands_starting_with_p1(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), critical_first=False)
    result = search(problem, full, trace_limit=20)
    expanded = [row.state for row in result.trace]
    assert State(frozenset({"P1"}), (20,)) not in expanded


@pytest.mark.parametrize(
    "doctors, critical_first, expected",
    [(1, False, 560), (1, True, 624), (2, True, 80), (3, True, 0)],
)
def test_astar_four_patients(four_patients, doctors, critical_first, expected):
    problem = Problem(
        four_patients,
        Goal(GoalType.ALL),
        doctors=doctors,
        critical_first=critical_first,
    )
    assert search(problem, full).cost == expected


@pytest.mark.parametrize(
    "doctors, expected_cost, ucs_expanded, astar_expanded",
    [(1, 4893, 2050, 470), (2, 1938, 18967, 3318), (3, 979, 64247, 1836)],
)
def test_scenario_12_astar_expands_less(
    doctors, expected_cost, ucs_expanded, astar_expanded
):
    patients = [Patient(*row) for row in SCENARIO_12]
    problem = Problem(patients, Goal(GoalType.ALL), doctors=doctors)
    ucs = search(problem, zero)
    astar_simple = search(problem, simple)
    astar = search(problem, full)
    assert ucs.cost == astar_simple.cost == astar.cost == expected_cost
    assert ucs.expanded == ucs_expanded
    assert astar.expanded == astar_expanded
    assert astar.expanded < astar_simple.expanded < ucs.expanded


def test_inconsistent_transitions_are_reopened_without_losing_optimum():
    patients = [Patient(*row) for row in SCENARIO_12]
    problem = Problem(patients, Goal(GoalType.ALL), doctors=2)
    result = search(problem, full)
    assert result.reopened > 0
    assert result.cost == search(problem, zero).cost


@pytest.mark.parametrize("weight", [1.5, 2, 3])
@pytest.mark.parametrize("doctors", [1, 2, 3])
def test_weighted_astar_stays_within_bound(weight, doctors):
    patients = [Patient(*row) for row in SCENARIO_12]
    problem = Problem(patients, Goal(GoalType.ALL), doctors=doctors)
    optimum = search(problem, full).cost
    weighted = search(problem, full, weight=weight)
    assert optimum <= weighted.cost <= weight * optimum
    assert weighted.expanded <= search(problem, full).expanded


def test_weight_one_is_plain_astar(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    plain = search(problem, full)
    weighted = search(problem, full, weight=1)
    assert (plain.cost, plain.expanded) == (weighted.cost, weighted.expanded)
