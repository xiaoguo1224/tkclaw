from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class WorkspaceDepartment(BaseModel):
    __tablename__ = "workspace_departments"
    __table_args__ = (
        Index(
            "uq_workspace_department_link",
            "workspace_id",
            "department_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)

    workspace = relationship("Workspace", back_populates="department_links", foreign_keys=[workspace_id])
    department = relationship("Department", back_populates="workspace_links", foreign_keys=[department_id])
    organization = relationship("Organization", foreign_keys=[org_id])
