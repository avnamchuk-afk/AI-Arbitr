from dataclasses import dataclass
from enum import Enum


class ContractStage(str, Enum):
    DRAFT = "draft"
    READY_TO_INVITE = "ready_to_invite"
    AWAITING_COUNTERPARTY = "awaiting_counterparty"
    AWAITING_CREATOR = "awaiting_creator"
    ACTIVE = "active"
    DISPUTE = "dispute"
    COMPLETED = "completed"
    DELETED = "deleted"


class ContractAction(str, Enum):
    GENERATE_CONTRACT = "generate_contract"
    ASK_QUESTION = "ask_question"
    ADD_TERM = "add_term"
    CREATE_VERSION = "create_version"
    SEND_INVITE = "send_invite"
    SIGN_COUNTERPARTY = "sign_counterparty"
    REQUEST_CHANGES = "request_changes"
    SIGN_CREATOR = "sign_creator"
    OPEN_DISPUTE = "open_dispute"
    RESPOND_TO_DISPUTE = "respond_to_dispute"
    CONFIRM_COMPLETION = "confirm_completion"
    DOWNLOAD_CERTIFICATE = "download_certificate"
    DELETE_CONTRACT = "delete_contract"


@dataclass(frozen=True)
class WorkflowContext:
    has_version: bool = False
    invite_sent: bool = False
    party_1_approved: bool = False
    party_2_approved: bool = False
    finalized: bool = False
    dispute_opened: bool = False
    completed: bool = False
    deleted: bool = False


STAGE_LABELS = {
    ContractStage.DRAFT: "Черновик",
    ContractStage.READY_TO_INVITE: "Версия готова к согласованию",
    ContractStage.AWAITING_COUNTERPARTY: "Ожидается подпись второй стороны",
    ContractStage.AWAITING_CREATOR: "Ожидается подпись создателя",
    ContractStage.ACTIVE: "Договор действует",
    ContractStage.DISPUTE: "Открыт спор",
    ContractStage.COMPLETED: "Договор исполнен",
    ContractStage.DELETED: "Удален",
}

ACTION_LABELS = {
    ContractAction.GENERATE_CONTRACT: "Составить договор",
    ContractAction.ASK_QUESTION: "Задать вопрос",
    ContractAction.ADD_TERM: "Добавить условие",
    ContractAction.CREATE_VERSION: "Сохранить версию",
    ContractAction.SEND_INVITE: "Направить на согласование",
    ContractAction.SIGN_COUNTERPARTY: "Подписать",
    ContractAction.REQUEST_CHANGES: "Предложить изменения",
    ContractAction.SIGN_CREATOR: "Подписать со своей стороны",
    ContractAction.OPEN_DISPUTE: "Открыть спор",
    ContractAction.RESPOND_TO_DISPUTE: "Ответить по спору",
    ContractAction.CONFIRM_COMPLETION: "Договор исполнен",
    ContractAction.DOWNLOAD_CERTIFICATE: "Скачать справку",
    ContractAction.DELETE_CONTRACT: "Удалить",
}

STAGE_ACTIONS = {
    ContractStage.DRAFT: {
        "party_1": (
            ContractAction.GENERATE_CONTRACT,
            ContractAction.CREATE_VERSION,
            ContractAction.DELETE_CONTRACT,
        ),
        "party_2": (),
    },
    ContractStage.READY_TO_INVITE: {
        "party_1": (
            ContractAction.ASK_QUESTION,
            ContractAction.ADD_TERM,
            ContractAction.CREATE_VERSION,
            ContractAction.SEND_INVITE,
            ContractAction.DELETE_CONTRACT,
        ),
        "party_2": (),
    },
    ContractStage.AWAITING_COUNTERPARTY: {
        "party_1": (ContractAction.ASK_QUESTION, ContractAction.SEND_INVITE),
        "party_2": (ContractAction.SIGN_COUNTERPARTY, ContractAction.REQUEST_CHANGES),
    },
    ContractStage.AWAITING_CREATOR: {
        "party_1": (ContractAction.SIGN_CREATOR,),
        "party_2": (),
    },
    ContractStage.ACTIVE: {
        "party_1": (
            ContractAction.OPEN_DISPUTE,
            ContractAction.CONFIRM_COMPLETION,
            ContractAction.DOWNLOAD_CERTIFICATE,
        ),
        "party_2": (
            ContractAction.OPEN_DISPUTE,
            ContractAction.CONFIRM_COMPLETION,
            ContractAction.DOWNLOAD_CERTIFICATE,
        ),
    },
    ContractStage.DISPUTE: {
        "party_1": (ContractAction.RESPOND_TO_DISPUTE, ContractAction.DOWNLOAD_CERTIFICATE),
        "party_2": (ContractAction.RESPOND_TO_DISPUTE, ContractAction.DOWNLOAD_CERTIFICATE),
    },
    ContractStage.COMPLETED: {
        "party_1": (ContractAction.DOWNLOAD_CERTIFICATE,),
        "party_2": (ContractAction.DOWNLOAD_CERTIFICATE,),
    },
    ContractStage.DELETED: {"party_1": (), "party_2": ()},
}


def resolve_stage(context: WorkflowContext) -> ContractStage:
    if context.deleted:
        return ContractStage.DELETED
    if context.completed:
        return ContractStage.COMPLETED
    if context.finalized and context.dispute_opened:
        return ContractStage.DISPUTE
    if context.finalized:
        return ContractStage.ACTIVE
    if context.party_2_approved and not context.party_1_approved:
        return ContractStage.AWAITING_CREATOR
    if context.invite_sent:
        return ContractStage.AWAITING_COUNTERPARTY
    if context.has_version:
        return ContractStage.READY_TO_INVITE
    return ContractStage.DRAFT


def available_actions(stage: ContractStage, actor_role: str) -> tuple[ContractAction, ...]:
    return STAGE_ACTIONS[stage].get(actor_role, ())


def describe_workflow(context: WorkflowContext, actor_role: str) -> dict:
    stage = resolve_stage(context)
    actions = available_actions(stage, actor_role)
    return {
        "stage": stage.value,
        "stage_label": STAGE_LABELS[stage],
        "available_actions": [action.value for action in actions],
        "action_labels": {action.value: ACTION_LABELS[action] for action in actions},
    }


def action_is_allowed(context: WorkflowContext, actor_role: str, action: ContractAction) -> bool:
    return action in available_actions(resolve_stage(context), actor_role)


def workflow_catalog() -> dict:
    return {
        "stages": {
            stage.value: {
                "label": STAGE_LABELS[stage],
                "actions": {
                    role: [action.value for action in actions]
                    for role, actions in STAGE_ACTIONS[stage].items()
                },
            }
            for stage in ContractStage
        },
        "actions": {action.value: ACTION_LABELS[action] for action in ContractAction},
    }
