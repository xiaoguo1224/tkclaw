from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class WecomBindSession(BaseModel):
    __tablename__ = "wecom_bind_sessions"
    __table_args__ = (
        Index(
            "uq_wecom_bind_sessions_state_active",
            "state",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_wecom_bind_sessions_instance_user_status",
            "instance_id",
            "user_id",
            "status",
        ),
    )

    instance_id: Mapped[str] = mapped_column(String(36), ForeignKey("instances.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    state: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    qr_url: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    bound_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bound_open_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    callback_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    instance = relationship("Instance", foreign_keys=[instance_id])
    organization = relationship("Organization", foreign_keys=[org_id])
    user = relationship("User", foreign_keys=[user_id])
