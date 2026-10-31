import pytest

from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem
from app.search.baseline import BaselineResult, level_order, order_cost
from app.search.engine import search
from app.search.generator import generate_patients
from app.search.heuristics import full

COUNTER_EXAMPLE = [
    Patient("P1", 3, 70, 25),
    Patient("P2", 1, 0, 5),
    Patient("P3", 2, 0, 25),
    Patient("P4", 3, 55, 5),
]


def test_example_matches_guide(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert level_order(problem) == BaselineResult(["P3", "P1", "P2"], 320)


@pytest.mark.parametrize("doctors", ["1", "2", "3"])
def test_scenario_12(scenario_12, scenario_12_patients, doctors):
    problem = Problem(scenario_12_patients, Goal(GoalType.ALL), doctors=int(doctors))
    expected = scenario_12["expected"][doctors]
    assert level_order(problem).cost == expected["baseline"]
    assert search(problem, full).cost == expected["optimal"]


def test_ties_break_by_longer_wait_then_capture(four_patients):
    problem = Problem(four_patients, Goal(GoalType.ALL), doctors=2)
    result = level_order(problem)
    assert result.order == ["P3", "P4", "P1", "P2"]
    assert result.cost == 80


def test_capture_order_tie_break_costs_184(four_patients):
    problem = Problem(four_patients, Goal(GoalType.ALL), doctors=2)
    assert order_cost(problem, ["P3", "P1", "P4", "P2"]) == 184


def test_level_order_is_not_optimal_with_two_doctors():
    problem = Problem(COUNTER_EXAMPLE, Goal(GoalType.ALL), doctors=2)
    baseline = level_order(problem)
    optimum = search(problem, full)
    assert baseline.order == ["P2", "P3", "P1", "P4"]
    assert baseline.cost == 60 + 80
    assert optimum.cost == 40
    assert optimum.order == ["P2", "P1", "P4", "P3"]


def test_order_cost_of_optimal_route(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert order_cost(problem, ["P3", "P2", "P1"]) == 280


def test_order_cost_adds_closing(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1), critical_first=False)
    assert order_cost(problem, ["P2"]) == 0 + 320


def test_order_cost_stops_at_goal(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1))
    assert order_cost(problem, ["P3", "P2", "P1"]) == order_cost(problem, ["P3"])


def test_order_cost_rejects_patient_blocked_by_n1_rule(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    with pytest.raises(DomainError) as error:
        order_cost(problem, ["P1", "P3", "P2"])
    assert error.value.code == ErrorCode.UNKNOWN_PATIENT


def test_order_cost_rejects_incomplete_order(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    with pytest.raises(DomainError) as error:
        order_cost(problem, ["P3"])
    assert error.value.field == "order"


def test_level_order_respects_horizon(example_patients):
    problem = Problem(example_patients, Goal(GoalType.HORIZON, 40))
    result = level_order(problem)
    assert result.order == ["P3", "P2"]
    assert result.cost == order_cost(problem, ["P3", "P2"])


def test_level_order_with_modified_start(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), frozenset({"P3"}), 30)
    assert level_order(problem) == BaselineResult(["P1", "P2"], 200 + 120)


@pytest.mark.parametrize("seed", range(1, 16))
@pytest.mark.parametrize("doctors", [1, 2, 3])
@pytest.mark.parametrize(
    "goal",
    [
        Goal(GoalType.ALL),
        Goal(GoalType.CRITICAL),
        Goal(GoalType.K, 3),
        Goal(GoalType.HORIZON, 60),
    ],
)
def test_baseline_is_never_better_than_optimum(seed, doctors, goal):
    problem = Problem(generate_patients(8, seed), goal, doctors=doctors)
    baseline = level_order(problem)
    assert baseline.cost >= search(problem, full).cost
    assert order_cost(problem, baseline.order) == baseline.cost
