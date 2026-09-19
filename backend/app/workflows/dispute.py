from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass
class DisputeState:
    opened: bool = False
    initiator_user_id: str = ""
    opened_at: str = ""
    response_due: str = ""
    responded: bool = False
    decision_issued: bool = False
    decision_at: str = ""
    accepted_user_ids: tuple[str, ...] = ()
    closed: bool = False

    def for_user(self, user_id: str) -> dict:
        result = asdict(self)
        result["is_initiator"] = self.initiator_user_id == str(user_id)
        result["accepted_by_me"] = str(user_id) in self.accepted_user_ids
        return result


def parse_dispute_state(contents: list[str]) -> DisputeState:
    state = DisputeState()
    accepted: list[str] = []
    for content in contents:
        parts = content.split("|")
        marker = parts[0]
        if marker == "DISPUTE_OPENED":
            state.opened = True
            state.initiator_user_id = parts[1] if len(parts) > 1 else ""
            state.opened_at = parts[2] if len(parts) > 2 else ""
        elif marker == "DELAY_NOTICE":
            state.opened = True
            state.initiator_user_id = parts[1] if len(parts) > 1 else state.initiator_user_id
            state.opened_at = parts[2] if len(parts) > 2 else state.opened_at
            state.response_due = parts[3] if len(parts) > 3 else ""
        elif marker == "DELAY_RESPONSE":
            state.responded = True
        elif marker == "DISPUTE_DECISION":
            state.decision_issued = True
            state.decision_at = parts[1] if len(parts) > 1 else ""
        elif marker == "DISPUTE_ACCEPTED" and len(parts) > 1 and parts[1] not in accepted:
            accepted.append(parts[1])
        elif marker == "DISPUTE_CLOSED":
            state.closed = True
    state.accepted_user_ids = tuple(accepted)
    return state
