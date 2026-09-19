import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, col, select

from devin_flow.devin import DevinClient
from devin_flow.devin.client import (
    AutomationAction,
    AutomationCondition,
    AutomationConditionGroup,
    AutomationConditions,
    AutomationCreate,
    AutomationRunAs,
    AutomationTrigger,
    AutomationUpdate,
    DevinNotConfiguredError,
    DevinUpstreamError,
)
from devin_flow.models import ActionNode, Edge, TriggerNode

METADATA_KEY = "devin_flow_action_id"

logger = logging.getLogger(__name__)


def is_trigger_complete(trigger: TriggerNode) -> bool:
    return trigger.event_action is not None and trigger.repository_full_name is not None


def is_action_complete(action: ActionNode) -> bool:
    return action.name.strip() != "" and action.playbook_id is not None


def connected_trigger(session: Session, action_id: UUID) -> TriggerNode | None:
    action = session.get(ActionNode, action_id)
    if action is None or action.deleted_at is not None:
        return None
    edge = session.exec(
        select(Edge).where(
            Edge.target_id == action_id,
            Edge.source_kind == "trigger",
        )
    ).first()
    return None if edge is None else session.get(TriggerNode, edge.source_id)


def connected_action(session: Session, trigger_id: UUID) -> ActionNode | None:
    edge = session.exec(
        select(Edge).where(
            Edge.source_id == trigger_id,
            Edge.target_kind == "action",
        )
    ).first()
    action = None if edge is None else session.get(ActionNode, edge.target_id)
    return None if action is None or action.deleted_at is not None else action


def flow_invalid_reason(action: ActionNode, trigger: TriggerNode | None) -> str | None:
    if not is_action_complete(action):
        return "Action is incomplete"
    if trigger is None:
        return "Action has no Trigger"
    if not is_trigger_complete(trigger):
        return "Trigger is incomplete"
    return None


def build_prompt(prompt: str, playbook_id: str) -> str:
    playbook = f"@playbook:{playbook_id}"
    return f"{prompt}\n\n{playbook}" if prompt.strip() else playbook


def build_automation_payload(
    action: ActionNode, trigger: TriggerNode
) -> AutomationCreate:
    if not (is_action_complete(action) and is_trigger_complete(trigger)):
        raise ValueError("action or trigger is incomplete")
    assert action.playbook_id is not None
    assert trigger.event_action is not None
    assert trigger.repository_full_name is not None
    return AutomationCreate(
        name=(
            f"{action.name}: {trigger.repository_full_name} "
            f"issue {trigger.event_action}"
        ),
        enabled=action.enabled,
        triggers=[
            AutomationTrigger(
                event_type="github:issues",
                conditions=AutomationConditions(
                    any=[
                        AutomationConditionGroup(
                            all=[
                                AutomationCondition(
                                    field="action",
                                    value=trigger.event_action,
                                ),
                                AutomationCondition(
                                    field="repository.full_name",
                                    value=trigger.repository_full_name,
                                ),
                            ]
                        )
                    ]
                ),
            )
        ],
        actions=[
            AutomationAction(prompt=build_prompt(action.prompt, action.playbook_id))
        ],
        run_as=AutomationRunAs(),
        metadata={METADATA_KEY: str(action.id)},
    )


def mark_pending(action: ActionNode) -> None:
    action.sync_status = "pending"


def sync_action(session: Session, client: DevinClient, action_id: UUID) -> None:
    action = session.exec(
        select(ActionNode).where(ActionNode.id == action_id).with_for_update()
    ).first()
    if action is None:
        return
    action.updated_at = datetime.now(UTC)
    try:
        trigger = connected_trigger(session, action.id)
        complete = (
            trigger is not None
            and is_trigger_complete(trigger)
            and is_action_complete(action)
        )
        if not complete and action.automation_id is None:
            action.sync_status = "unprovisioned"
            action.sync_error = None
        elif not complete:
            assert action.automation_id is not None
            client.update_automation(
                action.automation_id,
                AutomationUpdate(enabled=False),
            )
            action.sync_status = "disabled"
            action.sync_error = None
        else:
            assert trigger is not None
            payload = build_automation_payload(action, trigger)
            update = AutomationUpdate(
                name=payload.name,
                enabled=payload.enabled,
                triggers=payload.triggers,
                actions=payload.actions,
                metadata=payload.metadata,
            )
            if action.automation_id is not None:
                automation = client.update_automation(action.automation_id, update)
            else:
                found = client.list_automations({METADATA_KEY: str(action.id)})
                if found:
                    automation = client.update_automation(
                        found[0].automation_id, update
                    )
                else:
                    automation = client.create_automation(payload)
            action.automation_id = automation.automation_id
            action.sync_status = "enabled" if payload.enabled else "disabled"
            action.sync_error = None
    except DevinUpstreamError as exc:
        action.sync_status = "error"
        action.sync_error = exc.detail
    except DevinNotConfiguredError:
        action.sync_status = "error"
        action.sync_error = "devin api not configured"
    finally:
        session.add(action)
        session.commit()


def actions_to_sync(session: Session) -> Sequence[ActionNode]:
    # tombstoned Actions are retried only while an Automation still needs
    # disabling
    return session.exec(
        select(ActionNode)
        .where(
            col(ActionNode.sync_status).in_(["pending", "error"]),
            (col(ActionNode.deleted_at).is_(None))
            | (col(ActionNode.automation_id).is_not(None)),
        )
        .order_by(col(ActionNode.updated_at))
    ).all()


def retry_syncs(session: Session, client: DevinClient) -> int:
    # one attempt per Action per cycle; one failure must not stop the rest
    actions = actions_to_sync(session)
    for action in actions:
        try:
            sync_action(session, client, action.id)
        except Exception:
            logger.exception("sync of action %s failed", action.id)
            session.rollback()
    return len(actions)
