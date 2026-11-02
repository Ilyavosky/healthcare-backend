from dataclasses import dataclass

from app.domain.problem import Problem, State
from app.search.baseline import level_order
from app.search.engine import FrontierNode
from app.search.report import Schedule, build_schedule


@dataclass(frozen=True)
class AnytimeResult:
    node_id: int
    search_steps: int
    lower_bound: int
    schedule: Schedule

    @property
    def cost(self) -> int:
        return self.schedule.cost


def complete_order(problem: Problem, state: State) -> list[str]:
    return level_order(problem, state).order


def best_completion(
    problem: Problem, nodes: list[FrontierNode], lower_bound: float
) -> AnytimeResult | None:
    best: AnytimeResult | None = None
    for node in nodes:
        order = node.order + complete_order(problem, node.state)
        schedule = build_schedule(problem, order)
        if best is None or schedule.cost < best.cost:
            best = AnytimeResult(
                node_id=node.node_id,
                search_steps=len(node.order),
                lower_bound=int(-(-lower_bound // 1)),
                schedule=schedule,
            )
    return best
