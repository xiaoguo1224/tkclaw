"""Organization & membership schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class OrgCreate(BaseModel):
    name: str
    slug: str
    plan: str = "free"


class OrgUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None
    max_instances: int | None = None
    max_cpu_total: str | None = None
    max_mem_total: str | None = None
    max_storage_total: str | None = None
    cluster_id: str | None = None  # 绑定/解绑专属集群
    is_active: bool | None = None

    @field_validator("max_cpu_total", "max_mem_total", "max_storage_total", mode="before")
    @classmethod
    def _coerce_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        return str(v)


class OrgInfo(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    max_instances: int
    max_cpu_total: str
    max_mem_total: str
    max_storage_total: str
    cluster_id: str | None = None
    cluster_name: str | None = None
    is_active: bool
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrgNameUpdate(BaseModel):
    name: str


class AiProvisionInfo(BaseModel):
    status: str
    instance_id: str | None = None
    message_key: str | None = None
    message: str | None = None


class MemberInfo(BaseModel):
    id: str
    user_id: str
    org_id: str
    role: str
    is_super_admin: bool = False
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_url: str | None = None
    primary_department_id: str | None = None
    primary_department_name: str | None = None
    secondary_department_ids: list[str] = []
    secondary_departments: list[str] = []
    is_department_manager: bool = False
    ai_provision: AiProvisionInfo | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"
    primary_department_id: str | None = None
    secondary_department_ids: list[str] = []


class CreateMemberDirectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)
    role: str = "member"
    primary_department_id: str | None = None
    secondary_department_ids: list[str] = []

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: EmailStr) -> str:
        return str(v).strip().lower()


class UpdateMemberRoleRequest(BaseModel):
    role: str


class UpdateMemberDepartmentsRequest(BaseModel):
    primary_department_id: str | None = None
    secondary_department_ids: list[str] = []


class OAuthOrgSetupRequest(BaseModel):
    provider: str
    name: str
    slug: str
    job_title: str | None = None


FeishuOrgSetupRequest = OAuthOrgSetupRequest


class ResetPasswordResponse(BaseModel):
    password: str


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=128)
    parent_id: str | None = None
    description: str = ""
    sort_order: int = 0
    is_active: bool = True


class DepartmentUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    parent_id: str | None = None
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class DepartmentInfo(BaseModel):
    id: str
    org_id: str
    parent_id: str | None = None
    name: str
    slug: str
    description: str
    sort_order: int
    is_active: bool
    member_count: int = 0
    manager_count: int = 0
    created_at: datetime
    updated_at: datetime
    children: list["DepartmentInfo"] = []

    model_config = {"from_attributes": True}


class DepartmentMemberInfo(BaseModel):
    id: str
    org_id: str
    department_id: str
    user_id: str
    role: str
    is_primary: bool
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DepartmentMemberAddRequest(BaseModel):
    user_id: str
    role: str = "member"
    is_primary: bool = False


class DepartmentMemberUpdateRequest(BaseModel):
    role: str | None = None
    is_primary: bool | None = None


class OrgRequiredGeneAdd(BaseModel):
    gene_id: str


class OrgRequiredGeneInfo(BaseModel):
    id: str
    gene_id: str
    gene_name: str
    gene_slug: str
    gene_short_description: str | None = None
    gene_icon: str | None = None
    gene_category: str | None = None

    model_config = {"from_attributes": True}


class CheckAgentGenesResponse(BaseModel):
    missing_genes: list[OrgRequiredGeneInfo]
    all_installed: bool
    genehub_web_url: str
