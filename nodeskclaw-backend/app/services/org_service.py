"""Organization CRUD + membership management service."""

import asyncio
import logging
import re
import secrets

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.admin_membership import AdminMembership
from app.models.base import not_deleted
from app.models.cluster import Cluster
from app.models.oauth_connection import UserOAuthConnection
from app.models.org_membership import OrgMembership, OrgRole
from app.models.org_oauth_binding import OrgOAuthBinding
from app.models.organization import Organization
from app.models.instance import Instance
from app.models.instance_member import InstanceMember, InstanceRole
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.models.user_llm_config import UserLlmConfig
from app.models.user_llm_key import UserLlmKey
from app.models.user import User, UserRole
from app.schemas.deploy import DeployRequest
from app.schemas.llm import LlmConfigItem
from app.schemas.organization import (
    AiProvisionInfo,
    MemberDefaultAiCandidateInfo,
    MemberInfo,
    OAuthOrgSetupRequest,
    OrgCreate,
    OrgInfo,
    OrgUpdate,
)
from app.services import department_service, deploy_service
from app.services.registry_service import list_image_tags

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$")
_DEFAULT_RUNTIME = "openclaw"
_DEFAULT_MODEL_PROVIDER = "taoke"
_DEFAULT_MODEL_BASE_URL = "http://10.0.14.20:11434/v1"
_DEFAULT_MODEL_API_KEY = "taoke"
_DEFAULT_MODEL_API_TYPE = "openai-completions"
_DEFAULT_MODEL_ID = "Qwen3.5-122B-A10B-4bit"


async def list_orgs(db: AsyncSession) -> list[OrgInfo]:
    """列出所有组织（超管使用），附带成员数（排除 Admin 平台用户）。"""
    admin_user_ids_corr = (
        select(AdminMembership.user_id)
        .where(AdminMembership.org_id == Organization.id, AdminMembership.deleted_at.is_(None))
        .correlate(Organization)
    )
    member_count_sub = (
        select(func.count(OrgMembership.id))
        .where(
            OrgMembership.org_id == Organization.id,
            not_deleted(OrgMembership),
            OrgMembership.user_id.notin_(admin_user_ids_corr),
        )
        .correlate(Organization)
        .scalar_subquery()
        .label("member_count")
    )
    result = await db.execute(
        select(Organization, member_count_sub)
        .where(not_deleted(Organization))
        .order_by(Organization.created_at.desc())
    )
    orgs = []
    for org, count in result.all():
        info = OrgInfo.model_validate(org)
        info.member_count = count or 0
        orgs.append(info)
    return orgs


async def get_org(org_id: str, db: AsyncSession) -> Organization:
    """获取组织详情，不存在抛 404。"""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id, not_deleted(Organization))
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError("组织不存在")
    return org


async def create_org(body: OrgCreate, creator: User, db: AsyncSession) -> OrgInfo:
    """创建组织，并把创建者设为 org_admin。"""
    if not _SLUG_RE.match(body.slug):
        raise BadRequestError("slug 格式不合法（小写字母/数字/短横线，3-64 字符）")

    # 唯一性检查
    exists = await db.execute(
        select(Organization).where(Organization.slug == body.slug, not_deleted(Organization))
    )
    if exists.scalar_one_or_none():
        raise ConflictError(
            f"企业标识符 '{body.slug}' 已被使用",
            message_key="errors.org.slug_already_taken",
        )

    org = Organization(name=body.name, slug=body.slug, plan=body.plan)
    db.add(org)
    await db.flush()

    # 创建者自动成为组织管理员
    membership = OrgMembership(user_id=creator.id, org_id=org.id, role=OrgRole.admin)
    db.add(membership)

    # 如果创建者还没有当前组织，自动切换
    if creator.current_org_id is None:
        creator.current_org_id = org.id

    await db.commit()
    await db.refresh(org)
    logger.info("创建组织: %s (slug=%s) by user %s", org.name, org.slug, creator.id)
    return OrgInfo.model_validate(org)


async def oauth_org_setup(
    user: User, body: OAuthOrgSetupRequest, db: AsyncSession,
) -> OrgInfo:
    """OAuth 登录后首次开通组织。

    根据用户的 OAuthConnection 中的 provider_tenant_id 绑定组织。
    并发安全：(provider, provider_tenant_id) 有 unique 约束，
    两个同企业用户同时提交时，后者因 IntegrityError 自动降级为加入已创建的组织。
    """
    from sqlalchemy.exc import IntegrityError

    conn_result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == body.provider,
            UserOAuthConnection.deleted_at.is_(None),
        )
    )
    connection = conn_result.scalar_one_or_none()
    if connection is None or not connection.provider_tenant_id:
        raise BadRequestError(
            f"当前用户没有关联 {body.provider} 租户，无法开通组织",
            message_key="errors.org.missing_tenant_key",
        )
    tenant_id = connection.provider_tenant_id

    existing_binding = await db.execute(
        select(OrgOAuthBinding).where(
            OrgOAuthBinding.provider == body.provider,
            OrgOAuthBinding.provider_tenant_id == tenant_id,
            OrgOAuthBinding.deleted_at.is_(None),
        )
    )
    binding = existing_binding.scalar_one_or_none()
    if binding is not None:
        org_result = await db.execute(
            select(Organization).where(Organization.id == binding.org_id, not_deleted(Organization))
        )
        org = org_result.scalar_one()
        await _ensure_membership(user, org, OrgRole.member, body.job_title, db)
        return OrgInfo.model_validate(org)

    if not _SLUG_RE.match(body.slug):
        raise BadRequestError("slug 格式不合法（小写字母/数字/短横线，3-64 字符）")

    slug_exists = await db.execute(
        select(Organization).where(Organization.slug == body.slug, not_deleted(Organization))
    )
    if slug_exists.scalar_one_or_none():
        raise ConflictError(
            f"企业标识符 '{body.slug}' 已被使用",
            message_key="errors.org.slug_already_taken",
        )

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.flush()

    new_binding = OrgOAuthBinding(
        org_id=org.id, provider=body.provider, provider_tenant_id=tenant_id,
    )
    db.add(new_binding)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(OrgOAuthBinding).where(
                OrgOAuthBinding.provider == body.provider,
                OrgOAuthBinding.provider_tenant_id == tenant_id,
                OrgOAuthBinding.deleted_at.is_(None),
            )
        )
        existing = result.scalar_one()
        org_result = await db.execute(
            select(Organization).where(Organization.id == existing.org_id, not_deleted(Organization))
        )
        org = org_result.scalar_one()
        await _ensure_membership(user, org, OrgRole.member, body.job_title, db)
        return OrgInfo.model_validate(org)

    membership = OrgMembership(
        user_id=user.id, org_id=org.id, role=OrgRole.admin, job_title=body.job_title,
    )
    db.add(membership)
    user.current_org_id = org.id

    await db.commit()
    await db.refresh(org)
    logger.info(
        "OAuth 开通组织: %s (slug=%s, provider=%s, tenant=%s) by user %s",
        org.name, org.slug, body.provider, tenant_id, user.id,
    )
    return OrgInfo.model_validate(org)


async def feishu_org_setup(
    user: User, body: OAuthOrgSetupRequest, db: AsyncSession,
) -> OrgInfo:
    """向后兼容别名。"""
    if not body.provider:
        body.provider = "feishu"
    return await oauth_org_setup(user, body, db)


async def _ensure_membership(
    user: User, org: Organization, role: str, job_title: str | None, db: AsyncSession,
) -> None:
    """确保用户是组织成员，已存在则跳过。"""
    exists = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == org.id,
            not_deleted(OrgMembership),
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(OrgMembership(
            user_id=user.id, org_id=org.id, role=role, job_title=job_title,
        ))
    user.current_org_id = org.id
    await db.commit()
    await db.refresh(user)


async def update_org(org_id: str, body: OrgUpdate, db: AsyncSession) -> OrgInfo:
    """更新组织信息。"""
    org = await get_org(org_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return OrgInfo.model_validate(org)


async def delete_org(org_id: str, db: AsyncSession) -> None:
    """软删除组织（仍有运行中实例时禁止删除）。"""
    from app.models.instance import Instance, InstanceStatus

    org = await get_org(org_id, db)

    active_statuses = {
        InstanceStatus.running, InstanceStatus.creating,
        InstanceStatus.deploying, InstanceStatus.pending, InstanceStatus.updating,
    }
    result = await db.execute(
        select(func.count()).select_from(Instance).where(
            Instance.org_id == org_id,
            Instance.deleted_at.is_(None),
            Instance.status.in_(active_statuses),
        )
    )
    count = result.scalar() or 0
    if count > 0:
        raise ForbiddenError(f"该组织下仍有 {count} 个活跃实例，请先删除或停止所有实例")

    org.soft_delete()
    await db.commit()


# ── 成员管理 ─────────────────────────────────────────────


async def _load_active_default_instance_map(
    org_id: str, default_instance_ids: list[str], db: AsyncSession,
) -> dict[str, Instance]:
    if not default_instance_ids:
        return {}
    result = await db.execute(
        select(Instance).where(
            Instance.id.in_(default_instance_ids),
            Instance.org_id == org_id,
            not_deleted(Instance),
        )
    )
    return {inst.id: inst for inst in result.scalars().all()}

async def list_members(
    org_id: str, db: AsyncSession, *, current_user_id: str | None = None,
) -> list[MemberInfo]:
    """列出组织成员（排除 Admin 平台用户，但始终包含当前用户）。"""
    admin_user_ids = (
        select(AdminMembership.user_id)
        .where(
            AdminMembership.org_id == org_id,
            AdminMembership.deleted_at.is_(None),
        )
    )
    admin_filter = User.id.notin_(admin_user_ids)
    if current_user_id:
        admin_filter = or_(admin_filter, User.id == current_user_id)

    result = await db.execute(
        select(OrgMembership, User)
        .join(User, OrgMembership.user_id == User.id)
        .where(
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
            admin_filter,
        )
    )
    rows = result.all()
    department_memberships = await department_service.list_user_department_memberships(
        org_id, [user.id for _membership, user in rows], db,
    )
    default_instance_ids = [
        membership.default_instance_id
        for membership, _user in rows
        if membership.default_instance_id
    ]
    default_instance_map = await _load_active_default_instance_map(org_id, default_instance_ids, db)
    members = []
    for membership, user in rows:
        default_instance = (
            default_instance_map.get(membership.default_instance_id)
            if membership.default_instance_id
            else None
        )
        primary_department_id, primary_department_name, secondary_department_ids, secondary_departments, is_department_manager = (
            department_service.summarize_user_departments(department_memberships.get(user.id, []))
        )
        members.append(MemberInfo(
            id=membership.id,
            user_id=membership.user_id,
            org_id=membership.org_id,
            role=membership.role,
            is_super_admin=user.is_super_admin,
            user_name=user.name,
            user_email=user.email,
            user_avatar_url=user.avatar_url,
            primary_department_id=primary_department_id,
            primary_department_name=primary_department_name,
            secondary_department_ids=secondary_department_ids,
            secondary_departments=secondary_departments,
            is_department_manager=is_department_manager,
            default_ai_instance_id=default_instance.id if default_instance else None,
            default_ai_instance_name=default_instance.name if default_instance else None,
            has_default_ai=bool(default_instance),
            created_at=membership.created_at,
        ))
    return members


def _build_ai_employee_name(member_name: str | None) -> str:
    raw_name = (member_name or "").strip() or "member"
    final_name = f"{raw_name}-bot"
    return final_name[:128]


def _slugify(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", raw.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "member-bot"


async def _build_unique_instance_slug(org_id: str, base_slug: str, db: AsyncSession) -> str:
    candidate = base_slug
    for _ in range(10):
        exists = await db.execute(
            select(Instance.id).where(
                Instance.org_id == org_id,
                Instance.slug == candidate,
                not_deleted(Instance),
            )
        )
        if exists.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base_slug}-{secrets.token_hex(2)}"
    return f"{base_slug}-{secrets.token_hex(4)}"


async def _upsert_local_model_personal_config(user_id: str, org_id: str, db: AsyncSession) -> None:
    key_result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == user_id,
            UserLlmKey.provider == _DEFAULT_MODEL_PROVIDER,
            not_deleted(UserLlmKey),
        )
    )
    key = key_result.scalar_one_or_none()
    if key is None:
        db.add(UserLlmKey(
            user_id=user_id,
            provider=_DEFAULT_MODEL_PROVIDER,
            api_key=_DEFAULT_MODEL_API_KEY,
            base_url=_DEFAULT_MODEL_BASE_URL,
            api_type=_DEFAULT_MODEL_API_TYPE,
            is_active=True,
        ))
    else:
        key.api_key = _DEFAULT_MODEL_API_KEY
        key.base_url = _DEFAULT_MODEL_BASE_URL
        key.api_type = _DEFAULT_MODEL_API_TYPE
        key.is_active = True

    config_result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == user_id,
            UserLlmConfig.org_id == org_id,
            UserLlmConfig.provider == _DEFAULT_MODEL_PROVIDER,
            not_deleted(UserLlmConfig),
        )
    )
    config = config_result.scalar_one_or_none()
    selected_models = [{"id": _DEFAULT_MODEL_ID, "name": _DEFAULT_MODEL_ID}]
    if config is None:
        db.add(UserLlmConfig(
            user_id=user_id,
            org_id=org_id,
            provider=_DEFAULT_MODEL_PROVIDER,
            key_source="personal",
            selected_models=selected_models,
        ))
    else:
        config.key_source = "personal"
        config.selected_models = selected_models

    await db.commit()


async def _grant_manage_agents_permission_for_member(
    org_id: str, user_id: str, db: AsyncSession,
) -> None:
    result = await db.execute(
        select(WorkspaceMember)
        .join(Workspace, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            Workspace.org_id == org_id,
            WorkspaceMember.user_id == user_id,
            not_deleted(Workspace),
            not_deleted(WorkspaceMember),
        )
    )
    changed = False
    for member in result.scalars().all():
        perms = list(member.permissions or [])
        if "manage_agents" in perms:
            continue
        perms.append("manage_agents")
        member.permissions = perms
        changed = True
    if changed:
        await db.commit()


async def _grant_instance_admin_for_member(
    instance_id: str, user_id: str, db: AsyncSession,
) -> None:
    existing = (await db.execute(
        select(InstanceMember).where(
            InstanceMember.instance_id == instance_id,
            InstanceMember.user_id == user_id,
            not_deleted(InstanceMember),
        )
    )).scalar_one_or_none()
    if existing is not None:
        if existing.role != InstanceRole.admin:
            existing.role = InstanceRole.admin
            await db.commit()
        return
    db.add(InstanceMember(
        instance_id=instance_id,
        user_id=user_id,
        role=InstanceRole.admin,
    ))
    await db.commit()


async def provision_default_ai_employee_for_member(
    org_id: str,
    member_user: User,
    db: AsyncSession,
) -> AiProvisionInfo:
    org = await get_org(org_id, db)
    if not org.cluster_id:
        return AiProvisionInfo(
            status="failed",
            message_key="errors.org.default_cluster_required",
            message="组织未配置默认集群，无法自动创建 AI 员工",
        )

    try:
        await _upsert_local_model_personal_config(member_user.id, org_id, db)

        image_tags = await list_image_tags(db, runtime=_DEFAULT_RUNTIME)
        if not image_tags:
            return AiProvisionInfo(
                status="failed",
                message_key="errors.member.ai_provision_failed",
                message="未找到可用镜像版本，无法自动创建 AI 员工",
            )
        image_version = image_tags[0].get("tag")
        if not image_version:
            return AiProvisionInfo(
                status="failed",
                message_key="errors.member.ai_provision_failed",
                message="镜像版本为空，无法自动创建 AI 员工",
            )

        ai_name = _build_ai_employee_name(member_user.name)
        base_slug = _slugify(ai_name)
        unique_slug = await _build_unique_instance_slug(org_id, base_slug, db)

        req = DeployRequest(
            cluster_id=org.cluster_id,
            name=ai_name,
            slug=unique_slug,
            image_version=image_version,
            replicas=1,
            cpu_request="1000m",
            cpu_limit="2000m",
            mem_request="2Gi",
            mem_limit="4Gi",
            quota_cpu="2",
            quota_mem="4Gi",
            storage_size="20Gi",
            runtime=_DEFAULT_RUNTIME,
            llm_configs=[LlmConfigItem(
                provider=_DEFAULT_MODEL_PROVIDER,
                key_source="personal",
                selected_models=[{"id": _DEFAULT_MODEL_ID, "name": _DEFAULT_MODEL_ID}],
            )],
        )
        deploy_id, ctx = await deploy_service.deploy_instance(
            req=req, user=member_user, db=db, org_id=org_id,
        )
        task = asyncio.create_task(
            deploy_service.execute_deploy_pipeline(ctx),
            name=f"auto-provision-ai-{deploy_id}",
        )
        deploy_service.register_deploy_task(deploy_id, task)
        return AiProvisionInfo(status="success", instance_id=ctx.instance_id)
    except Exception as exc:
        logger.exception("新成员自动创建 AI 员工失败: org=%s user=%s err=%s", org_id, member_user.id, exc)
        return AiProvisionInfo(
            status="failed",
            message_key="errors.member.ai_provision_failed",
            message=f"自动创建 AI 员工失败: {exc}",
        )


async def add_member(
    org_id: str,
    user_id: str,
    role: str,
    db: AsyncSession,
    *,
    primary_department_id: str | None = None,
    secondary_department_ids: list[str] | None = None,
) -> MemberInfo:
    """添加成员到组织。"""
    # 检查用户存在
    user_result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("用户不存在")

    # 检查是否已是成员
    exists = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    if exists.scalar_one_or_none():
        raise ConflictError("该用户已是组织成员")

    membership = OrgMembership(user_id=user_id, org_id=org_id, role=role)
    db.add(membership)

    # 如果用户还没有当前组织，自动设置
    if user.current_org_id is None:
        user.current_org_id = org_id

    await department_service.assign_member_departments(
        org_id=org_id,
        user_id=user_id,
        primary_department_id=primary_department_id,
        secondary_department_ids=secondary_department_ids or [],
        db=db,
    )

    await db.commit()
    await db.refresh(membership)
    ai_provision = await provision_default_ai_employee_for_member(org_id, user, db)
    if ai_provision.status == "success" and ai_provision.instance_id:
        membership.default_instance_id = ai_provision.instance_id
        await db.commit()
        await db.refresh(membership)
        await _grant_manage_agents_permission_for_member(org_id, user.id, db)

    department_memberships = await department_service.list_user_department_memberships(org_id, [user.id], db)
    primary_id, primary_name, secondary_department_ids, secondary_departments, is_department_manager = (
        department_service.summarize_user_departments(department_memberships.get(user.id, []))
    )

    return MemberInfo(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        is_super_admin=user.is_super_admin,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        primary_department_id=primary_id,
        primary_department_name=primary_name,
        secondary_department_ids=secondary_department_ids,
        secondary_departments=secondary_departments,
        is_department_manager=is_department_manager,
        default_ai_instance_id=membership.default_instance_id,
        default_ai_instance_name=_build_ai_employee_name(user.name) if membership.default_instance_id else None,
        has_default_ai=bool(membership.default_instance_id),
        ai_provision=ai_provision,
        created_at=membership.created_at,
    )


async def create_member_direct(
    org_id: str,
    name: str,
    email: str,
    password: str,
    role: str,
    db: AsyncSession,
    primary_department_id: str | None = None,
    secondary_department_ids: list[str] | None = None,
) -> MemberInfo:
    """直接创建账号并加入组织。"""
    from app.services.auth_service import _hash_password

    normalized_email = email.strip().lower()

    existing_user = (
        await db.execute(
            select(User).where(
                User.email == normalized_email,
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing_user is not None:
        existing_membership = (await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == existing_user.id,
                OrgMembership.org_id == org_id,
                not_deleted(OrgMembership),
            )
        )).scalar_one_or_none()
        if existing_membership is not None:
            raise ConflictError("该邮箱已是当前组织成员")

        membership = OrgMembership(user_id=existing_user.id, org_id=org_id, role=role)
        db.add(membership)
        if existing_user.current_org_id is None:
            existing_user.current_org_id = org_id
        await department_service.assign_member_departments(
            org_id=org_id,
            user_id=existing_user.id,
            primary_department_id=primary_department_id,
            secondary_department_ids=secondary_department_ids or [],
            db=db,
        )
        await db.commit()
        await db.refresh(membership)
        ai_provision = await provision_default_ai_employee_for_member(org_id, existing_user, db)
        if ai_provision.status == "success" and ai_provision.instance_id:
            membership.default_instance_id = ai_provision.instance_id
            await db.commit()
            await db.refresh(membership)
            await _grant_manage_agents_permission_for_member(org_id, existing_user.id, db)

        department_memberships = await department_service.list_user_department_memberships(org_id, [existing_user.id], db)
        primary_id, primary_name, secondary_department_ids, secondary_departments, is_department_manager = (
            department_service.summarize_user_departments(department_memberships.get(existing_user.id, []))
        )

        return MemberInfo(
            id=membership.id,
            user_id=membership.user_id,
            org_id=membership.org_id,
            role=membership.role,
            is_super_admin=existing_user.is_super_admin,
            user_name=existing_user.name,
            user_email=existing_user.email,
            user_avatar_url=existing_user.avatar_url,
            primary_department_id=primary_id,
            primary_department_name=primary_name,
            secondary_department_ids=secondary_department_ids,
            secondary_departments=secondary_departments,
            is_department_manager=is_department_manager,
            default_ai_instance_id=membership.default_instance_id,
            default_ai_instance_name=_build_ai_employee_name(existing_user.name) if membership.default_instance_id else None,
            has_default_ai=bool(membership.default_instance_id),
            ai_provision=ai_provision,
            created_at=membership.created_at,
        )

    user = User(
        name=name.strip(),
        email=normalized_email,
        password_hash=_hash_password(password),
        role=UserRole.user,
        is_active=True,
        must_change_password=False,
        current_org_id=org_id,
    )
    db.add(user)
    await db.flush()

    membership = OrgMembership(user_id=user.id, org_id=org_id, role=role)
    db.add(membership)
    await department_service.assign_member_departments(
        org_id=org_id,
        user_id=user.id,
        primary_department_id=primary_department_id,
        secondary_department_ids=secondary_department_ids or [],
        db=db,
    )
    await db.commit()
    await db.refresh(membership)
    ai_provision = await provision_default_ai_employee_for_member(org_id, user, db)
    if ai_provision.status == "success" and ai_provision.instance_id:
        membership.default_instance_id = ai_provision.instance_id
        await db.commit()
        await db.refresh(membership)
        await _grant_manage_agents_permission_for_member(org_id, user.id, db)

    department_memberships = await department_service.list_user_department_memberships(org_id, [user.id], db)
    primary_id, primary_name, secondary_department_ids, secondary_departments, is_department_manager = (
        department_service.summarize_user_departments(department_memberships.get(user.id, []))
    )

    return MemberInfo(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        is_super_admin=user.is_super_admin,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        primary_department_id=primary_id,
        primary_department_name=primary_name,
        secondary_department_ids=secondary_department_ids,
        secondary_departments=secondary_departments,
        is_department_manager=is_department_manager,
        default_ai_instance_id=membership.default_instance_id,
        default_ai_instance_name=_build_ai_employee_name(user.name) if membership.default_instance_id else None,
        has_default_ai=bool(membership.default_instance_id),
        ai_provision=ai_provision,
        created_at=membership.created_at,
    )


async def set_org_default_cluster(
    org_id: str, cluster_id: str | None, db: AsyncSession,
) -> OrgInfo:
    org = await get_org(org_id, db)
    if cluster_id is None:
        org.cluster_id = None
        await db.commit()
        await db.refresh(org)
        return OrgInfo.model_validate(org)

    cluster = (await db.execute(
        select(Cluster).where(Cluster.id == cluster_id, not_deleted(Cluster))
    )).scalar_one_or_none()
    if cluster is None:
        raise NotFoundError("集群不存在")
    if cluster.org_id not in (None, org_id):
        raise ForbiddenError("该集群不在当前组织可用范围")
    org.cluster_id = cluster.id
    await db.commit()
    await db.refresh(org)
    return OrgInfo.model_validate(org)


async def list_member_default_ai_candidates(
    org_id: str, membership_id: str, db: AsyncSession,
) -> list[MemberDefaultAiCandidateInfo]:
    row = (await db.execute(
        select(OrgMembership).where(
            OrgMembership.id == membership_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError("成员记录不存在")

    used_instance_ids = set((await db.execute(
        select(OrgMembership.default_instance_id).where(
            OrgMembership.org_id == org_id,
            OrgMembership.id != membership_id,
            OrgMembership.default_instance_id.is_not(None),
            not_deleted(OrgMembership),
        )
    )).scalars().all())
    used_instance_ids.discard(None)

    result = await db.execute(
        select(Instance).where(
            Instance.org_id == org_id,
            not_deleted(Instance),
        ).order_by(Instance.created_at.desc())
    )
    return [
        MemberDefaultAiCandidateInfo(id=inst.id, name=inst.name, status=inst.status)
        for inst in result.scalars().all()
        if inst.id not in used_instance_ids
    ]


async def update_member_default_ai(
    org_id: str,
    membership_id: str,
    instance_id: str | None,
    db: AsyncSession,
) -> MemberInfo:
    row = await db.execute(
        select(OrgMembership, User)
        .join(User, OrgMembership.user_id == User.id)
        .where(
            OrgMembership.id == membership_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
            not_deleted(User),
        )
    )
    pair = row.first()
    if pair is None:
        raise NotFoundError("成员记录不存在")
    membership, user = pair

    if instance_id is None:
        membership.default_instance_id = None
    else:
        instance = (await db.execute(
            select(Instance).where(
                Instance.id == instance_id,
                not_deleted(Instance),
            )
        )).scalar_one_or_none()
        if instance is None:
            raise NotFoundError("AI 员工不存在")
        if instance.org_id != org_id:
            raise ForbiddenError("不允许关联其他组织的 AI 员工")
        used_by_other = (await db.execute(
            select(OrgMembership.id).where(
                OrgMembership.org_id == org_id,
                OrgMembership.id != membership_id,
                OrgMembership.default_instance_id == instance.id,
                not_deleted(OrgMembership),
            )
        )).scalar_one_or_none()
        if used_by_other is not None:
            raise ConflictError("该 AI 员工已被其他成员设置为默认")
        membership.default_instance_id = instance.id

    await db.commit()
    if instance_id is not None:
        await _grant_manage_agents_permission_for_member(org_id, membership.user_id, db)
        await _grant_instance_admin_for_member(instance_id, membership.user_id, db)

    default_map = await _load_active_default_instance_map(
        org_id,
        [membership.default_instance_id] if membership.default_instance_id else [],
        db,
    )
    default_instance = default_map.get(membership.default_instance_id) if membership.default_instance_id else None
    department_memberships = await department_service.list_user_department_memberships(org_id, [user.id], db)
    primary_id, primary_name, secondary_department_ids, secondary_departments, is_department_manager = (
        department_service.summarize_user_departments(department_memberships.get(user.id, []))
    )
    return MemberInfo(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        is_super_admin=user.is_super_admin,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        primary_department_id=primary_id,
        primary_department_name=primary_name,
        secondary_department_ids=secondary_department_ids,
        secondary_departments=secondary_departments,
        is_department_manager=is_department_manager,
        default_ai_instance_id=default_instance.id if default_instance else None,
        default_ai_instance_name=default_instance.name if default_instance else None,
        has_default_ai=bool(default_instance),
        created_at=membership.created_at,
    )


async def update_member_role(org_id: str, membership_id: str, role: str, db: AsyncSession) -> MemberInfo:
    """修改成员角色。"""
    result = await db.execute(
        select(OrgMembership, User)
        .join(User, OrgMembership.user_id == User.id)
        .where(
            OrgMembership.id == membership_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    row = result.first()
    if row is None:
        raise NotFoundError("成员记录不存在")

    membership, user = row
    membership.role = role
    await db.commit()
    default_map = await _load_active_default_instance_map(
        org_id,
        [membership.default_instance_id] if membership.default_instance_id else [],
        db,
    )
    default_instance = default_map.get(membership.default_instance_id) if membership.default_instance_id else None
    department_memberships = await department_service.list_user_department_memberships(org_id, [user.id], db)
    primary_id, primary_name, secondary_department_ids, secondary_departments, is_department_manager = (
        department_service.summarize_user_departments(department_memberships.get(user.id, []))
    )

    return MemberInfo(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        is_super_admin=user.is_super_admin,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        primary_department_id=primary_id,
        primary_department_name=primary_name,
        secondary_department_ids=secondary_department_ids,
        secondary_departments=secondary_departments,
        is_department_manager=is_department_manager,
        default_ai_instance_id=default_instance.id if default_instance else None,
        default_ai_instance_name=default_instance.name if default_instance else None,
        has_default_ai=bool(default_instance),
        created_at=membership.created_at,
    )


async def update_member_departments(
    org_id: str,
    membership_id: str,
    primary_department_id: str | None,
    secondary_department_ids: list[str],
    db: AsyncSession,
) -> MemberInfo:
    result = await db.execute(
        select(OrgMembership, User)
        .join(User, OrgMembership.user_id == User.id)
        .where(
            OrgMembership.id == membership_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    row = result.first()
    if row is None:
        raise NotFoundError("成员记录不存在")

    membership, user = row
    await department_service.assign_member_departments(
        org_id=org_id,
        user_id=membership.user_id,
        primary_department_id=primary_department_id,
        secondary_department_ids=secondary_department_ids,
        db=db,
    )
    await db.commit()
    default_map = await _load_active_default_instance_map(
        org_id,
        [membership.default_instance_id] if membership.default_instance_id else [],
        db,
    )
    default_instance = default_map.get(membership.default_instance_id) if membership.default_instance_id else None
    department_memberships = await department_service.list_user_department_memberships(org_id, [user.id], db)
    primary_id, primary_name, secondary_department_ids, secondary_departments, is_department_manager = (
        department_service.summarize_user_departments(department_memberships.get(user.id, []))
    )

    return MemberInfo(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        is_super_admin=user.is_super_admin,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        primary_department_id=primary_id,
        primary_department_name=primary_name,
        secondary_department_ids=secondary_department_ids,
        secondary_departments=secondary_departments,
        is_department_manager=is_department_manager,
        default_ai_instance_id=default_instance.id if default_instance else None,
        default_ai_instance_name=default_instance.name if default_instance else None,
        has_default_ai=bool(default_instance),
        created_at=membership.created_at,
    )


async def remove_member(org_id: str, membership_id: str, db: AsyncSession) -> None:
    """移除成员（软删除）。"""
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.id == membership_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError("成员记录不存在")

    # 检查是否是最后一个 admin
    admin_count = await db.execute(
        select(func.count()).where(
            OrgMembership.org_id == org_id,
            OrgMembership.role == OrgRole.admin,
            not_deleted(OrgMembership),
        )
    )
    if membership.role == OrgRole.admin and admin_count.scalar_one() <= 1:
        raise ForbiddenError("组织至少需要一个管理员")

    department_memberships = (await db.execute(
        select(department_service.DepartmentMembership).where(
            department_service.DepartmentMembership.org_id == org_id,
            department_service.DepartmentMembership.user_id == membership.user_id,
            not_deleted(department_service.DepartmentMembership),
        )
    )).scalars().all()
    for department_membership in department_memberships:
        department_membership.soft_delete()

    membership.soft_delete()
    await db.commit()


async def switch_org(user: User, org_id: str, db: AsyncSession) -> OrgInfo:
    """切换用户当前组织。"""
    # 检查是否是该组织的成员（超管可切换任意组织）
    if not user.is_super_admin:
        result = await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.org_id == org_id,
                not_deleted(OrgMembership),
            )
        )
        if result.scalar_one_or_none() is None:
            raise ForbiddenError("您不是该组织的成员")

    org = await get_org(org_id, db)
    user.current_org_id = org_id
    await db.commit()
    return OrgInfo.model_validate(org)


async def list_user_orgs(user: User, db: AsyncSession) -> list[OrgInfo]:
    """列出用户所属的所有组织，附带成员数（排除 Admin 平台用户）。"""
    if user.is_super_admin:
        return await list_orgs(db)

    admin_user_ids_corr = (
        select(AdminMembership.user_id)
        .where(AdminMembership.org_id == Organization.id, AdminMembership.deleted_at.is_(None))
        .correlate(Organization)
    )
    member_count_sub = (
        select(func.count(OrgMembership.id))
        .where(
            OrgMembership.org_id == Organization.id,
            not_deleted(OrgMembership),
            OrgMembership.user_id.notin_(admin_user_ids_corr),
        )
        .correlate(Organization)
        .scalar_subquery()
        .label("member_count")
    )
    result = await db.execute(
        select(Organization, member_count_sub)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(
            OrgMembership.user_id == user.id,
            not_deleted(OrgMembership),
            not_deleted(Organization),
        )
        .order_by(Organization.created_at.desc())
    )
    orgs = []
    for org, count in result.all():
        info = OrgInfo.model_validate(org)
        info.member_count = count or 0
        orgs.append(info)
    return orgs
