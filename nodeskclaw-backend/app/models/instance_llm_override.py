"""Per-instance LLM provider overrides (base_url / api_type)."""

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class InstanceLlmOverride(BaseModel):
    __tablename__ = "instance_llm_overrides"
    __table_args__ = (
        Index(
            "uq_instance_llm_overrides_inst_provider",
            "instance_id", "provider",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
