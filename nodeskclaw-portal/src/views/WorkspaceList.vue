<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Loader2, Bot } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import WorkspaceCard from '@/components/workspace/WorkspaceCard.vue'
import CustomSelect from '@/components/shared/CustomSelect.vue'
import api from '@/services/api'

const router = useRouter()
const store = useWorkspaceStore()
const authStore = useAuthStore()
const orgStore = useOrgStore()
const { t } = useI18n()
const selectedDepartmentId = ref('')
const showChannelReminderDialog = ref(false)
const channelReminderNeverAgain = ref(false)
const channelReminderInstanceId = ref('')
const channelReminderInstanceName = ref('')
const POST_LOGIN_FIRST_LANDING_KEY = 'portal_post_login_first_landing_pending'

const departmentOptions = computed(() => [
  { value: '', label: t('workspaceList.allDepartments') },
  ...store.filterDepartments.map(item => ({
    value: item.id,
    label: `${' '.repeat(item.depth * 2)}${item.name}`,
  })),
])

onMounted(async () => {
  await store.fetchWorkspaceFilterDepartments()
  if (
    selectedDepartmentId.value
    && !store.filterDepartments.some(item => item.id === selectedDepartmentId.value)
  ) {
    selectedDepartmentId.value = ''
  }
  await store.fetchWorkspaces(selectedDepartmentId.value || null)
  await checkDefaultAiChannelReminderOnFirstLanding()
})

watch(selectedDepartmentId, async value => {
  await store.fetchWorkspaces(value || null)
})

watch(
  () => store.filterDepartments,
  (items) => {
    if (selectedDepartmentId.value && !items.some(item => item.id === selectedDepartmentId.value)) {
      selectedDepartmentId.value = ''
    }
  },
)

function openWorkspace(id: string) {
  router.push(`/workspace/${id}`)
}

function createNew() {
  router.push('/workspace/create')
}

function consumePostLoginFirstLandingFlag() {
  const pending = sessionStorage.getItem(POST_LOGIN_FIRST_LANDING_KEY) === '1'
  if (pending) {
    sessionStorage.removeItem(POST_LOGIN_FIRST_LANDING_KEY)
  }
  return pending
}

function getNeverAgainStorageKey(userId: string, orgId: string, instanceId: string) {
  return `portal_channel_reminder_skip:${userId}:${orgId}:${instanceId}`
}

function hasConfiguredChannel(configs: Record<string, unknown>) {
  const values = Object.values(configs)
  if (values.length === 0) return false
  return values.some((value) => {
    if (value && typeof value === 'object') {
      return Object.keys(value as Record<string, unknown>).length > 0
    }
    return Boolean(value)
  })
}

async function checkDefaultAiChannelReminderOnFirstLanding() {
  if (!consumePostLoginFirstLandingFlag()) return
  const userId = authStore.user?.id
  const orgId = authStore.user?.current_org_id
  if (!userId || !orgId) return

  const member = await orgStore.fetchCurrentMember()
  const defaultInstanceId = member?.default_ai_instance_id
  if (!defaultInstanceId) return

  const skipKey = getNeverAgainStorageKey(userId, orgId, defaultInstanceId)
  if (localStorage.getItem(skipKey) === '1') return

  try {
    const res = await api.get(`/instances/${defaultInstanceId}/channel-configs`)
    const configs = (res.data?.data ?? {}) as Record<string, unknown>
    if (hasConfiguredChannel(configs)) return
    channelReminderInstanceId.value = defaultInstanceId
    channelReminderInstanceName.value = member?.default_ai_instance_name || ''
    showChannelReminderDialog.value = true
  } catch {
    showChannelReminderDialog.value = false
  }
}

function closeChannelReminderDialog() {
  if (channelReminderNeverAgain.value) {
    const userId = authStore.user?.id
    const orgId = authStore.user?.current_org_id
    const instanceId = channelReminderInstanceId.value
    if (userId && orgId && instanceId) {
      localStorage.setItem(getNeverAgainStorageKey(userId, orgId, instanceId), '1')
    }
  }
  showChannelReminderDialog.value = false
}

function goConfigureDefaultAiChannel() {
  const targetInstanceId = channelReminderInstanceId.value
  closeChannelReminderDialog()
  if (!targetInstanceId) return
  router.push(`/instances/${targetInstanceId}/channels`)
}
</script>

<template>
  <div class="max-w-5xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">{{ t('workspaceList.title') }}</h1>
        <p class="text-sm text-muted-foreground mt-1">{{ t('workspaceList.subtitle') }}</p>
      </div>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="createNew"
      >
        <Plus class="w-4 h-4" />
        {{ t('workspaceList.createNew') }}
      </button>
    </div>

    <div class="mb-6 max-w-xs">
      <label class="text-sm font-medium block mb-2">{{ t('workspaceList.departmentFilter') }}</label>
      <CustomSelect
        :model-value="selectedDepartmentId"
        :options="departmentOptions"
        trigger-class="w-full justify-between"
        @update:model-value="(value: string | null) => { selectedDepartmentId = value || '' }"
      />
      <p v-if="store.filterDepartments.length === 0" class="text-xs text-muted-foreground mt-2">
        {{ t('workspaceList.noDepartmentOptions') }}
      </p>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="store.workspaces.length === 0"
      class="text-center py-20 space-y-4"
    >
      <div class="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto text-2xl">
        <Bot class="w-8 h-8 text-primary" />
      </div>
      <h3 class="text-lg font-semibold">{{ t('workspaceList.emptyTitle') }}</h3>
      <p class="text-sm text-muted-foreground max-w-sm mx-auto">
        {{ selectedDepartmentId ? t('workspaceList.emptyByDepartment') : t('workspaceList.emptyDescription') }}
      </p>
      <button
        class="mt-4 px-6 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="createNew"
      >
        {{ t('workspaceList.createFirst') }}
      </button>
    </div>

    <!-- Grid -->
    <div
      v-else
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <WorkspaceCard
        v-for="ws in store.workspaces"
        :key="ws.id"
        :workspace="ws"
        @click="openWorkspace(ws.id)"
      />
    </div>

    <div v-if="showChannelReminderDialog" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="closeChannelReminderDialog" />
      <div class="relative z-10 w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl">
        <h3 class="text-lg font-semibold">{{ t('workspaceList.channelReminder.title') }}</h3>
        <p class="mt-2 text-sm text-muted-foreground">
          {{ t('workspaceList.channelReminder.description', { name: channelReminderInstanceName || t('common.instance') }) }}
        </p>
        <label class="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
          <input v-model="channelReminderNeverAgain" type="checkbox" class="h-4 w-4 rounded border-border" />
          <span>{{ t('workspaceList.channelReminder.neverAgain') }}</span>
        </label>
        <div class="mt-6 flex justify-end gap-2">
          <button
            class="px-3 py-2 rounded-md text-sm border border-border hover:bg-muted/60 transition-colors"
            @click="closeChannelReminderDialog"
          >
            {{ t('workspaceList.channelReminder.later') }}
          </button>
          <button
            class="px-3 py-2 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            @click="goConfigureDefaultAiChannel"
          >
            {{ t('workspaceList.channelReminder.goConfig') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
