"""Department models for org hierarchy and scoped membership."""

from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class DepartmentMembershipRole(str, Enum):
    member = "member"
    manager = "manager"


class WorkspaceVisibilityScope(str, Enum):
    org = "org"
    departments = "departments"


class WorkspaceAutoSyncMode(str, Enum):
    manual = "manual"
    suggested = "suggested"


class Department(BaseModel):
    __tablename__ = "departments"
    __table_args__ = (
        Index(
            "uq_department_org_slug",
            "org_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")

    organization = relationship("Organization", back_populates="departments", foreign_keys=[org_id])
    parent = relationship("Department", remote_side="Department.id", back_populates="children", foreign_keys=[parent_id])
    children = relationship("Department", back_populates="parent")
    memberships = relationship("DepartmentMembership", back_populates="department")
    workspace_links = relationship("WorkspaceDepartment", back_populates="department")


class DepartmentMembership(BaseModel):
    __tablename__ = "department_memberships"
    __table_args__ = (
        Index(
            "uq_department_membership_user_department",
            "user_id",
            "department_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_department_membership_primary_org_user",
            "org_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND is_primary = true"),
        ),
    )

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), default=DepartmentMembershipRole.member, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

    organization = relationship("Organization", foreign_keys=[org_id])
    user = relationship("User", back_populates="department_memberships", foreign_keys=[user_id])
    department = relationship("Department", back_populates="memberships", foreign_keys=[department_id])
