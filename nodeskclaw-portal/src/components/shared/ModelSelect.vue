<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Search, X, ChevronDown, Loader2, RefreshCw, PenLine } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

export interface ModelItem {
  id: string
  name: string
  context_window?: number | null
  max_tokens?: number | null
  input?: string[] | null
}

const props = withDefaults(defineProps<{
  provider: string
  modelValue: ModelItem | null
  disabled?: boolean
  allowManualInput?: boolean
}>(), {
  allowManualInput: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: ModelItem | null]
  'fetch-models': [provider: string, callback: (models: ModelItem[], error?: string) => void]
}>()

const open = ref(false)
const search = ref('')
const loading = ref(false)
const errorMsg = ref('')
const availableModels = ref<ModelItem[]>([])
const containerRef = ref<HTMLDivElement>()

const manualMode = ref(false)
const manualInput = ref('')
const manualError = ref('')
const manualInputRef = ref<HTMLInputElement>()

const filtered = computed(() => {
  if (!search.value) return availableModels.value
  const q = search.value.toLowerCase()
  return availableModels.value.filter(m =>
    m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)
  )
})

function select(model: ModelItem) {
  if (props.modelValue?.id === model.id) {
    emit('update:modelValue', null)
  } else {
    emit('update:modelValue', model)
  }
  open.value = false
  manualMode.value = false
}

function clear() {
  emit('update:modelValue', null)
}

function loadModels() {
  loading.value = true
  errorMsg.value = ''
  emit('fetch-models', props.provider, (models: ModelItem[], error?: string) => {
    availableModels.value = models
    errorMsg.value = error ?? ''
    loading.value = false
  })
}

function handleOpen() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value && availableModels.value.length === 0) {
    loadModels()
  }
}

function onClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    open.value = false
    manualMode.value = false
  }
}

function enterManualMode() {
  manualMode.value = true
  manualInput.value = ''
  manualError.value = ''
  nextTick(() => manualInputRef.value?.focus())
}

function confirmManualInput() {
  const trimmed = manualInput.value.trim()
  if (!trimmed) {
    manualError.value = t('llm.modelIdEmpty')
    return
  }
  emit('update:modelValue', { id: trimmed, name: trimmed })
  open.value = false
  manualMode.value = false
}

function cancelManualMode() {
  manualMode.value = false
  manualInput.value = ''
  manualError.value = ''
}

onMounted(() => document.addEventListener('click', onClickOutside, true))
onUnmounted(() => document.removeEventListener('click', onClickOutside, true))

watch(() => props.provider, () => {
  availableModels.value = []
  search.value = ''
  manualMode.value = false
})
</script>

<template>
  <div ref="containerRef" class="relative">
    <label class="text-xs text-muted-foreground mb-1 block">{{ t('llm.model') }}</label>

    <div
      class="h-[38px] flex items-center gap-1.5 px-3 rounded-lg border bg-card text-sm cursor-pointer transition-colors"
      :class="[
        disabled ? 'opacity-50 cursor-not-allowed border-border' : 'hover:border-primary/50 border-border',
        open ? 'ring-2 ring-primary/50 border-primary' : ''
      ]"
      @click="handleOpen"
    >
      <template v-if="modelValue">
        <span class="flex-1 font-mono text-xs truncate">{{ modelValue.id }}</span>
        <button
          class="text-muted-foreground hover:text-destructive transition-colors shrink-0"
          @click.stop="clear"
        >
          <X class="w-3.5 h-3.5" />
        </button>
      </template>
      <span v-else class="flex-1 text-muted-foreground text-sm">{{ t('llm.selectModel') }}</span>
      <ChevronDown class="w-4 h-4 text-muted-foreground shrink-0 transition-transform" :class="open ? 'rotate-180' : ''" />
    </div>

    <div
      v-if="open"
      class="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg overflow-hidden"
    >
      <!-- Manual input mode -->
      <div v-if="manualMode" class="p-3 space-y-2">
        <div class="flex items-center gap-2">
          <input
            ref="manualInputRef"
            v-model="manualInput"
            type="text"
            :placeholder="t('llm.manualInputPlaceholder')"
            class="flex-1 bg-transparent text-sm outline-none border border-border rounded-md px-2.5 py-1.5 placeholder:text-muted-foreground focus:border-primary/50 focus:ring-1 focus:ring-primary/50"
            @click.stop
            @keydown.enter.stop="confirmManualInput"
            @keydown.escape.stop="cancelManualMode"
          />
        </div>
        <p v-if="manualError" class="text-[10px] text-destructive">{{ manualError }}</p>
        <div class="flex justify-end gap-2">
          <button
            class="px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors rounded-md"
            @click.stop="cancelManualMode"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            class="px-2.5 py-1 text-xs text-primary-foreground bg-primary hover:bg-primary/90 transition-colors rounded-md"
            @click.stop="confirmManualInput"
          >
            {{ t('common.confirm') }}
          </button>
        </div>
      </div>

      <!-- Normal dropdown -->
      <template v-else>
        <div class="flex items-center gap-2 px-3 py-2 border-b border-border">
          <Search class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <input
            v-model="search"
            type="text"
            :placeholder="t('llm.searchModel')"
            class="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            @click.stop
          />
          <button
            class="text-muted-foreground hover:text-foreground transition-colors"
            :title="t('llm.refreshModels')"
            @click.stop="loadModels"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="loading ? 'animate-spin' : ''" />
          </button>
        </div>

        <div class="max-h-60 overflow-y-auto">
          <div v-if="loading" class="flex items-center justify-center py-6">
            <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
          <div v-else-if="filtered.length === 0" class="py-4 text-center text-xs text-muted-foreground space-y-2">
            <div>{{ search ? t('llm.noMatchingModels') : t('llm.noAvailableModels') }}</div>
            <div v-if="errorMsg && !search" class="text-destructive">{{ errorMsg }}</div>
            <button
              v-if="allowManualInput && !search"
              class="inline-flex items-center gap-1 text-primary hover:text-primary/80 transition-colors"
              @click.stop="enterManualMode"
            >
              <PenLine class="w-3 h-3" />
              {{ t('llm.manualInputModel') }}
            </button>
          </div>
          <template v-else>
            <button
              v-for="m in filtered"
              :key="m.id"
              class="w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent transition-colors"
              :class="modelValue?.id === m.id ? 'bg-primary/5' : ''"
              @click.stop="select(m)"
            >
              <div
                class="w-4 h-4 rounded-full border flex items-center justify-center shrink-0 transition-colors"
                :class="modelValue?.id === m.id ? 'border-primary' : 'border-muted-foreground/40'"
              >
                <div v-if="modelValue?.id === m.id" class="w-2 h-2 rounded-full bg-primary" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="font-mono text-xs truncate">{{ m.id }}</div>
                <div v-if="m.name !== m.id" class="text-[10px] text-muted-foreground truncate">{{ m.name }}</div>
              </div>
              <span v-if="m.context_window" class="text-[10px] text-muted-foreground shrink-0">
                {{ (m.context_window / 1000).toFixed(0) }}k ctx
              </span>
            </button>
            <button
              v-if="allowManualInput"
              class="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors border-t border-border"
              @click.stop="enterManualMode"
            >
              <PenLine class="w-3.5 h-3.5" />
              {{ t('llm.manualInputModel') }}
            </button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>
