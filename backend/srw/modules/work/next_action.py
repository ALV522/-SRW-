from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Protocol


class JudgmentLike(Protocol):
    criterion_key: str
    status: str
    reason: str
    gap: str


class WorkItemLike(Protocol):
    id: str
    type: str
    priority: int
    reason: str
    criterion_key: str | None
    state: str
    created_at: object


class NextActionType(StrEnum):
    RESOLVE_CONFLICT = "RESOLVE_CONFLICT"
    VERIFY_CRITERION = "VERIFY_CRITERION"
    RUN_SCREEN = "RUN_SCREEN"
    PREPARE_INTERVIEW = "PREPARE_INTERVIEW"
    REVIEW_REEVALUATION = "REVIEW_REEVALUATION"
    MAKE_DECISION = "MAKE_DECISION"
    WAIT_FOR_INPUT = "WAIT_FOR_INPUT"


@dataclass(frozen=True, slots=True)
class NextAction:
    type: NextActionType
    reason: str
    criterion_key: str | None = None
    work_item_id: str | None = None


_WORK_PRIORITY: tuple[NextActionType, ...] = (
    NextActionType.RESOLVE_CONFLICT,
    NextActionType.VERIFY_CRITERION,
    NextActionType.RUN_SCREEN,
    NextActionType.PREPARE_INTERVIEW,
    NextActionType.REVIEW_REEVALUATION,
)
_WORK_RANK = {item.value: rank for rank, item in enumerate(_WORK_PRIORITY)}


def choose_next_action(
    judgments: Iterable[JudgmentLike],
    work_items: Iterable[WorkItemLike],
    decision_ready: bool,
) -> NextAction:
    judgment_rows = list(judgments)
    conflicts = sorted(
        (row for row in judgment_rows if row.status == "conflict"),
        key=lambda row: row.criterion_key,
    )
    if conflicts:
        row = conflicts[0]
        return NextAction(
            type=NextActionType.RESOLVE_CONFLICT,
            reason=row.gap or row.reason or "存在矛盾，需要先解决",
            criterion_key=row.criterion_key,
        )

    open_items = [row for row in work_items if row.state in {"open", "in_progress"}]
    if open_items:
        row = min(
            open_items,
            key=lambda item: (
                _WORK_RANK.get(item.type, len(_WORK_RANK)),
                item.priority,
                str(item.created_at),
                item.id,
            ),
        )
        try:
            action_type = NextActionType(row.type)
        except ValueError:
            action_type = NextActionType.WAIT_FOR_INPUT
        return NextAction(
            type=action_type,
            reason=row.reason or "存在待处理事项",
            criterion_key=row.criterion_key,
            work_item_id=row.id,
        )

    partial = sorted(
        (row for row in judgment_rows if row.status in {"partial", "missing"}),
        key=lambda row: row.criterion_key,
    )
    if partial:
        row = partial[0]
        return NextAction(
            type=NextActionType.VERIFY_CRITERION,
            reason=row.gap or row.reason or "仍需核实",
            criterion_key=row.criterion_key,
        )

    if decision_ready:
        return NextAction(type=NextActionType.MAKE_DECISION, reason="当前判断信息已满足决策条件")
    return NextAction(type=NextActionType.WAIT_FOR_INPUT, reason="等待新的材料或人工输入")
