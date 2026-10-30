import pytest

from app.domain.constants import GOAL_NODE
from app.domain.errors import DomainError, ErrorCode
from app.domain.goal import Goal, GoalType
from app.domain.patient import Patient
from app.domain.problem import Problem, State

EMPTY = frozenset()


def s(*ids: str) -> frozenset[str]:
    return frozenset(ids)


def after(problem: Problem, *ids: str) -> State:
    state = problem.initial_state()
    for patient_id in ids:
        state = problem.assign(state, problem.patient(patient_id))
    return state


def edges_of(problem: Problem, state: State) -> dict:
    return {
        (GOAL_NODE if patient_id is None else patient_id): cost
        for _, cost, patient_id in problem.successors(state)
    }


def optimum(problem: Problem) -> int:
    best = None

    def explore(state: State, cost: int) -> None:
        nonlocal best
        for next_state, step, _ in problem.successors(state):
            if next_state == GOAL_NODE:
                total = cost + step
                best = total if best is None else min(best, total)
            else:
                explore(next_state, cost + step)

    explore(problem.initial_state(), 0)
    return best


@pytest.fixture
def problem_all(example_patients) -> Problem:
    return Problem(example_patients, Goal(GoalType.ALL), critical_first=False)


def test_initial_state_with_one_doctor(problem_all):
    assert problem_all.initial_state() == State(EMPTY, (0,))
    assert problem_all.patient("P2").level == 3
    assert [p.patient_id for p in problem_all.patients] == ["P1", "P2", "P3"]


def test_initial_state_with_several_doctors_is_sorted(example_patients):
    default = Problem(example_patients, Goal(GoalType.ALL), t0=10, doctors=2)
    custom = Problem(
        example_patients, Goal(GoalType.ALL), t0=10, doctors=2, doctors_free_at=(25, 10)
    )
    assert default.initial_state().free_at == (10, 10)
    assert custom.initial_state().free_at == (10, 25)
    assert custom.time_of(custom.initial_state()) == 10


def test_states_are_hashable_and_comparable(problem_all):
    a = after(problem_all, "P3", "P2")
    b = after(problem_all, "P2", "P3")
    assert a == b
    assert len({a, b}) == 1


def test_pending_keeps_capture_order(problem_all):
    state = after(problem_all, "P3")
    assert [p.patient_id for p in problem_all.pending(state)] == ["P1", "P2"]
    assert problem_all.pending(after(problem_all, "P1", "P2", "P3")) == []


@pytest.mark.parametrize(
    "ids, expected",
    [
        ((), 0),
        (("P1",), 20),
        (("P2",), 5),
        (("P3",), 30),
        (("P2", "P3"), 35),
        (("P1", "P2", "P3"), 55),
    ],
)
def test_time_with_one_doctor(problem_all, ids, expected):
    assert problem_all.time_of(after(problem_all, *ids)) == expected


def test_time_ignores_start_attended_durations(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL), s("P3"), 30)
    assert problem.time_of(problem.initial_state()) == 30
    assert problem.time_of(after(problem, "P2")) == 35


def test_assign_sends_patient_to_first_free_doctor(four_patients):
    problem = Problem(four_patients, Goal(GoalType.ALL), doctors=2)
    state = after(problem, "P3")
    assert state.free_at == (0, 30)
    state = problem.assign(state, problem.patient("P4"))
    assert state.free_at == (10, 30)
    assert state.attended == s("P3", "P4")


@pytest.mark.parametrize(
    "ids, expected",
    [
        ((), {"P1": 0, "P2": 0, "P3": 0}),
        (("P1",), {"P2": 0, "P3": 320}),
        (("P2",), {"P1": 0, "P3": 80}),
        (("P3",), {"P1": 200, "P2": 40}),
        (("P1", "P2"), {"P3": 400}),
        (("P1", "P3"), {"P2": 120}),
        (("P2", "P3"), {"P1": 240}),
        (("P1", "P2", "P3"), {GOAL_NODE: 0}),
    ],
)
def test_successors_match_guide_edge_table(problem_all, ids, expected):
    assert edges_of(problem_all, after(problem_all, *ids)) == expected


@pytest.mark.parametrize(
    "ids, expected",
    [
        ((), {"P3": 0}),
        (("P1",), {"P3": 320}),
        (("P2",), {"P3": 80}),
        (("P3",), {"P1": 200, "P2": 40}),
    ],
)
def test_critical_first_only_allows_level_one_while_pending(
    example_patients, ids, expected
):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    assert edges_of(problem, after(problem, *ids)) == expected


def test_two_doctors_example_path(four_patients):
    problem = Problem(four_patients, Goal(GoalType.ALL), doctors=2)
    state = problem.initial_state()
    expected = [
        ("P3", 0, (0, 30)),
        ("P4", 0, (10, 30)),
        ("P2", 0, (15, 30)),
        ("P1", 80, (30, 35)),
    ]
    total = 0
    for patient_id, cost, free_at in expected:
        step = {pid: (n, c) for n, c, pid in problem.successors(state)}
        next_state, step_cost = step[patient_id]
        assert step_cost == cost
        assert next_state.free_at == free_at
        total += step_cost
        state = next_state
    assert edges_of(problem, state) == {GOAL_NODE: 0}
    assert total == 80


@pytest.mark.parametrize(
    "patients_fixture, doctors, critical_first, expected",
    [
        ("example_patients", 1, False, 280),
        ("example_patients", 1, True, 280),
        ("four_patients", 1, False, 560),
        ("four_patients", 1, True, 624),
        ("four_patients", 2, True, 80),
        ("four_patients", 3, True, 0),
    ],
)
def test_brute_force_optimum(
    request, patients_fixture, doctors, critical_first, expected
):
    patients = request.getfixturevalue(patients_fixture)
    problem = Problem(
        patients, Goal(GoalType.ALL), doctors=doctors, critical_first=critical_first
    )
    assert optimum(problem) == expected


def test_goal_all(problem_all):
    assert not problem_all.is_goal(after(problem_all, "P1", "P2"))
    full = after(problem_all, "P1", "P2", "P3")
    assert problem_all.is_goal(full)
    assert problem_all.closing_cost(full) == 0


def test_goal_critical(example_patients):
    problem = Problem(example_patients, Goal(GoalType.CRITICAL))
    assert not problem.is_goal(after(problem, "P3"))
    state = after(problem, "P3", "P1")
    assert problem.is_goal(state)
    assert edges_of(problem, state) == {GOAL_NODE: 120}


def test_goal_k_and_closing_cost_one_doctor(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1), critical_first=False)
    state = after(problem, "P2")
    assert not problem.is_goal(problem.initial_state())
    assert problem.is_goal(state)
    assert [p.patient_id for p in problem.closing_order(state)] == ["P3", "P1"]
    assert problem.closing_cost(state) == 320
    assert edges_of(problem, state) == {GOAL_NODE: 320}


def test_closing_cost_uses_every_doctor(four_patients):
    problem = Problem(four_patients, Goal(GoalType.K, 1), doctors=2)
    state = after(problem, "P3")
    assert [p.patient_id for p in problem.closing_order(state)] == ["P4", "P1", "P2"]
    assert problem.closing_cost(state) == 80


def test_goal_k_counts_only_patients_attended_during_search(example_patients):
    problem = Problem(example_patients, Goal(GoalType.K, 1), s("P3"), 30)
    assert not problem.is_goal(problem.initial_state())
    assert problem.is_goal(after(problem, "P2"))


def test_goal_horizon_filters_successors(example_patients):
    problem = Problem(
        example_patients, Goal(GoalType.HORIZON, 30), critical_first=False
    )
    assert edges_of(problem, problem.initial_state()) == {"P1": 0, "P2": 0, "P3": 0}
    assert edges_of(problem, after(problem, "P2")) == {"P1": 0}
    state = after(problem, "P3")
    assert problem.is_goal(state)
    assert edges_of(problem, state) == {GOAL_NODE: 320}


def test_goal_horizon_with_two_doctors(four_patients):
    problem = Problem(four_patients, Goal(GoalType.HORIZON, 20), doctors=2)
    state = after(problem, "P3")
    assert state.free_at == (0, 30)
    assert set(edges_of(problem, state)) == {"P1", "P2", "P4"}
    state = after(problem, "P3", "P1")
    assert state.free_at == (20, 30)
    assert problem.is_goal(state)


def test_critical_first_skips_level_one_that_does_not_fit_horizon():
    patients = [Patient("A", 1, 0, 50), Patient("B", 3, 0, 10)]
    problem = Problem(patients, Goal(GoalType.HORIZON, 20))
    assert edges_of(problem, problem.initial_state()) == {"B": 0}


def test_fits_horizon_is_always_true_without_horizon_goal(problem_all, p3):
    assert problem_all.fits_horizon(p3, 1000)


def test_goal_subset(example_patients):
    problem = Problem(
        example_patients, Goal(GoalType.SUBSET, s("P2")), critical_first=False
    )
    assert not problem.is_goal(after(problem, "P1"))
    assert problem.is_goal(after(problem, "P2"))


def test_closing_order_breaks_level_ties_by_longer_wait():
    patients = [Patient("A", 3, 10, 5), Patient("B", 3, 50, 5), Patient("C", 1, 0, 5)]
    problem = Problem(patients, Goal(GoalType.K, 1))
    assert [p.patient_id for p in problem.closing_order(problem.initial_state())] == [
        "C",
        "B",
        "A",
    ]


def test_closing_order_keeps_capture_order_on_full_tie():
    patients = [Patient("A", 3, 10, 5), Patient("B", 3, 10, 5)]
    problem = Problem(patients, Goal(GoalType.K, 1))
    assert [p.patient_id for p in problem.closing_order(problem.initial_state())] == [
        "A",
        "B",
    ]


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


@pytest.mark.parametrize(
    "doctors, free_at, field",
    [
        (0, None, "doctors"),
        (4, None, "doctors"),
        (2, (0,), "doctors_free_at"),
        (2, (0, -5), "doctors_free_at"),
    ],
)
def test_invalid_doctors(example_patients, doctors, free_at, field):
    with pytest.raises(DomainError) as error:
        Problem(
            example_patients,
            Goal(GoalType.ALL),
            doctors=doctors,
            doctors_free_at=free_at,
        )
    assert error.value.code == ErrorCode.INVALID_DOCTORS
    assert error.value.field == field


def test_patient_arriving_after_turn_start_is_valid_once_arrived(example_patients):
    patients = [Patient("P4", 3, -20, 5)] + example_patients
    problem = Problem(patients, Goal(GoalType.ALL), EMPTY, 20)
    assert problem.patient("P4").wait_at(20) == 0


@pytest.mark.parametrize("doctors", [1, 2, 3])
@pytest.mark.parametrize("critical_first", [True, False])
@pytest.mark.parametrize(
    "goal",
    [
        Goal(GoalType.ALL),
        Goal(GoalType.CRITICAL),
        Goal(GoalType.K, 2),
        Goal(GoalType.HORIZON, 40),
        Goal(GoalType.SUBSET, frozenset({"P1"})),
    ],
)
def test_every_reachable_goal_state_only_closes(
    four_patients, goal, doctors, critical_first
):
    problem = Problem(
        four_patients, goal, doctors=doctors, critical_first=critical_first
    )
    seen = {problem.initial_state()}
    stack = [problem.initial_state()]
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
            assert len(next_state.free_at) == doctors
            if next_state not in seen:
                seen.add(next_state)
                stack.append(next_state)
