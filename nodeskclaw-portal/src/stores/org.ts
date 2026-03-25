import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import { useAuthStore } from './auth'

export interface OrgInfo {
  id: string
  name: string
  slug: string
  plan: string
  max_instances: number
  max_cpu_total: string
  max_mem_total: string
  max_storage_total: string
  cluster_id: string | null
  cluster_name?: string | null
  is_active: boolean
  member_count: number
  created_at: string
  updated_at: string
}

export interface MemberInfo {
  id: string
  user_id: string
  org_id: string
  role: string
  is_super_admin: boolean
  user_name: string | null
  user_email: string | null
  user_avatar_url: string | null
  primary_department_id: string | null
  primary_department_name: string | null
  secondary_department_ids: string[]
  secondary_departments: string[]
  is_department_manager: boolean
  created_at: string
}

export interface DepartmentInfo {
  id: string
  org_id: string
  parent_id: string | null
  name: string
  slug: string
  description: string
  sort_order: number
  is_active: boolean
  member_count: number
  manager_count: number
  created_at: string
  updated_at: string
  children: DepartmentInfo[]
}

export interface OrgUsage {
  instance_count: number
  instance_limit: number
  cpu_used: string
  cpu_limit: string
  mem_used: string
  mem_limit: string
  storage_used: string
  storage_limit: string
}

export const useOrgStore = defineStore('org', () => {
  const currentOrg = ref<OrgInfo | null>(null)
  const members = ref<MemberInfo[]>([])
  const departments = ref<DepartmentInfo[]>([])
  const usage = ref<OrgUsage | null>(null)
  const loading = ref(false)

  const currentOrgId = computed(() => currentOrg.value?.id ?? null)

  async function fetchMyOrg() {
    try {
      const res = await api.get('/orgs/my')
      const orgs: OrgInfo[] = res.data.data ?? []

      const authStore = useAuthStore()
      if (authStore.user?.current_org_id) {
        currentOrg.value = orgs.find(o => o.id === authStore.user!.current_org_id) ?? null
      }
      if (!currentOrg.value && orgs.length > 0) {
        currentOrg.value = orgs[0]
      }
    } catch (e) {
      console.warn('[orgStore] fetchMyOrg 失败:', e)
    }
  }

  async function fetchCurrentOrg() {
    try {
      const res = await api.get('/orgs/current')
      currentOrg.value = res.data.data
    } catch (e) {
      console.warn('[orgStore] fetchCurrentOrg 失败:', e)
    }
  }

  async function updateOrgName(name: string) {
    const res = await api.put('/orgs/current/name', { name })
    currentOrg.value = res.data.data
    return res.data.data
  }

  // ── 成员管理 ──

  async function fetchMembers() {
    if (!currentOrgId.value) return
    loading.value = true
    try {
      const res = await api.get(`/orgs/${currentOrgId.value}/members`)
      members.value = res.data.data ?? []
    } finally {
      loading.value = false
    }
  }

  async function fetchDepartments() {
    if (!currentOrgId.value) return
    const res = await api.get(`/orgs/${currentOrgId.value}/departments`)
    departments.value = res.data.data ?? []
  }

  async function createDepartment(payload: {
    name: string
    slug: string
    parent_id?: string | null
    description?: string
    sort_order?: number
    is_active?: boolean
  }) {
    if (!currentOrgId.value) return
    const res = await api.post(`/orgs/${currentOrgId.value}/departments`, payload)
    await fetchDepartments()
    return res.data.data as DepartmentInfo
  }

  async function updateDepartment(departmentId: string, payload: Record<string, unknown>) {
    if (!currentOrgId.value) return
    const res = await api.put(`/orgs/${currentOrgId.value}/departments/${departmentId}`, payload)
    await fetchDepartments()
    return res.data.data as DepartmentInfo
  }

  async function deleteDepartment(departmentId: string) {
    if (!currentOrgId.value) return
    await api.delete(`/orgs/${currentOrgId.value}/departments/${departmentId}`)
    await fetchDepartments()
  }

  async function addMember(
    userId: string,
    role: string = 'member',
    primaryDepartmentId?: string | null,
    secondaryDepartmentIds: string[] = [],
  ) {
    if (!currentOrgId.value) return
    const res = await api.post(`/orgs/${currentOrgId.value}/members`, {
      user_id: userId,
      role,
      primary_department_id: primaryDepartmentId ?? null,
      secondary_department_ids: secondaryDepartmentIds,
    })
    members.value.push(res.data.data)
    return res.data.data
  }

  async function updateMemberRole(membershipId: string, role: string) {
    if (!currentOrgId.value) return
    const res = await api.put(`/orgs/${currentOrgId.value}/members/${membershipId}`, { role })
    const idx = members.value.findIndex(m => m.id === membershipId)
    if (idx >= 0) members.value[idx] = res.data.data
    return res.data.data
  }

  async function removeMember(membershipId: string) {
    if (!currentOrgId.value) return
    await api.delete(`/orgs/${currentOrgId.value}/members/${membershipId}`)
    members.value = members.value.filter(m => m.id !== membershipId)
  }

  async function updateMemberDepartments(
    membershipId: string,
    primaryDepartmentId: string | null,
    secondaryDepartmentIds: string[],
  ) {
    if (!currentOrgId.value) return
    const res = await api.put(`/orgs/${currentOrgId.value}/members/${membershipId}/departments`, {
      primary_department_id: primaryDepartmentId,
      secondary_department_ids: secondaryDepartmentIds,
    })
    const idx = members.value.findIndex(m => m.id === membershipId)
    if (idx >= 0) members.value[idx] = res.data.data
    return res.data.data
  }

  // ── 用量 ──

  async function fetchUsage() {
    loading.value = true
    try {
      const res = await api.get('/billing/usage')
      usage.value = res.data.data
    } finally {
      loading.value = false
    }
  }

  return {
    currentOrg,
    currentOrgId,
    members,
    departments,
    usage,
    loading,
    fetchMyOrg,
    fetchCurrentOrg,
    updateOrgName,
    fetchMembers,
    fetchDepartments,
    createDepartment,
    updateDepartment,
    deleteDepartment,
    addMember,
    updateMemberRole,
    updateMemberDepartments,
    removeMember,
    fetchUsage,
  }
})
