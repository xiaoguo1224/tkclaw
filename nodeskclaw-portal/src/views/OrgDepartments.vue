<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Building2, Loader2, Plus, Pencil, ShieldCheck, Trash2, UserCog, X } from 'lucide-vue-next'
import { useOrgStore, type DepartmentInfo, type DepartmentMemberInfo } from '@/stores/org'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { resolveApiErrorMessage } from '@/i18n/error'
import CustomSelect from '@/components/shared/CustomSelect.vue'

const { t } = useI18n()
const orgStore = useOrgStore()
const authStore = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()

const loading = ref(true)
const showDialog = ref(false)
const showManagerDialog = ref(false)
const editingDepartmentId = ref<string | null>(null)
const saving = ref(false)
const deletingId = ref<string | null>(null)
const managerDepartment = ref<FlatDepartment | null>(null)
const departmentMembers = ref<DepartmentMemberInfo[]>([])
const loadingManagers = ref(false)
const savingManager = ref(false)
const selectedManagerUserId = ref('')

const formName = ref('')
const formSlug = ref('')
const formParentId = ref<string | null>(null)
const formDescription = ref('')

const isOrgAdmin = computed(() => authStore.user?.portal_org_role === 'admin')

interface FlatDepartment {
  id: string
  name: string
  slug: string
  description: string
  parent_id: string | null
  member_count: number
  manager_count: number
  depth: number
}

function flattenDepartments(items: DepartmentInfo[], depth = 0): FlatDepartment[] {
  return items.flatMap(item => [
    {
      id: item.id,
      name: item.name,
      slug: item.slug,
      description: item.description,
      parent_id: item.parent_id,
      member_count: item.member_count,
      manager_count: item.manager_count,
      depth,
    },
    ...flattenDepartments(item.children || [], depth + 1),
  ])
}

const flatDepartments = computed(() => flattenDepartments(orgStore.departments))
const parentOptions = computed(() => [
  { value: '', label: t('orgDepartments.noParent') },
  ...flatDepartments.value
    .filter(item => item.id !== editingDepartmentId.value)
    .map(item => ({
      value: item.id,
      label: `${' '.repeat(item.depth * 2)}${item.name}`,
    })),
])

onMounted(async () => {
  if (!orgStore.currentOrgId) await orgStore.fetchCurrentOrg()
  if (orgStore.currentOrgId) {
    await orgStore.fetchDepartments()
    await orgStore.fetchMembers()
  }
  loading.value = false
})

function openCreateDialog() {
  editingDepartmentId.value = null
  formName.value = ''
  formSlug.value = ''
  formParentId.value = null
  formDescription.value = ''
  showDialog.value = true
}

function openEditDialog(item: FlatDepartment) {
  editingDepartmentId.value = item.id
  formName.value = item.name
  formSlug.value = item.slug
  formParentId.value = item.parent_id
  formDescription.value = item.description
  showDialog.value = true
}

function closeDialog() {
  showDialog.value = false
}

const managerCandidates = computed(() =>
  orgStore.members.map(member => ({
    value: member.user_id,
    label: `${member.user_name || t('orgMembers.unknownUser')} / ${member.user_email || ''}`,
  })),
)

const currentManagers = computed(() => departmentMembers.value.filter(item => item.role === 'manager'))

async function refreshDepartmentMembers() {
  if (!managerDepartment.value) return
  loadingManagers.value = true
  try {
    departmentMembers.value = await orgStore.fetchDepartmentMembers(managerDepartment.value.id)
  } finally {
    loadingManagers.value = false
  }
}

async function openManagerDialog(item: FlatDepartment) {
  managerDepartment.value = item
  selectedManagerUserId.value = ''
  showManagerDialog.value = true
  await refreshDepartmentMembers()
}

function closeManagerDialog() {
  showManagerDialog.value = false
  managerDepartment.value = null
  departmentMembers.value = []
  selectedManagerUserId.value = ''
}

async function handleAddManager() {
  if (!managerDepartment.value || !selectedManagerUserId.value) return
  savingManager.value = true
  try {
    const existing = departmentMembers.value.find(item => item.user_id === selectedManagerUserId.value)
    if (existing) {
      await orgStore.updateDepartmentMember(managerDepartment.value.id, existing.id, { role: 'manager' })
    } else {
      await orgStore.addDepartmentMember(managerDepartment.value.id, selectedManagerUserId.value, 'manager', false)
    }
    await refreshDepartmentMembers()
    selectedManagerUserId.value = ''
    toast.success(t('orgDepartments.managerUpdated'))
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('orgDepartments.managerUpdateFailed')))
  } finally {
    savingManager.value = false
  }
}

async function handleDemoteManager(member: DepartmentMemberInfo) {
  if (!managerDepartment.value) return
  savingManager.value = true
  try {
    await orgStore.updateDepartmentMember(managerDepartment.value.id, member.id, { role: 'member' })
    await refreshDepartmentMembers()
    toast.success(t('orgDepartments.managerUpdated'))
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('orgDepartments.managerUpdateFailed')))
  } finally {
    savingManager.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const payload = {
      name: formName.value.trim(),
      slug: formSlug.value.trim(),
      parent_id: formParentId.value || null,
      description: formDescription.value.trim(),
    }
    if (editingDepartmentId.value) {
      await orgStore.updateDepartment(editingDepartmentId.value, payload)
      toast.success(t('orgDepartments.updated'))
    } else {
      await orgStore.createDepartment(payload)
      toast.success(t('orgDepartments.created'))
    }
    closeDialog()
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('orgDepartments.saveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleDelete(item: FlatDepartment) {
  const ok = await confirm({
    title: t('orgDepartments.deleteTitle'),
    description: t('orgDepartments.deleteConfirm', { name: item.name }),
    variant: 'danger',
  })
  if (!ok) return
  deletingId.value = item.id
  try {
    await orgStore.deleteDepartment(item.id)
    toast.success(t('orgDepartments.deleted'))
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('orgDepartments.deleteFailed')))
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-base font-semibold">{{ t('orgDepartments.title') }}</h2>
        <p class="text-sm text-muted-foreground mt-0.5">{{ t('orgDepartments.subtitle') }}</p>
      </div>
      <button
        v-if="isOrgAdmin"
        class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="openCreateDialog"
      >
        <Plus class="w-4 h-4" />
        {{ t('orgDepartments.create') }}
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="flatDepartments.length === 0" class="text-center py-16 border border-dashed border-border rounded-2xl">
      <Building2 class="w-10 h-10 mx-auto text-muted-foreground/40 mb-3" />
      <p class="text-sm text-muted-foreground">{{ t('orgDepartments.empty') }}</p>
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="item in flatDepartments"
        :key="item.id"
        class="flex items-start justify-between gap-4 p-4 rounded-xl border border-border bg-card"
      >
        <div class="min-w-0 flex-1" :style="{ paddingLeft: `${item.depth * 20}px` }">
          <div class="flex items-center gap-2">
            <span class="font-medium text-sm">{{ item.name }}</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{{ item.slug }}</span>
          </div>
          <p v-if="item.description" class="text-xs text-muted-foreground mt-1">{{ item.description }}</p>
          <div class="flex items-center gap-3 mt-2 text-[11px] text-muted-foreground">
            <span>{{ t('orgDepartments.memberCount', { count: item.member_count }) }}</span>
            <span>{{ t('orgDepartments.managerCount', { count: item.manager_count }) }}</span>
          </div>
        </div>
        <div v-if="isOrgAdmin" class="flex items-center gap-2 shrink-0">
          <button class="p-1.5 rounded-md hover:bg-muted transition-colors" @click="openManagerDialog(item)">
            <UserCog class="w-4 h-4" />
          </button>
          <button class="p-1.5 rounded-md hover:bg-muted transition-colors" @click="openEditDialog(item)">
            <Pencil class="w-4 h-4" />
          </button>
          <button
            class="p-1.5 rounded-md hover:bg-red-500/10 text-muted-foreground hover:text-red-400 transition-colors"
            :disabled="deletingId === item.id"
            @click="handleDelete(item)"
          >
            <Loader2 v-if="deletingId === item.id" class="w-4 h-4 animate-spin" />
            <Trash2 v-else class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="closeDialog">
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-md p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ editingDepartmentId ? t('orgDepartments.editTitle') : t('orgDepartments.createTitle') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="closeDialog">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="space-y-2">
            <label class="text-sm text-muted-foreground">{{ t('orgDepartments.nameLabel') }}</label>
            <input v-model="formName" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <div class="space-y-2">
            <label class="text-sm text-muted-foreground">{{ t('orgDepartments.slugLabel') }}</label>
            <input v-model="formSlug" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <div class="space-y-2">
            <label class="text-sm text-muted-foreground">{{ t('orgDepartments.parentLabel') }}</label>
            <CustomSelect
              :model-value="formParentId || ''"
              :options="parentOptions"
              trigger-class="w-full justify-between"
              @update:model-value="(value: string | null) => { formParentId = value || null }"
            />
          </div>
          <div class="space-y-2">
            <label class="text-sm text-muted-foreground">{{ t('orgDepartments.descriptionLabel') }}</label>
            <textarea v-model="formDescription" rows="3" class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors" @click="closeDialog">
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!formName.trim() || !formSlug.trim() || saving"
              @click="handleSave"
            >
              <Loader2 v-if="saving" class="w-4 h-4 animate-spin inline mr-1" />
              {{ t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="showManagerDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="closeManagerDialog">
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-xl p-6 space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-semibold text-base">{{ t('orgDepartments.managerTitle') }}</h3>
              <p class="text-sm text-muted-foreground mt-1">{{ managerDepartment?.name }}</p>
            </div>
            <button class="text-muted-foreground hover:text-foreground" @click="closeManagerDialog">
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="space-y-2">
            <label class="text-sm text-muted-foreground">{{ t('orgDepartments.managerSelectLabel') }}</label>
            <div class="flex gap-2">
              <CustomSelect
                :model-value="selectedManagerUserId"
                :options="managerCandidates"
                trigger-class="flex-1 justify-between"
                @update:model-value="(value: string | null) => { selectedManagerUserId = value || '' }"
              />
              <button
                class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="!selectedManagerUserId || savingManager"
                @click="handleAddManager"
              >
                <Loader2 v-if="savingManager" class="w-4 h-4 animate-spin" />
                <span v-else>{{ t('orgDepartments.setManager') }}</span>
              </button>
            </div>
          </div>

          <div class="space-y-2">
            <div class="text-sm text-muted-foreground">{{ t('orgDepartments.currentManagers') }}</div>
            <div v-if="loadingManagers" class="flex justify-center py-10">
              <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
            <div v-else-if="currentManagers.length === 0" class="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-xl">
              {{ t('orgDepartments.noManagers') }}
            </div>
            <div v-else class="space-y-2">
              <div
                v-for="member in currentManagers"
                :key="member.id"
                class="flex items-center justify-between gap-3 rounded-xl border border-border px-3 py-3"
              >
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium truncate">{{ member.user_name }}</span>
                    <span class="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                      <ShieldCheck class="w-3 h-3" />
                      {{ t('orgDepartments.managerBadge') }}
                    </span>
                  </div>
                  <p class="text-xs text-muted-foreground truncate mt-1">{{ member.user_email }}</p>
                </div>
                <button
                  class="px-3 py-1.5 rounded-lg border border-border text-xs hover:bg-accent transition-colors disabled:opacity-50"
                  :disabled="savingManager"
                  @click="handleDemoteManager(member)"
                >
                  {{ t('orgDepartments.removeManager') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
