import pytest

from app.domain.goal import Goal, GoalType
from app.domain.problem import Problem
from app.search.generator import generate_patients
from app.search.heuristics import AlgorithmName
from app.services.solve_service import DEFAULT_ALGORITHMS, solve


def test_default_runs_ucs_and_astar(example_patients):
    outcome = solve(Problem(example_patients, Goal(GoalType.ALL)))
    assert list(outcome.runs) == list(DEFAULT_ALGORITHMS)
    assert outcome.same_cost is True
    assert outcome.reference == AlgorithmName.ASTAR
    assert outcome.cost == 280
    assert outcome.baseline.cost == 320
    assert outcome.baseline_gap_pct == 14.29
    assert outcome.reduction_pct == {AlgorithmName.ASTAR: 16.67}


def test_all_three_algorithms(scenario_12_patients):
    problem = Problem(scenario_12_patients, Goal(GoalType.ALL), doctors=2)
    outcome = solve(problem, list(AlgorithmName))
    costs = {name: run.result.cost for name, run in outcome.runs.items()}
    assert costs == dict.fromkeys(AlgorithmName, 1938)
    assert outcome.baseline.cost == 2112
    ucs = outcome.runs[AlgorithmName.UCS].result.expanded
    astar = outcome.runs[AlgorithmName.ASTAR].result.expanded
    assert outcome.reduction_pct[AlgorithmName.ASTAR] == round(
        100 * (1 - astar / ucs), 2
    )


def test_duplicates_and_empty_list(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert list(solve(problem, [AlgorithmName.UCS, AlgorithmName.UCS]).runs) == [
        AlgorithmName.UCS
    ]
    assert list(solve(problem, []).runs) == list(DEFAULT_ALGORITHMS)


def test_single_algorithm_has_no_same_cost(example_patients):
    outcome = solve(Problem(example_patients, Goal(GoalType.ALL)), [AlgorithmName.UCS])
    assert outcome.same_cost is None
    assert outcome.reference == AlgorithmName.UCS
    assert outcome.reduction_pct == {}


def test_trace_only_when_requested(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert solve(problem).runs[AlgorithmName.ASTAR].result.trace == []
    traced = solve(problem, include_trace=True, trace_limit=3)
    assert len(traced.runs[AlgorithmName.ASTAR].result.trace) == 3


def test_schedule_alerts_and_left_out(example_patients):
    outcome = solve(Problem(example_patients, Goal(GoalType.K, 1)))
    assert [s.patient_id for s in outcome.schedule.steps] == ["P3"]
    assert [s.patient_id for s in outcome.schedule.left_out] == ["P1", "P2"]
    assert any(a.code == "LEFT_OUT_CRITICAL" for a in outcome.alerts)


def test_time_limit_falls_back_to_weighted_astar():
    problem = Problem(generate_patients(24, 7), Goal(GoalType.ALL), doctors=2)
    outcome = solve(
        problem,
        [AlgorithmName.ASTAR],
        time_limit_ms=300,
        fallback_weights=(1.5, 3, 10),
    )
    run = outcome.runs[AlgorithmName.ASTAR]
    assert run.finished
    assert run.weight > 1
    assert not run.optimal
    assert run.limits[0].weight == 1
    assert outcome.same_cost is None
    assert outcome.baseline_gap_pct is None
    assert outcome.cost <= outcome.baseline.cost


def test_ucs_has_no_fallback():
    problem = Problem(generate_patients(24, 7), Goal(GoalType.ALL), doctors=2)
    outcome = solve(
        problem, [AlgorithmName.UCS], time_limit_ms=50, fallback_weights=(2,)
    )
    run = outcome.runs[AlgorithmName.UCS]
    assert not run.finished
    assert [limit.weight for limit in run.limits] == [1]
    assert outcome.reference is None
    assert outcome.schedule == outcome.baseline_schedule
    assert outcome.cost == outcome.baseline.cost


@pytest.mark.parametrize("seed", range(1, 6))
def test_outcome_cost_matches_reference(seed):
    problem = Problem(generate_patients(9, seed), Goal(GoalType.ALL), doctors=2)
    outcome = solve(problem, list(AlgorithmName))
    assert outcome.cost == outcome.runs[outcome.reference].result.cost
    assert outcome.cost <= outcome.baseline.cost
