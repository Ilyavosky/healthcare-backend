from dataclasses import dataclass, field

from app.domain.problem import Problem
from app.search.baseline import BaselineResult, level_order
from app.search.engine import SearchLimitError, SearchResult, search
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
) -> SolveOutcome:
    names = list(dict.fromkeys(algorithms)) or list(DEFAULT_ALGORITHMS)
    runs = {
        name: _run(
            problem,
            name,
            trace_limit if include_trace else 0,
            time_limit_ms,
            fallback_weights if name in WEIGHTED_ALGORITHMS else (),
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
    schedule = runs[reference].schedule if reference is not None else baseline_schedule
    optimal_costs = {run.result.cost for run in runs.values() if run.optimal}
    optimal_runs = [run for run in runs.values() if run.optimal]
    return SolveOutcome(
        runs=runs,
        baseline=baseline,
        baseline_schedule=baseline_schedule,
        reference=reference,
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
) -> AlgorithmRun:
    limits = []
    for weight in (1, *fallback_weights):
        try:
            result = search(
                problem,
                HEURISTICS[name],
                trace_limit=trace_limit,
                time_limit_ms=time_limit_ms,
                weight=weight,
            )
        except SearchLimitError as error:
            limits.append(
                LimitReached(
                    weight, error.expanded, error.max_frontier, error.elapsed_ms
                )
            )
            continue
        schedule = build_schedule(problem, result.order)
        return AlgorithmRun(name, result, schedule, weight, limits)
    return AlgorithmRun(name, None, None, limits[-1].weight, limits)


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
