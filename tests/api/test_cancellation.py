import asyncio
import threading
import time
from functools import partial

import pytest

from app.api.routers.solve import run_until_disconnected
from app.domain.goal import Goal, GoalType
from app.domain.problem import Problem
from app.search.engine import SearchCancelledError, search
from app.search.generator import generate_patients
from app.search.heuristics import AlgorithmName
from app.services.solve_service import solve


class DisconnectedRequest:
    async def is_disconnected(self) -> bool:
        return True


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def large_problem() -> Problem:
    return Problem(generate_patients(40, 7), Goal(GoalType.ALL), doctors=2)


def test_should_stop_cancels_the_search(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    with pytest.raises(SearchCancelledError):
        search(problem, should_stop=lambda: True)


def test_solve_propagates_cancellation(example_patients):
    problem = Problem(example_patients, Goal(GoalType.ALL))
    with pytest.raises(SearchCancelledError):
        solve(problem, should_stop=lambda: True)


def test_disconnected_client_stops_an_unbounded_search():
    cancelled = threading.Event()
    work = partial(
        solve,
        large_problem(),
        [AlgorithmName.UCS],
        time_limit_ms=None,
        should_stop=cancelled.is_set,
    )
    started = time.perf_counter()
    with pytest.raises(SearchCancelledError):
        asyncio.run(run_until_disconnected(DisconnectedRequest(), work, cancelled))
    assert cancelled.is_set()
    assert time.perf_counter() - started < 3


def test_connected_client_gets_the_result(example_patients):
    cancelled = threading.Event()
    problem = Problem(example_patients, Goal(GoalType.ALL))
    work = partial(solve, problem, should_stop=cancelled.is_set)
    outcome = asyncio.run(run_until_disconnected(ConnectedRequest(), work, cancelled))
    assert outcome.cost == 280
    assert not cancelled.is_set()
