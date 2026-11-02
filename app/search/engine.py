import heapq
import itertools
import time
from dataclasses import dataclass

from app.domain.constants import GOAL_NODE
from app.domain.problem import Problem, State
from app.search.heuristics import Heuristic, zero

Node = State | str
GOAL_DEPTH = 10**9


@dataclass(frozen=True)
class PathStep:
    from_state: State
    patient_id: str | None
    cost: int
    to_state: Node
    start: int


@dataclass(frozen=True)
class TraceChild:
    node_id: int
    patient_id: str | None
    g: int
    h: int
    f: float


@dataclass(frozen=True)
class TraceRow:
    state: Node
    g: int
    h: int
    f: float
    node_id: int = 0
    parent_id: int = -1
    patient_id: str | None = None
    children: tuple[TraceChild, ...] = ()


@dataclass(frozen=True)
class SearchResult:
    cost: int
    path: list[PathStep]
    expanded: int
    max_frontier: int
    elapsed_ms: float
    trace: list[TraceRow]
    reopened: int = 0

    @property
    def order(self) -> list[str]:
        return [step.patient_id for step in self.path if step.patient_id is not None]

    @property
    def final_state(self) -> State:
        return self.path[-1].from_state


class NoSolutionError(RuntimeError):
    pass


class SearchLimitError(RuntimeError):
    def __init__(self, expanded: int, max_frontier: int, elapsed_ms: float) -> None:
        super().__init__(
            f"Se alcanzó el límite de búsqueda tras expandir {expanded} nodos"
        )
        self.expanded = expanded
        self.max_frontier = max_frontier
        self.elapsed_ms = elapsed_ms


def search(
    problem: Problem,
    heuristic: Heuristic = zero,
    trace_limit: int = 0,
    max_expanded: int | None = None,
    time_limit_ms: float | None = None,
    weight: float = 1,
) -> SearchResult:
    started = time.perf_counter()
    counter = itertools.count()
    start = problem.initial_state()
    start_h = heuristic(problem, start)
    frontier: list[tuple[float, int, int, int, int, Node]] = [
        (weight * start_h, start_h, -_depth(start), next(counter), 0, start)
    ]
    best_g: dict[Node, int] = {start: 0}
    parent: dict[Node, tuple[State, str | None, int]] = {}
    closed: set[Node] = set()
    trace: list[TraceRow] = []
    max_frontier = 1
    expanded = 0
    reopened = 0

    origin: dict[int, tuple[int, str | None]] = {}

    while frontier:
        max_frontier = max(max_frontier, len(frontier))
        f, h, _, entry_id, g, node = heapq.heappop(frontier)
        if node in closed or g > best_g[node]:
            continue
        closed.add(node)
        expanded += 1
        tracing = len(trace) < trace_limit
        children: list[TraceChild] = []
        if node == GOAL_NODE:
            if tracing:
                trace.append(_trace_row(node, g, h, f, entry_id, origin, children))
            return SearchResult(
                cost=g,
                path=_reconstruct_path(parent, node),
                expanded=expanded,
                max_frontier=max_frontier,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                trace=trace,
                reopened=reopened,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if (max_expanded is not None and expanded >= max_expanded) or (
            time_limit_ms is not None and elapsed_ms >= time_limit_ms
        ):
            raise SearchLimitError(expanded, max_frontier, elapsed_ms)
        for next_node, step_cost, patient_id in problem.iter_successors(node):
            if time_limit_ms is not None:
                elapsed_ms = (time.perf_counter() - started) * 1000
                if elapsed_ms >= time_limit_ms:
                    raise SearchLimitError(expanded, max_frontier, elapsed_ms)
            new_g = g + step_cost
            if new_g >= best_g.get(next_node, new_g + 1):
                continue
            if next_node in closed:
                closed.discard(next_node)
                reopened += 1
            best_g[next_node] = new_g
            parent[next_node] = (node, patient_id, step_cost)
            new_h = heuristic(problem, next_node)
            child_id = next(counter)
            new_f = new_g + weight * new_h
            if tracing:
                origin[child_id] = (entry_id, patient_id)
                children.append(TraceChild(child_id, patient_id, new_g, new_h, new_f))
            heapq.heappush(
                frontier,
                (new_f, new_h, -_depth(next_node), child_id, new_g, next_node),
            )
        if tracing:
            trace.append(_trace_row(node, g, h, f, entry_id, origin, children))

    raise NoSolutionError("La búsqueda terminó sin llegar a la meta")


def _trace_row(
    node: Node,
    g: int,
    h: int,
    f: float,
    entry_id: int,
    origin: dict[int, tuple[int, str | None]],
    children: list[TraceChild],
) -> TraceRow:
    parent_id, patient_id = origin.get(entry_id, (-1, None))
    return TraceRow(node, g, h, f, entry_id, parent_id, patient_id, tuple(children))


def _depth(node: Node) -> int:
    return len(node.attended) if isinstance(node, State) else GOAL_DEPTH


def _reconstruct_path(
    parent: dict[Node, tuple[State, str | None, int]], goal: Node
) -> list[PathStep]:
    path: list[PathStep] = []
    node = goal
    while node in parent:
        previous, patient_id, cost = parent[node]
        path.append(PathStep(previous, patient_id, cost, node, previous.next_start))
        node = previous
    path.reverse()
    return path
