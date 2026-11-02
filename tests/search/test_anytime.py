import pytest

from app.domain.goal import Goal, GoalType
from app.domain.problem import Problem
from app.search.anytime import best_completion, complete_order
from app.search.baseline import level_key, order_cost
from app.search.engine import SearchLimitError, search
from app.search.heuristics import full, simple, zero
from tests.search.test_engine import random_patients

GOALS = [
    Goal(GoalType.ALL),
    Goal(GoalType.CRITICAL),
    Goal(GoalType.K, 3),
    Goal(GoalType.HORIZON, 40),
]


def stopped(problem: Problem, heuristic, max_expanded: int) -> SearchLimitError:
    with pytest.raises(SearchLimitError) as error:
        search(problem, heuristic, trace_limit=1000, max_expanded=max_expanded)
    return error.value


def test_completion_from_the_start_is_the_baseline_order(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert complete_order(problem, problem.initial_state()) == ["P3", "P1", "P2"]


@pytest.mark.parametrize("seed", range(1, 9))
@pytest.mark.parametrize("goal", GOALS)
def test_completion_matches_greedy_triage_from_any_state(seed, goal):
    problem = Problem(random_patients(seed, 8), goal, doctors=2)
    state = problem.initial_state()
    while not problem.is_goal(state):
        expected = []
        current = state
        while not problem.is_goal(current):
            patient = min(
                problem.candidates(current), key=lambda p: level_key(problem, p)
            )
            expected.append(patient.patient_id)
            current = problem.assign(current, patient)
        assert complete_order(problem, state) == expected
        state = problem.assign(state, problem.candidates(state)[-1])


@pytest.mark.parametrize("seed", range(1, 13))
@pytest.mark.parametrize("doctors", [1, 2, 3])
@pytest.mark.parametrize("goal", GOALS)
@pytest.mark.parametrize("heuristic", [zero, simple, full])
def test_lower_bound_and_completion_bracket_the_optimum(seed, doctors, goal, heuristic):
    problem = Problem(random_patients(seed, 7), goal, doctors=doctors)
    optimum = search(problem, full)
    if optimum.expanded <= 3:
        return
    error = stopped(problem, heuristic, max(2, optimum.expanded // 3))
    assert error.lower_bound <= optimum.cost
    assert error.best_nodes
    anytime = best_completion(problem, error.best_nodes, error.lower_bound)
    assert anytime.lower_bound <= optimum.cost <= anytime.cost
    order = [step.patient_id for step in anytime.schedule.steps]
    assert order_cost(problem, order) == anytime.cost


@pytest.mark.parametrize("seed", range(1, 8))
def test_best_nodes_follow_their_traced_parents(seed):
    problem = Problem(random_patients(seed, 10), Goal(GoalType.ALL), doctors=2)
    error = stopped(problem, zero, 12)
    rows = {row.node_id: row for row in error.trace}
    children = {
        child.node_id: (row.node_id, child.patient_id)
        for row in error.trace
        for child in row.children
    }
    for node in error.best_nodes:
        order = []
        node_id = node.node_id
        while node_id in children:
            parent_id, patient_id = children[node_id]
            order.append(patient_id)
            node_id = parent_id
        assert node_id in rows
        assert list(reversed(order)) == node.order


def test_lower_bound_counts_an_interrupted_expansion(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), critical_first=False)
    with pytest.raises(SearchLimitError) as error:
        search(problem, full, time_limit_ms=0)
    assert error.value.lower_bound == full(problem, problem.initial_state())
    assert [node.order for node in error.value.best_nodes] == [[]]
