<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { AlertCircle, CheckCircle2, Clock, DollarSign, Loader2, Play } from 'lucide-vue-next'
import { useWorkspaceStore, type TaskInfo } from '@/stores/workspace'
import { useI18n } from 'vue-i18n'

type ActiveTaskStatus = 'pending' | 'in_progress' | 'done' | 'blocked'
type TaskBucketKey = ActiveTaskStatus

interface TaskBucketState {
  items: TaskInfo[]
  page: number
  total: number
  hasMore: boolean
  loading: boolean
  initialized: boolean
  requestSeq: number
}

const ACTIVE_BUCKET_KEYS: ActiveTaskStatus[] = ['pending', 'in_progress', 'done', 'blocked']
const PAGE_SIZE = 20
const LOAD_MORE_THRESHOLD = 160

const props = defineProps<{
  workspaceId: string
}>()

const { t } = useI18n()
const store = useWorkspaceStore()

const columns = computed(() => [
  { key: 'pending' as const, label: t('blackboard.taskPending'), icon: Clock, color: 'text-yellow-500' },
  { key: 'in_progress' as const, label: t('blackboard.taskInProgress'), icon: Play, color: 'text-blue-500' },
  { key: 'done' as const, label: t('blackboard.taskDone'), icon: CheckCircle2, color: 'text-green-500' },
  { key: 'blocked' as const, label: t('blackboard.taskBlocked'), icon: AlertCircle, color: 'text-red-500' },
])

function createBucketState(): TaskBucketState {
  return {
    items: [],
    page: 0,
    total: 0,
    hasMore: true,
    loading: false,
    initialized: false,
    requestSeq: 0,
  }
}

const taskBuckets = reactive<Record<TaskBucketKey, TaskBucketState>>({
  pending: createBucketState(),
  in_progress: createBucketState(),
  done: createBucketState(),
  blocked: createBucketState(),
})

const scrollContainers: Record<TaskBucketKey, HTMLElement | null> = {
  pending: null,
  in_progress: null,
  done: null,
  blocked: null,
}

const editingValueTaskId = ref<string | null>(null)
const valueInput = ref<number | null>(null)
const refreshTimer = ref<number | null>(null)

function priorityBadgeClass(priority: string) {
  const map: Record<string, string> = {
    urgent: 'bg-red-500/20 text-red-400',
    high: 'bg-orange-500/20 text-orange-400',
    medium: 'bg-blue-500/20 text-blue-400',
    low: 'bg-zinc-500/20 text-zinc-400',
  }
  return map[priority] || map.medium
}

function mergeTasks(currentItems: TaskInfo[], nextItems: TaskInfo[]) {
  if (currentItems.length === 0) return nextItems
  const seen = new Set(currentItems.map(task => task.id))
  const merged = [...currentItems]
  for (const task of nextItems) {
    if (seen.has(task.id)) continue
    seen.add(task.id)
    merged.push(task)
  }
  return merged
}

function resetBucketState(bucketKey: TaskBucketKey) {
  const state = taskBuckets[bucketKey]
  state.items = []
  state.page = 0
  state.total = 0
  state.hasMore = true
  state.loading = false
  state.initialized = false
  state.requestSeq += 1
  scrollContainers[bucketKey]?.scrollTo({ top: 0 })
}

function setScrollContainer(bucketKey: TaskBucketKey, element: unknown) {
  const domElement = element instanceof HTMLElement
    ? element
    : (
        typeof element === 'object'
        && element !== null
        && '$el' in element
        && (element as { $el?: unknown }).$el instanceof HTMLElement
      )
      ? (element as { $el: HTMLElement }).$el
      : null
  scrollContainers[bucketKey] = domElement
  if (scrollContainers[bucketKey]) {
    void nextTick(() => maybeLoadMore(bucketKey))
  }
}

function isInitialLoading(bucketKey: TaskBucketKey) {
  const state = taskBuckets[bucketKey]
  return state.loading && state.items.length === 0
}

function isValueEditable(_bucketKey: TaskBucketKey, task: TaskInfo) {
  return task.status === 'done'
}

async function loadBucket(bucketKey: TaskBucketKey, reset = false) {
  const state = taskBuckets[bucketKey]
  if (!reset && (!state.hasMore || state.loading)) return

  if (reset) resetBucketState(bucketKey)

  const requestSeq = state.requestSeq + 1
  const nextPage = reset ? 1 : state.page + 1
  state.requestSeq = requestSeq
  state.loading = true

  try {
    const response = await store.fetchTasksPaginated(props.workspaceId, {
      bucket: 'column',
      status: bucketKey,
      page: nextPage,
      pageSize: PAGE_SIZE,
    })

    if (taskBuckets[bucketKey].requestSeq !== requestSeq) return

    state.items = nextPage === 1
      ? response.items
      : mergeTasks(state.items, response.items)
    state.page = response.pagination.page
    state.total = response.pagination.total
    state.hasMore = state.items.length < response.pagination.total
    state.initialized = true
  } catch (error) {
    console.error('load task bucket error:', error)
    if (taskBuckets[bucketKey].requestSeq === requestSeq) {
      state.initialized = true
      state.hasMore = false
    }
  } finally {
    if (taskBuckets[bucketKey].requestSeq === requestSeq) {
      state.loading = false
      await nextTick()
      maybeLoadMore(bucketKey)
    }
  }
}

async function refreshAllBuckets() {
  editingValueTaskId.value = null
  valueInput.value = null
  await Promise.all(
    ACTIVE_BUCKET_KEYS.map(bucketKey => loadBucket(bucketKey, true)),
  )
}

function maybeLoadMore(bucketKey: TaskBucketKey, element?: HTMLElement | null) {
  const state = taskBuckets[bucketKey]
  const container = element || scrollContainers[bucketKey]
  if (!container || !state.initialized || state.loading || !state.hasMore) return
  const remaining = container.scrollHeight - container.scrollTop - container.clientHeight
  if (remaining <= LOAD_MORE_THRESHOLD) {
    void loadBucket(bucketKey)
  }
}

function handleBucketScroll(bucketKey: TaskBucketKey, event: Event) {
  maybeLoadMore(bucketKey, event.target as HTMLElement)
}

function scheduleRefresh() {
  if (refreshTimer.value !== null) {
    window.clearTimeout(refreshTimer.value)
  }
  refreshTimer.value = window.setTimeout(() => {
    refreshTimer.value = null
    void refreshAllBuckets()
  }, 120)
}

function startValueEdit(task: TaskInfo) {
  editingValueTaskId.value = task.id
  valueInput.value = task.actual_value
}

async function saveValue(taskId: string) {
  if (valueInput.value != null) {
    await store.updateTask(props.workspaceId, taskId, { actual_value: valueInput.value })
  }
  editingValueTaskId.value = null
}

watch(
  () => props.workspaceId,
  () => {
    void refreshAllBuckets()
  },
  { immediate: true },
)

watch(
  () => store.taskEventVersion,
  () => {
    if (store.lastTaskEvent?.workspace_id !== props.workspaceId) return
    scheduleRefresh()
  },
)

onBeforeUnmount(() => {
  if (refreshTimer.value !== null) {
    window.clearTimeout(refreshTimer.value)
  }
})

defineExpose({ refresh: refreshAllBuckets })
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-muted-foreground">{{ t('blackboard.tasks') }}</h3>
    </div>

    <div class="grid grid-cols-4 gap-3">
      <div
        v-for="col in columns"
        :key="col.key"
        class="flex h-[25rem] min-h-0 flex-col rounded-xl border border-border/50 bg-muted/20"
      >
        <div class="flex items-center gap-1.5 border-b border-border/40 px-3 py-2.5">
          <component :is="col.icon" class="h-3.5 w-3.5" :class="col.color" />
          <span class="text-xs font-medium">{{ col.label }}</span>
          <span class="text-xs text-muted-foreground">({{ taskBuckets[col.key].total }})</span>
        </div>

        <div
          :ref="el => setScrollContainer(col.key, el)"
          class="flex-1 min-h-0 overflow-y-auto px-2.5 pb-2.5"
          @scroll.passive="handleBucketScroll(col.key, $event)"
        >
          <div class="space-y-2 pt-2.5">
            <div v-if="isInitialLoading(col.key)" class="flex justify-center py-8">
              <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
            </div>

            <template v-else-if="taskBuckets[col.key].items.length > 0">
              <div
                v-for="task in taskBuckets[col.key].items"
                :key="task.id"
                class="space-y-1.5 rounded-lg border border-border/50 bg-background/80 p-2.5 text-xs"
              >
                <div class="flex items-start justify-between gap-1">
                  <span class="text-sm font-medium leading-tight">{{ task.title }}</span>
                  <span
                    v-if="task.priority"
                    class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium"
                    :class="priorityBadgeClass(task.priority)"
                  >
                    {{ task.priority }}
                  </span>
                </div>

                <p v-if="task.description" class="line-clamp-2 text-muted-foreground">{{ task.description }}</p>

                <div v-if="task.assignee_name" class="text-muted-foreground">
                  {{ t('blackboard.assignee') }}: {{ task.assignee_name }}
                </div>

                <div class="flex flex-wrap items-center gap-2 text-muted-foreground">
                  <span v-if="task.estimated_value != null">{{ t('blackboard.estimatedValue') }}: {{ task.estimated_value }}</span>
                  <span v-if="task.actual_value != null">{{ t('blackboard.actualValue') }}: {{ task.actual_value }}</span>
                  <span v-if="task.token_cost != null">Token: {{ task.token_cost }}</span>
                </div>

                <div v-if="task.blocker_reason && task.status === 'blocked'" class="text-[11px] text-red-400">
                  {{ task.blocker_reason }}
                </div>

                <div v-if="isValueEditable(col.key, task)" class="flex items-center gap-2 pt-1">
                  <template v-if="editingValueTaskId === task.id">
                    <input
                      v-model.number="valueInput"
                      type="number"
                      step="0.1"
                      min="0"
                      class="h-5 w-16 rounded border border-border bg-background px-1 text-[11px]"
                      :placeholder="t('blackboard.actualValue')"
                      @keyup.enter="saveValue(task.id)"
                      @keyup.escape="editingValueTaskId = null"
                    />
                    <button
                      class="text-[11px] text-green-400 transition-colors hover:text-green-300"
                      @click="saveValue(task.id)"
                    >
                      {{ t('blackboard.save') }}
                    </button>
                  </template>
                  <button
                    v-else
                    class="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                    @click="startValueEdit(task)"
                  >
                    <DollarSign class="h-3 w-3" />
                    {{ t('blackboard.annotateValue') }}
                  </button>
                </div>
              </div>
            </template>

            <div v-else class="py-6 text-center text-xs text-muted-foreground">
              {{ t('blackboard.noTasks') }}
            </div>

            <div v-if="taskBuckets[col.key].loading && taskBuckets[col.key].items.length > 0" class="flex justify-center py-2">
              <Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
