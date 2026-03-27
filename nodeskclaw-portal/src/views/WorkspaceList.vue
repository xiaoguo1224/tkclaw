<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Loader2, Bot } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useWorkspaceStore } from '@/stores/workspace'
import WorkspaceCard from '@/components/workspace/WorkspaceCard.vue'
import CustomSelect from '@/components/shared/CustomSelect.vue'

const router = useRouter()
const store = useWorkspaceStore()
const { t } = useI18n()
const selectedDepartmentId = ref('')

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
  </div>
</template>
