import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from app.domain.problem import Problem
from app.search.anytime import AnytimeResult, best_completion
from app.search.baseline import BaselineResult, level_order
from app.search.engine import (
    FrontierNode,
    SearchLimitError,
    SearchResult,
    TraceRow,
    search,
)
from app.search.heuristics import HEURISTICS, AlgorithmName
from app.search.report import (
    Alert,
    Schedule,
    baseline_gap_pct,
    build_alerts,
    build_schedule,
    reduction_pct,
)

DEFAULT_ALGORITHMS: tuple[AlgorithmName, ...] = (AlgorithmName.UCS, AlgorithmName.ASTAR)
WEIGHTED_ALGORITHMS: frozenset[AlgorithmName] = frozenset(
    {AlgorithmName.ASTAR, AlgorithmName.ASTAR_SIMPLE}
)


@dataclass(frozen=True)
class LimitReached:
    weight: float
    expanded: int
    max_frontier: int
    elapsed_ms: float


@dataclass(frozen=True)
class AlgorithmRun:
    name: AlgorithmName
    result: SearchResult | None
    schedule: Schedule | None
    weight: float = 1
    limits: list[LimitReached] = field(default_factory=list)
    anytime: AnytimeResult | None = None
    partial_trace: list[TraceRow] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.result is not None

    @property
    def optimal(self) -> bool:
        return self.finished and self.weight == 1


@dataclass(frozen=True)
class SolveOutcome:
    runs: dict[AlgorithmName, AlgorithmRun]
    baseline: BaselineResult
    baseline_schedule: Schedule
    reference: AlgorithmName | None
    reference_kind: str
    schedule: Schedule
    alerts: list[Alert]
    same_cost: bool | None
    reduction_pct: dict[AlgorithmName, float]
    baseline_gap_pct: float | None

    @property
    def cost(self) -> int:
        return self.schedule.cost


def solve(
    problem: Problem,
    algorithms: list[AlgorithmName] | tuple[AlgorithmName, ...] = DEFAULT_ALGORITHMS,
    include_trace: bool = False,
    trace_limit: int = 500,
    time_limit_ms: float | None = None,
    fallback_weights: tuple[float, ...] = (),
    should_stop: Callable[[], bool] | None = None,
) -> SolveOutcome:
    names = list(dict.fromkeys(algorithms)) or list(DEFAULT_ALGORITHMS)
    runs = {
        name: _run(
            problem,
            name,
            trace_limit if include_trace else 0,
            time_limit_ms,
            fallback_weights if name in WEIGHTED_ALGORITHMS else (),
            should_stop,
        )
        for name in names
    }
    baseline = level_order(problem)
    baseline_schedule = build_schedule(problem, baseline.order)
    reference = _reference(runs)
    if (
        reference is not None
        and not runs[reference].optimal
        and baseline.cost < runs[reference].result.cost
    ):
        reference = None
    reference_kind = "baseline"
    schedule = baseline_schedule
    if reference is not None:
        reference_kind = "optimal" if runs[reference].optimal else "approximate"
        schedule = runs[reference].schedule
    else:
        anytime = _best_anytime(runs)
        if anytime is not None and runs[anytime].anytime.cost < baseline.cost:
            reference = anytime
            reference_kind = "anytime"
            schedule = runs[anytime].anytime.schedule
    optimal_costs = {run.result.cost for run in runs.values() if run.optimal}
    optimal_runs = [run for run in runs.values() if run.optimal]
    return SolveOutcome(
        runs=runs,
        baseline=baseline,
        baseline_schedule=baseline_schedule,
        reference=reference,
        reference_kind=reference_kind,
        schedule=schedule,
        alerts=build_alerts(problem, schedule),
        same_cost=len(optimal_costs) == 1 if len(optimal_runs) > 1 else None,
        reduction_pct=_reductions(runs),
        baseline_gap_pct=(
            baseline_gap_pct(baseline.cost, min(optimal_costs))
            if optimal_costs
            else None
        ),
    )


def _run(
    problem: Problem,
    name: AlgorithmName,
    trace_limit: int,
    time_limit_ms: float | None,
    fallback_weights: tuple[float, ...],
    should_stop: Callable[[], bool] | None = None,
) -> AlgorithmRun:
    limits = []
    lower_bound = 0
    partial_trace: list[TraceRow] = []
    candidates: list[FrontierNode] = []
    weights = (1, *fallback_weights)
    started = time.perf_counter()
    for attempt, weight in enumerate(weights):
        try:
            result = search(
                problem,
                HEURISTICS[name],
                trace_limit=trace_limit,
                time_limit_ms=_attempt_budget(
                    time_limit_ms, started, attempt, len(weights)
                ),
                weight=weight,
                should_stop=should_stop,
            )
        except SearchLimitError as error:
            limits.append(
                LimitReached(
                    weight, error.expanded, error.max_frontier, error.elapsed_ms
                )
            )
            if attempt == 0:
                partial_trace = error.trace
                candidates.extend(error.best_nodes)
            else:
                candidates.extend(_untraced(error.best_nodes))
            if error.lower_bound is not None:
                lower_bound = max(lower_bound, error.lower_bound)
            continue
        schedule = build_schedule(problem, result.order)
        return AlgorithmRun(name, result, schedule, weight, limits)
    return AlgorithmRun(
        name,
        None,
        None,
        limits[-1].weight,
        limits,
        anytime=best_completion(problem, candidates, lower_bound),
        partial_trace=partial_trace,
    )


def _untraced(nodes: list[FrontierNode]) -> list[FrontierNode]:
    return [replace(node, node_id=-1) for node in nodes]


def _best_anytime(runs: dict[AlgorithmName, AlgorithmRun]) -> AlgorithmName | None:
    candidates = [run for run in runs.values() if run.anytime is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda run: run.anytime.cost).name


def _attempt_budget(
    total_ms: float | None, started: float, attempt: int, attempts: int
) -> float | None:
    if total_ms is None:
        return None
    remaining = total_ms - (time.perf_counter() - started) * 1000
    if attempt < attempts - 1:
        remaining /= 2
    return max(remaining, 1.0)


def _reference(runs: dict[AlgorithmName, AlgorithmRun]) -> AlgorithmName | None:
    finished = [run for run in runs.values() if run.finished]
    if not finished:
        return None
    best = min(finished, key=lambda run: (not run.optimal, run.result.cost))
    if runs.get(AlgorithmName.ASTAR) and runs[AlgorithmName.ASTAR].finished:
        astar = runs[AlgorithmName.ASTAR]
        if astar.result.cost == best.result.cost and astar.optimal == best.optimal:
            return AlgorithmName.ASTAR
    return best.name


def _reductions(runs: dict[AlgorithmName, AlgorithmRun]) -> dict[AlgorithmName, float]:
    ucs = runs.get(AlgorithmName.UCS)
    if ucs is None or not ucs.finished:
        return {}
    return {
        name: reduction_pct(ucs.result.expanded, run.result.expanded)
        for name, run in runs.items()
        if name != AlgorithmName.UCS and run.finished
    }
