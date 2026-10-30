import heapq
import itertools
import time
from dataclasses import dataclass

from app.domain.constants import GOAL_NODE
from app.domain.problem import Problem, State
from app.search.heuristics import Heuristic, zero

Node = State | str


@dataclass(frozen=True)
class PathStep:
    from_state: State
    patient_id: str | None
    cost: int
    to_state: Node
    start: int


@dataclass(frozen=True)
class TraceRow:
    state: Node
    g: int
    h: int
    f: int


@dataclass(frozen=True)
class SearchResult:
    cost: int
    path: list[PathStep]
    expanded: int
    max_frontier: int
    elapsed_ms: float
    trace: list[TraceRow]

    @property
    def order(self) -> list[str]:
        return [step.patient_id for step in self.path if step.patient_id is not None]

    @property
    def final_state(self) -> State:
        return self.path[-1].from_state


class NoSolutionError(RuntimeError):
    pass


def search(
    problem: Problem,
    heuristic: Heuristic = zero,
    trace_limit: int = 0,
) -> SearchResult:
    started = time.perf_counter()
    counter = itertools.count()
    start = problem.initial_state()
    frontier: list[tuple[int, int, int, Node]] = [
        (heuristic(problem, start), next(counter), 0, start)
    ]
    best_g: dict[Node, int] = {start: 0}
    parent: dict[Node, tuple[State, str | None, int]] = {}
    closed: set[Node] = set()
    trace: list[TraceRow] = []
    max_frontier = 1

    while frontier:
        max_frontier = max(max_frontier, len(frontier))
        f, _, g, node = heapq.heappop(frontier)
        if node in closed:
            continue
        closed.add(node)
        if len(trace) < trace_limit:
            trace.append(TraceRow(node, g, f - g, f))
        if node == GOAL_NODE:
            return SearchResult(
                cost=g,
                path=_reconstruct_path(parent, node),
                expanded=len(closed),
                max_frontier=max_frontier,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                trace=trace,
            )
        for next_node, step_cost, patient_id in problem.successors(node):
            new_g = g + step_cost
            if next_node in closed or new_g >= best_g.get(next_node, new_g + 1):
                continue
            best_g[next_node] = new_g
            parent[next_node] = (node, patient_id, step_cost)
            new_f = new_g + heuristic(problem, next_node)
            heapq.heappush(frontier, (new_f, next(counter), new_g, next_node))

    raise NoSolutionError("La búsqueda terminó sin llegar a la meta")


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
