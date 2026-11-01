import time

import pytest

from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem
from app.search.baseline import level_order, order_cost
from app.search.engine import SearchLimitError, search
from app.search.generator import generate_patients
from app.search.heuristics import full, simple
from app.search.report import build_schedule


def reference_level_order(problem: Problem) -> tuple[list[str], int]:
    state = problem.initial_state()
    order, total = [], 0
    while not problem.is_goal(state):
        chosen = min(
            problem.candidates(state),
            key=lambda p: (p.level, -p.wait, problem.capture_index[p.patient_id]),
        )
        total += chosen.penalty_at(state.next_start)
        state = problem.assign(state, chosen)
        order.append(chosen.patient_id)
    return order, total + problem.closing_cost(state)


def reference_full(problem: Problem, state) -> int:
    pending = problem.pending(state)
    if not pending:
        return 0
    t = problem.time_of(state)
    base = sum(p.penalty_at(t) for p in pending)
    late = sorted((p.weight for p in pending if p.is_late_at(t)), reverse=True)
    durations = sorted(p.duration for p in pending)
    sums = [0]
    for d in durations:
        sums.append(sums[-1] + d)
    doctors = len(state.free_at)
    extra = 0
    for k, w in enumerate(late):
        wait = min(state.free_at[k] - t, sums[1]) if k < doctors else sums[k // doctors]
        extra += w * wait
    return base + extra


GOALS = [
    Goal(GoalType.ALL),
    Goal(GoalType.CRITICAL),
    Goal(GoalType.K, 3),
    Goal(GoalType.HORIZON, 40),
    Goal(GoalType.HORIZON, 5),
    Goal(GoalType.SUBSET, frozenset({"P2", "P7"})),
]


@pytest.mark.parametrize("seed", range(1, 26))
@pytest.mark.parametrize("doctors", [1, 2, 4])
@pytest.mark.parametrize("goal", GOALS)
def test_fast_baseline_equals_reference(seed, doctors, goal):
    problem = Problem(
        generate_patients(9, seed),
        goal,
        frozenset({"P1"}) if seed % 3 == 0 else frozenset(),
        t0=seed % 20,
        doctors=doctors,
        critical_first=seed % 2 == 0,
    )
    order, cost = reference_level_order(problem)
    assert level_order(problem).order == order
    assert level_order(problem).cost == cost == order_cost(problem, order)


@pytest.mark.parametrize("seed", range(1, 31))
@pytest.mark.parametrize("doctors", [1, 2, 3, 6])
def test_fast_heuristic_equals_reference(seed, doctors):
    problem = Problem(
        generate_patients(8, seed),
        Goal(GoalType.ALL),
        t0=seed % 15,
        doctors=doctors,
        doctors_free_at=tuple(seed % 15 + (seed * i) % 25 for i in range(doctors)),
    )
    stack, seen = [problem.initial_state()], set()
    while stack and len(seen) < 400:
        state = stack.pop()
        if state in seen:
            continue
        seen.add(state)
        assert full(problem, state) == reference_full(problem, state)
        assert simple(problem, state) == sum(
            p.penalty_at(state.next_start) for p in problem.pending(state)
        )
        stack.extend(s for s, _, _ in problem.successors(state) if s != "META")


@pytest.mark.parametrize("seed", range(1, 21))
@pytest.mark.parametrize("extra", [0, 1, 3])
def test_order_pruning_keeps_the_optimum(seed, extra, monkeypatch):
    patients = generate_patients(6, seed)
    problem = Problem(
        patients, Goal(GoalType.ALL), doctors=6 + extra, critical_first=seed % 2 == 0
    )
    pruned = search(problem, full)
    monkeypatch.setattr(Problem, "order_is_irrelevant", lambda self, state: False)
    unpruned = search(problem, full)
    assert pruned.cost == unpruned.cost
    assert pruned.expanded <= unpruned.expanded


def test_huge_doctor_count_is_not_materialized():
    started = time.perf_counter()
    problem = Problem(generate_patients(5, 1), Goal(GoalType.ALL), doctors=10**12)
    assert problem.initial_state().free_at == (0, 0, 0, 0, 0)
    assert search(problem, full).expanded == 7
    assert time.perf_counter() - started < 1


def test_large_baseline_and_schedule_are_fast():
    patients = generate_patients(20000, 4)
    problem = Problem(patients, Goal(GoalType.ALL), doctors=7)
    started = time.perf_counter()
    baseline = level_order(problem)
    schedule = build_schedule(problem, baseline.order)
    assert time.perf_counter() - started < 3
    assert schedule.cost == baseline.cost
    assert len(schedule.steps) == 20000


def test_time_limit_is_checked_inside_an_expansion():
    patients = [Patient(f"P{i}", 3, 100, 5 + i % 7) for i in range(4000)]
    problem = Problem(patients, Goal(GoalType.ALL), doctors=2)
    started = time.perf_counter()
    with pytest.raises(SearchLimitError):
        search(problem, full, time_limit_ms=150)
    assert time.perf_counter() - started < 1.5


@pytest.mark.parametrize("n", [200, 500, 1000])
def test_plateau_scales_linearly(n):
    problem = Problem(generate_patients(n, 6), Goal(GoalType.ALL), doctors=n)
    started = time.perf_counter()
    result = search(problem, full)
    assert result.expanded == n + 2
    assert time.perf_counter() - started < 5
