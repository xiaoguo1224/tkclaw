"""Department hierarchy and scoped membership service."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.base import not_deleted
from app.models.department import Department, DepartmentMembership, DepartmentMembershipRole
from app.models.org_membership import OrgMembership, OrgRole
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_department import WorkspaceDepartment
from app.schemas.organization import DepartmentInfo, DepartmentMemberInfo

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,126}$")


async def _load_departments(org_id: str, db: AsyncSession) -> list[Department]:
    result = await db.execute(
        select(Department).where(
            Department.org_id == org_id,
            not_deleted(Department),
        ).order_by(Department.sort_order.asc(), Department.created_at.asc())
    )
    return list(result.scalars().all())


def _build_children_map(departments: list[Department]) -> dict[str | None, list[Department]]:
    grouped: dict[str | None, list[Department]] = defaultdict(list)
    for department in departments:
        grouped[department.parent_id].append(department)
    return grouped


def _collect_descendant_ids(root_id: str, grouped: dict[str | None, list[Department]]) -> set[str]:
    stack = [root_id]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for child in grouped.get(current, []):
            stack.append(child.id)
    return seen


async def get_department(org_id: str, department_id: str, db: AsyncSession) -> Department:
    result = await db.execute(
        select(Department).where(
            Department.id == department_id,
            Department.org_id == org_id,
            not_deleted(Department),
        )
    )
    department = result.scalar_one_or_none()
    if department is None:
        raise NotFoundError("部门不存在", "errors.department.not_found")
    return department


async def list_departments(org_id: str, db: AsyncSession) -> list[DepartmentInfo]:
    departments = await _load_departments(org_id, db)
    if not departments:
        return []

    result = await db.execute(
        select(
            DepartmentMembership.department_id,
            func.count(DepartmentMembership.id),
            func.count().filter(DepartmentMembership.role == DepartmentMembershipRole.manager),
        ).where(
            DepartmentMembership.org_id == org_id,
            not_deleted(DepartmentMembership),
        ).group_by(DepartmentMembership.department_id)
    )
    stats = {
        row[0]: {"member_count": row[1] or 0, "manager_count": row[2] or 0}
        for row in result.all()
    }

    info_map: dict[str, DepartmentInfo] = {}
    for department in departments:
        info_map[department.id] = DepartmentInfo(
            id=department.id,
            org_id=department.org_id,
            parent_id=department.parent_id,
            name=department.name,
            slug=department.slug,
            description=department.description,
            sort_order=department.sort_order,
            is_active=department.is_active,
            member_count=stats.get(department.id, {}).get("member_count", 0),
            manager_count=stats.get(department.id, {}).get("manager_count", 0),
            created_at=department.created_at,
            updated_at=department.updated_at,
            children=[],
        )

    roots: list[DepartmentInfo] = []
    for department in departments:
        node = info_map[department.id]
        if department.parent_id and department.parent_id in info_map:
            info_map[department.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


async def create_department(org_id: str, body, db: AsyncSession) -> DepartmentInfo:
    if not _SLUG_RE.match(body.slug):
        raise BadRequestError("部门标识格式不合法", "errors.department.invalid_slug")
    if body.parent_id:
        await get_department(org_id, body.parent_id, db)

    existing = await db.execute(
        select(Department.id).where(
            Department.org_id == org_id,
            Department.slug == body.slug,
            not_deleted(Department),
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError("部门标识已存在", message_key="errors.department.slug_already_taken")

    department = Department(
        org_id=org_id,
        parent_id=body.parent_id,
        name=body.name.strip(),
        slug=body.slug.strip(),
        description=body.description.strip(),
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    db.add(department)
    await db.commit()
    await db.refresh(department)
    return DepartmentInfo(
        id=department.id,
        org_id=department.org_id,
        parent_id=department.parent_id,
        name=department.name,
        slug=department.slug,
        description=department.description,
        sort_order=department.sort_order,
        is_active=department.is_active,
        member_count=0,
        manager_count=0,
        created_at=department.created_at,
        updated_at=department.updated_at,
        children=[],
    )


async def update_department(org_id: str, department_id: str, body, db: AsyncSession) -> DepartmentInfo:
    department = await get_department(org_id, department_id, db)
    if body.slug is not None:
        if not _SLUG_RE.match(body.slug):
            raise BadRequestError("部门标识格式不合法", "errors.department.invalid_slug")
        existing = await db.execute(
            select(Department.id).where(
                Department.org_id == org_id,
                Department.slug == body.slug,
                Department.id != department_id,
                not_deleted(Department),
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError("部门标识已存在", message_key="errors.department.slug_already_taken")
        department.slug = body.slug.strip()
    if body.parent_id is not None:
        if body.parent_id == department_id:
            raise BadRequestError("部门不能设置自己为父部门", "errors.department.invalid_parent")
        if body.parent_id:
            all_departments = await _load_departments(org_id, db)
            grouped = _build_children_map(all_departments)
            descendant_ids = _collect_descendant_ids(department_id, grouped)
            if body.parent_id in descendant_ids:
                raise BadRequestError("不能把子部门设置为父部门", "errors.department.invalid_parent")
            await get_department(org_id, body.parent_id, db)
        department.parent_id = body.parent_id
    for field in ("name", "description", "sort_order", "is_active"):
        value = getattr(body, field)
        if value is not None:
            setattr(department, field, value.strip() if isinstance(value, str) else value)
    await db.commit()
    await db.refresh(department)
    return DepartmentInfo(
        id=department.id,
        org_id=department.org_id,
        parent_id=department.parent_id,
        name=department.name,
        slug=department.slug,
        description=department.description,
        sort_order=department.sort_order,
        is_active=department.is_active,
        member_count=0,
        manager_count=0,
        created_at=department.created_at,
        updated_at=department.updated_at,
        children=[],
    )


async def delete_department(org_id: str, department_id: str, db: AsyncSession) -> None:
    department = await get_department(org_id, department_id, db)
    child_count = await db.execute(
        select(func.count()).select_from(Department).where(
            Department.org_id == org_id,
            Department.parent_id == department_id,
            not_deleted(Department),
        )
    )
    if (child_count.scalar() or 0) > 0:
        raise ForbiddenError("请先删除或迁移子部门", "errors.department.has_children")
    membership_count = await db.execute(
        select(func.count()).select_from(DepartmentMembership).where(
            DepartmentMembership.department_id == department_id,
            not_deleted(DepartmentMembership),
        )
    )
    if (membership_count.scalar() or 0) > 0:
        raise ForbiddenError("请先移除部门成员", "errors.department.has_members")
    department.soft_delete()
    await db.commit()


async def list_department_members(org_id: str, department_id: str, db: AsyncSession) -> list[DepartmentMemberInfo]:
    await get_department(org_id, department_id, db)
    result = await db.execute(
        select(DepartmentMembership, User).join(User, DepartmentMembership.user_id == User.id).where(
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.department_id == department_id,
            not_deleted(DepartmentMembership),
            not_deleted(User),
        )
    )
    return [
        DepartmentMemberInfo(
            id=membership.id,
            org_id=membership.org_id,
            department_id=membership.department_id,
            user_id=membership.user_id,
            role=membership.role,
            is_primary=membership.is_primary,
            user_name=user.name,
            user_email=user.email,
            user_avatar_url=user.avatar_url,
            created_at=membership.created_at,
        )
        for membership, user in result.all()
    ]


async def assign_member_departments(
    *,
    org_id: str,
    user_id: str,
    primary_department_id: str | None,
    secondary_department_ids: list[str],
    db: AsyncSession,
) -> None:
    valid_ids = [department_id for department_id in [primary_department_id, *secondary_department_ids] if department_id]
    if len(set(valid_ids)) != len(valid_ids):
        raise BadRequestError("部门配置重复", "errors.department.duplicate_membership")
    if primary_department_id is None and secondary_department_ids:
        raise BadRequestError("存在兼任部门时必须指定主部门", "errors.department.primary_required")

    for department_id in valid_ids:
        await get_department(org_id, department_id, db)

    existing_memberships = (await db.execute(
        select(DepartmentMembership).where(
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.user_id == user_id,
            not_deleted(DepartmentMembership),
        )
    )).scalars().all()
    existing_by_department = {membership.department_id: membership for membership in existing_memberships}

    desired_ids = set(valid_ids)
    for membership in existing_memberships:
        if membership.department_id not in desired_ids:
            membership.soft_delete()

    for department_id in valid_ids:
        membership = existing_by_department.get(department_id)
        if membership is None or membership.deleted_at is not None:
            membership = DepartmentMembership(
                org_id=org_id,
                user_id=user_id,
                department_id=department_id,
            )
            db.add(membership)
        membership.is_primary = department_id == primary_department_id
        membership.role = existing_by_department.get(department_id).role if department_id in existing_by_department else DepartmentMembershipRole.member


async def add_department_member(org_id: str, department_id: str, body, db: AsyncSession) -> DepartmentMemberInfo:
    await get_department(org_id, department_id, db)
    user_exists = (await db.execute(
        select(OrgMembership.id).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == body.user_id,
            not_deleted(OrgMembership),
        )
    )).scalar_one_or_none()
    if user_exists is None:
        raise NotFoundError("用户不是当前组织成员", "errors.org.member_not_found")

    if body.is_primary:
        existing_memberships = (await db.execute(
            select(DepartmentMembership.department_id).where(
                DepartmentMembership.org_id == org_id,
                DepartmentMembership.user_id == body.user_id,
                not_deleted(DepartmentMembership),
                DepartmentMembership.department_id != department_id,
            )
        )).scalars().all()
        await assign_member_departments(
            org_id=org_id,
            user_id=body.user_id,
            primary_department_id=department_id,
            secondary_department_ids=list(existing_memberships),
            db=db,
        )
    else:
        existing = (await db.execute(
            select(DepartmentMembership).where(
                DepartmentMembership.org_id == org_id,
                DepartmentMembership.user_id == body.user_id,
                DepartmentMembership.department_id == department_id,
                not_deleted(DepartmentMembership),
            )
        )).scalar_one_or_none()
        if existing:
            raise ConflictError("该用户已在部门中", message_key="errors.department.member_exists")
        membership = DepartmentMembership(
            org_id=org_id,
            user_id=body.user_id,
            department_id=department_id,
            role=body.role,
            is_primary=False,
        )
        db.add(membership)

    await db.commit()
    user = (await db.execute(select(User).where(User.id == body.user_id, not_deleted(User)))).scalar_one()
    membership = (await db.execute(
        select(DepartmentMembership).where(
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.user_id == body.user_id,
            DepartmentMembership.department_id == department_id,
            not_deleted(DepartmentMembership),
        )
    )).scalar_one()
    return DepartmentMemberInfo(
        id=membership.id,
        org_id=membership.org_id,
        department_id=membership.department_id,
        user_id=membership.user_id,
        role=membership.role,
        is_primary=membership.is_primary,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        created_at=membership.created_at,
    )


async def update_department_member(org_id: str, department_id: str, membership_id: str, body, db: AsyncSession) -> DepartmentMemberInfo:
    await get_department(org_id, department_id, db)
    result = await db.execute(
        select(DepartmentMembership, User).join(User, DepartmentMembership.user_id == User.id).where(
            DepartmentMembership.id == membership_id,
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.department_id == department_id,
            not_deleted(DepartmentMembership),
            not_deleted(User),
        )
    )
    row = result.first()
    if row is None:
        raise NotFoundError("部门成员不存在", "errors.department.member_not_found")
    membership, user = row
    if body.role is not None:
        membership.role = body.role
    if body.is_primary is not None:
        membership.is_primary = body.is_primary
        if body.is_primary:
            siblings = (await db.execute(
                select(DepartmentMembership).where(
                    DepartmentMembership.org_id == org_id,
                    DepartmentMembership.user_id == membership.user_id,
                    DepartmentMembership.id != membership.id,
                    not_deleted(DepartmentMembership),
                )
            )).scalars().all()
            for sibling in siblings:
                sibling.is_primary = False
    await db.commit()
    return DepartmentMemberInfo(
        id=membership.id,
        org_id=membership.org_id,
        department_id=membership.department_id,
        user_id=membership.user_id,
        role=membership.role,
        is_primary=membership.is_primary,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        created_at=membership.created_at,
    )


async def remove_department_member(org_id: str, department_id: str, membership_id: str, db: AsyncSession) -> None:
    await get_department(org_id, department_id, db)
    membership = (await db.execute(
        select(DepartmentMembership).where(
            DepartmentMembership.id == membership_id,
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.department_id == department_id,
            not_deleted(DepartmentMembership),
        )
    )).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("部门成员不存在", "errors.department.member_not_found")
    if membership.is_primary:
        raise ForbiddenError("请先设置新的主部门", "errors.department.primary_required")
    membership.soft_delete()
    await db.commit()


async def list_user_department_memberships(org_id: str, user_ids: list[str], db: AsyncSession) -> dict[str, list[tuple[DepartmentMembership, Department]]]:
    if not user_ids:
        return {}
    result = await db.execute(
        select(DepartmentMembership, Department).join(
            Department, DepartmentMembership.department_id == Department.id,
        ).where(
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.user_id.in_(user_ids),
            not_deleted(DepartmentMembership),
            not_deleted(Department),
        )
    )
    grouped: dict[str, list[tuple[DepartmentMembership, Department]]] = defaultdict(list)
    for membership, department in result.all():
        grouped[membership.user_id].append((membership, department))
    return grouped


def summarize_user_departments(
    user_memberships: list[tuple[DepartmentMembership, Department]],
) -> tuple[str | None, str | None, list[str], list[str], bool]:
    primary_id = None
    primary_name = None
    secondary_ids: list[str] = []
    secondary_names: list[str] = []
    is_manager = False
    for membership, department in user_memberships:
        if membership.role == DepartmentMembershipRole.manager:
            is_manager = True
        if membership.is_primary:
            primary_id = department.id
            primary_name = department.name
        else:
            secondary_ids.append(department.id)
            secondary_names.append(department.name)
    return primary_id, primary_name, secondary_ids, secondary_names, is_manager


async def get_user_primary_department_id(org_id: str, user_id: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(DepartmentMembership.department_id).where(
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.user_id == user_id,
            DepartmentMembership.is_primary.is_(True),
            not_deleted(DepartmentMembership),
        )
    )
    return result.scalar_one_or_none()


async def get_org_department_scope_ids(org_id: str, db: AsyncSession) -> set[str]:
    departments = await _load_departments(org_id, db)
    return {department.id for department in departments}


async def get_department_tree_ids(org_id: str, department_id: str, db: AsyncSession) -> set[str]:
    departments = await _load_departments(org_id, db)
    grouped = _build_children_map(departments)
    return _collect_descendant_ids(department_id, grouped)


async def get_user_managed_department_ids(org_id: str, user_id: str, db: AsyncSession) -> set[str]:
    managed_rows = (await db.execute(
        select(DepartmentMembership.department_id).where(
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.user_id == user_id,
            DepartmentMembership.role == DepartmentMembershipRole.manager,
            not_deleted(DepartmentMembership),
        )
    )).scalars().all()
    if not managed_rows:
        return set()
    departments = await _load_departments(org_id, db)
    grouped = _build_children_map(departments)
    scope: set[str] = set()
    for department_id in managed_rows:
        scope.update(_collect_descendant_ids(department_id, grouped))
    return scope


async def get_workspace_allowed_department_ids(workspace_id: str, db: AsyncSession) -> set[str]:
    workspace = (await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, not_deleted(Workspace))
    )).scalar_one_or_none()
    if workspace is None:
        return set()
    if workspace.visibility_scope != "departments":
        return await get_org_department_scope_ids(workspace.org_id, db)
    linked_department_ids = (await db.execute(
        select(WorkspaceDepartment.department_id).where(
            WorkspaceDepartment.workspace_id == workspace_id,
            WorkspaceDepartment.org_id == workspace.org_id,
            not_deleted(WorkspaceDepartment),
        )
    )).scalars().all()
    if linked_department_ids:
        return set(linked_department_ids)
    return set(workspace.allowed_department_ids or [])


async def get_workspace_linked_department_ids(workspace_id: str, org_id: str, db: AsyncSession) -> list[str]:
    linked_department_ids = (await db.execute(
        select(WorkspaceDepartment.department_id).where(
            WorkspaceDepartment.workspace_id == workspace_id,
            WorkspaceDepartment.org_id == org_id,
            not_deleted(WorkspaceDepartment),
        )
    )).scalars().all()
    if linked_department_ids:
        return sorted(set(linked_department_ids))
    workspace = (await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.org_id == org_id,
            not_deleted(Workspace),
        )
    )).scalar_one_or_none()
    if workspace is None:
        return []
    return sorted(set(workspace.allowed_department_ids or []))


async def sync_workspace_departments(
    workspace_id: str,
    org_id: str,
    department_ids: list[str],
    db: AsyncSession,
) -> None:
    desired_ids = {department_id for department_id in department_ids if department_id}
    for department_id in desired_ids:
        await get_department(org_id, department_id, db)

    existing_links = (await db.execute(
        select(WorkspaceDepartment).where(
            WorkspaceDepartment.workspace_id == workspace_id,
            WorkspaceDepartment.org_id == org_id,
            not_deleted(WorkspaceDepartment),
        )
    )).scalars().all()
    existing_by_department = {link.department_id: link for link in existing_links}

    for link in existing_links:
        if link.department_id not in desired_ids:
            link.soft_delete()

    for department_id in desired_ids:
        if department_id in existing_by_department:
            continue
        db.add(WorkspaceDepartment(
            workspace_id=workspace_id,
            department_id=department_id,
            org_id=org_id,
        ))


async def can_manage_org_members(org_id: str, user_id: str, db: AsyncSession) -> bool:
    org_role = (await db.execute(
        select(OrgMembership.role).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
            not_deleted(OrgMembership),
        )
    )).scalar_one_or_none()
    if org_role == OrgRole.admin:
        return True
    return bool(await get_user_managed_department_ids(org_id, user_id, db))


async def require_org_member_scope(org_id: str, operator_id: str, target_user_id: str, db: AsyncSession) -> None:
    org_role = (await db.execute(
        select(OrgMembership.role).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == operator_id,
            not_deleted(OrgMembership),
        )
    )).scalar_one_or_none()
    if org_role == OrgRole.admin:
        return
    managed_ids = await get_user_managed_department_ids(org_id, operator_id, db)
    if not managed_ids:
        raise ForbiddenError("没有部门管理权限", "errors.department.forbidden")
    target_department_ids = (await db.execute(
        select(DepartmentMembership.department_id).where(
            DepartmentMembership.org_id == org_id,
            DepartmentMembership.user_id == target_user_id,
            not_deleted(DepartmentMembership),
        )
    )).scalars().all()
    if not target_department_ids or not set(target_department_ids).intersection(managed_ids):
        raise ForbiddenError("只能管理本部门树成员", "errors.department.forbidden")


async def get_workspace_manageable_scope(
    workspace_id: str,
    org_id: str,
    operator_id: str,
    db: AsyncSession,
) -> set[str]:
    org_role = (await db.execute(
        select(OrgMembership.role).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == operator_id,
            not_deleted(OrgMembership),
        )
    )).scalar_one_or_none()
    workspace_scope = await get_workspace_allowed_department_ids(workspace_id, db)
    if org_role == OrgRole.admin:
        return workspace_scope
    managed_scope = await get_user_managed_department_ids(org_id, operator_id, db)
    return workspace_scope.intersection(managed_scope)
