from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session, select

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


def is_trigger_complete(trigger: TriggerNode) -> bool:
    return trigger.event_action is not None and trigger.repository_full_name is not None


def is_action_complete(action: ActionNode) -> bool:
    return action.name.strip() != "" and action.playbook_id is not None


def connected_trigger(session: Session, action_id: UUID) -> TriggerNode | None:
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
    return None if edge is None else session.get(ActionNode, edge.target_id)


def flow_invalid_reason(action: ActionNode, trigger: TriggerNode | None) -> str | None:
    if not is_action_complete(action):
        return "Action is incomplete"
    if trigger is None:
        return "Action has no Trigger"
    if not is_trigger_complete(trigger):
        return "Trigger is incomplete"
    return None


def build_prompt(action: ActionNode) -> str:
    if action.playbook_id is None:
        raise ValueError("action requires a playbook")
    playbook = f"@playbook:{action.playbook_id}"
    return f"{action.prompt}\n\n{playbook}" if action.prompt.strip() else playbook


def build_automation_payload(
    action: ActionNode, trigger: TriggerNode
) -> AutomationCreate:
    if trigger.event_action is None or trigger.repository_full_name is None:
        raise ValueError("trigger is incomplete")
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
        actions=[AutomationAction(prompt=build_prompt(action))],
        run_as=AutomationRunAs(),
        metadata={METADATA_KEY: str(action.id)},
    )


def mark_pending(action: ActionNode) -> None:
    action.sync_status = "pending"


def sync_action(session: Session, client: DevinClient, action_id: UUID) -> None:
    action = session.get(ActionNode, action_id)
    if action is None:
        return
    action.updated_at = datetime.now(UTC)
    try:
        trigger = connected_trigger(session, action.id)
        complete = trigger is not None and is_trigger_complete(trigger)
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
