from itertools import pairwise

import pytest

from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem
from app.search.baseline import level_order
from app.search.engine import search
from app.search.generator import generate_patients
from app.search.heuristics import full
from app.search.report import (
    Alert,
    AlertCode,
    ScheduleStep,
    baseline_gap_pct,
    build_alerts,
    build_schedule,
    doctor_loads,
    reduction_pct,
)


def schedule_for(problem: Problem):
    return build_schedule(problem, search(problem, full).order)


def row(step: ScheduleStep) -> tuple:
    return (
        step.patient_id,
        step.doctor,
        step.start,
        step.end,
        step.delay,
        step.penalty,
    )


def test_example_matches_guide(example_patients):
    schedule = schedule_for(Problem(example_patients, Goal(GoalType.ALL)))
    assert [row(s) for s in schedule.steps] == [
        ("P3", 1, 0, 30, 0, 0),
        ("P2", 1, 30, 35, 10, 40),
        ("P1", 1, 35, 55, 30, 240),
    ]
    assert schedule.left_out == []
    assert schedule.cost == 280


def test_two_doctors(four_patients):
    schedule = schedule_for(Problem(four_patients, Goal(GoalType.ALL), doctors=2))
    assert [row(s) for s in schedule.steps] == [
        ("P3", 1, 0, 30, 0, 0),
        ("P4", 2, 0, 10, 0, 0),
        ("P1", 2, 10, 30, 5, 40),
        ("P2", 1, 30, 35, 10, 40),
    ]
    assert doctor_loads(schedule) == {1: ["P3", "P2"], 2: ["P4", "P1"]}


def test_doctor_numbers_follow_input_order(four_patients):
    problem = Problem(
        four_patients,
        Goal(GoalType.ALL),
        t0=10,
        doctors=2,
        doctors_free_at=(40, 10),
    )
    schedule = schedule_for(problem)
    assert row(schedule.steps[0]) == ("P3", 2, 10, 40, 10, 160)
    assert schedule.cost == search(problem, full).cost


def test_idle_doctors_are_never_used(example_patients):
    schedule = schedule_for(Problem(example_patients, Goal(GoalType.ALL), doctors=6))
    assert {s.doctor for s in schedule.steps} == {1, 2, 3}
    assert all(s.start == 0 for s in schedule.steps)


def test_left_out_follow_closing_order(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1))
    schedule = schedule_for(problem)
    assert [row(s) for s in schedule.steps] == [("P3", 1, 0, 30, 0, 0)]
    assert [row(s) for s in schedule.left_out] == [
        ("P1", 1, 30, 50, 25, 200),
        ("P2", 1, 50, 55, 30, 120),
    ]
    assert all(s.after_goal for s in schedule.left_out)
    assert schedule.cost == 320


@pytest.mark.parametrize("seed", range(1, 16))
@pytest.mark.parametrize("doctors", [1, 2, 3, 5])
@pytest.mark.parametrize(
    "goal",
    [
        Goal(GoalType.ALL),
        Goal(GoalType.CRITICAL),
        Goal(GoalType.K, 2),
        Goal(GoalType.HORIZON, 45),
        Goal(GoalType.SUBSET, frozenset({"P2", "P5"})),
    ],
)
def test_schedule_cost_equals_search_cost(seed, doctors, goal):
    problem = Problem(generate_patients(8, seed), goal, doctors=doctors)
    result = search(problem, full)
    schedule = build_schedule(problem, result.order)
    assert schedule.cost == result.cost
    assert len(schedule.all_steps) == len(problem.patients)
    baseline = level_order(problem)
    assert build_schedule(problem, baseline.order).cost == baseline.cost
    for doctor in range(1, doctors + 1):
        mine = [s for s in schedule.all_steps if s.doctor == doctor]
        for previous, current in pairwise(mine):
            assert previous.end <= current.start


def test_alerts_for_example(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    alerts = build_alerts(problem, schedule_for(problem))
    assert alerts == [
        Alert("P3", AlertCode.NEAR_LIMIT, 0),
        Alert("P2", AlertCode.EXCEEDS_LIMIT, 10),
        Alert("P1", AlertCode.EXCEEDS_LIMIT, 30),
    ]


def test_alerts_already_late_and_left_out(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1), t0=10)
    alerts = build_alerts(problem, schedule_for(problem))
    assert Alert("P3", AlertCode.ALREADY_LATE, 10) in alerts
    assert Alert("P1", AlertCode.ALREADY_LATE, 5) in alerts
    assert Alert("P1", AlertCode.LEFT_OUT_CRITICAL, 35) in alerts
    assert Alert("P2", AlertCode.LEFT_OUT, 40) in alerts
    assert Alert("P1", AlertCode.LEFT_OUT, 35) not in alerts


def test_near_limit_uses_margin():
    patients = [Patient("A", 3, 55, 10), Patient("B", 3, 0, 10)]
    problem = Problem(patients, Goal(GoalType.ALL))
    schedule = schedule_for(problem)
    assert Alert("A", AlertCode.NEAR_LIMIT, 5) in build_alerts(problem, schedule)
    assert build_alerts(problem, schedule, margin=4) == []


def test_already_attended_are_not_alerted(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), frozenset({"P1"}), 40)
    alerts = build_alerts(problem, schedule_for(problem))
    assert all(alert.patient_id != "P1" for alert in alerts)


@pytest.mark.parametrize(
    "ucs, other, expected", [(100, 25, 75.0), (9, 6, 33.33), (10, 10, 0.0), (0, 0, 0.0)]
)
def test_reduction_pct(ucs, other, expected):
    assert reduction_pct(ucs, other) == expected


@pytest.mark.parametrize(
    "baseline, optimum, expected",
    [(320, 280, 14.29), (140, 40, 250.0), (80, 80, 0.0), (0, 0, 0.0), (5, 0, None)],
)
def test_baseline_gap_pct(baseline, optimum, expected):
    assert baseline_gap_pct(baseline, optimum) == expected
