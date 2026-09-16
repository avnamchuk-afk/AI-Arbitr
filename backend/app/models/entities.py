import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    finalized = "finalized"


class ParticipantRole(str, enum.Enum):
    party_1 = "party_1"
    party_2 = "party_2"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    changes_requested = "changes_requested"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trusted_login_count: Mapped[int] = mapped_column(Integer, default=0)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject: Mapped[str] = mapped_column(String(160), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    contract_category: Mapped[str] = mapped_column(String(80), default="unknown", index=True)
    session_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(80), default="app", index=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ContractSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120), default="Новый договор")
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.draft)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True, nullable=True)
    invite_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    participants: Mapped[list["ContractParticipant"]] = relationship(back_populates="session")
    versions: Mapped[list["ContractVersion"]] = relationship(back_populates="session")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class ContractAnalyticsSnapshot(Base):
    __tablename__ = "contract_analytics_snapshots"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    contract_category: Mapped[str] = mapped_column(String(80), default="unknown", index=True)
    contract_kind: Mapped[str] = mapped_column(String(120), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    version_count: Mapped[int] = mapped_column(Integer, default=0)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    user_message_count: Mapped[int] = mapped_column(Integer, default=0)
    assistant_message_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_to_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    signed_by_party_2: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    signed_by_party_1: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    finalized: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    completed_without_dispute: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dispute_opened: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    monthly_payment_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_prolongation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    utilities_separate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    children_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pets_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, index=True)


class ContractParticipant(Base):
    __tablename__ = "contract_participants"
    __table_args__ = (UniqueConstraint("session_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    role: Mapped[ParticipantRole] = mapped_column(Enum(ParticipantRole))
    approval_status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.pending)
    approved_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[ContractSession] = relationship(back_populates="participants")
    user: Mapped[User | None] = relationship()


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    session: Mapped[ContractSession] = relationship(back_populates="messages")


class ContractVersion(Base):
    __tablename__ = "contract_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped[ContractSession] = relationship(back_populates="versions")


class DeadlineExtensionProposal(Base):
    __tablename__ = "deadline_extension_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), index=True)
    proposer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    responder_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    proposed_deadline: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    compensation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
