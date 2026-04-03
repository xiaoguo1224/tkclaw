<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { Bot, User } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  modelValue: string
  textareaEl: HTMLTextAreaElement | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: string): void
}>()

const store = useWorkspaceStore()

interface MentionCandidate {
  type: 'agent' | 'human'
  id: string
  name: string
}

const showPicker = ref(false)
const query = ref('')
const selectedIdx = ref(0)
const atStartPos = ref(-1)

const candidates = computed<MentionCandidate[]>(() => {
  const agents: MentionCandidate[] = (store.currentWorkspace?.agents || []).map(a => ({
    type: 'agent',
    id: a.instance_id,
    name: a.display_name || a.name,
  }))
  const humans: MentionCandidate[] = (store.members || []).map(m => ({
    type: 'human',
    id: m.user_id,
    name: m.user_name,
  }))
  return [...agents, ...humans]
})

const filtered = computed(() => {
  const q = query.value.toLowerCase()
  if (!q) return candidates.value
  return candidates.value.filter(c => c.name.toLowerCase().includes(q))
})

watch(filtered, () => {
  selectedIdx.value = 0
})

function onInput() {
  const el = props.textareaEl
  if (!el) return
  const cursor = el.selectionStart ?? 0
  const text = props.modelValue
  const before = text.slice(0, cursor)

  const atIdx = before.lastIndexOf('@')
  if (atIdx === -1) {
    showPicker.value = false
    return
  }
  const charBeforeAt = atIdx > 0 ? before[atIdx - 1] : ' '
  if (charBeforeAt !== ' ' && charBeforeAt !== '\n' && atIdx !== 0) {
    showPicker.value = false
    return
  }
  const fragment = before.slice(atIdx + 1)
  if (fragment.includes(' ') || fragment.includes('\n')) {
    showPicker.value = false
    return
  }
  query.value = fragment
  atStartPos.value = atIdx
  showPicker.value = true
}

function select(candidate: MentionCandidate) {
  const start = atStartPos.value
  if (start < 0) return
  const el = props.textareaEl
  const cursor = el?.selectionStart ?? props.modelValue.length
  const before = props.modelValue.slice(0, start)
  const after = props.modelValue.slice(cursor)
  const insertText = `@${candidate.type}:${candidate.id} `
  emit('update:modelValue', before + insertText + after)
  showPicker.value = false

  nextTick(() => {
    if (el) {
      const newPos = before.length + insertText.length
      el.selectionStart = newPos
      el.selectionEnd = newPos
      el.focus()
    }
  })
}

function onKeydown(e: KeyboardEvent) {
  if (!showPicker.value || filtered.value.length === 0) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIdx.value = (selectedIdx.value + 1) % filtered.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIdx.value = (selectedIdx.value - 1 + filtered.value.length) % filtered.value.length
  } else if (e.key === 'Enter' || e.key === 'Tab') {
    e.preventDefault()
    select(filtered.value[selectedIdx.value])
  } else if (e.key === 'Escape') {
    e.preventDefault()
    showPicker.value = false
  }
}

defineExpose({ onInput, onKeydown })
</script>

<template>
  <div v-if="showPicker && filtered.length > 0" class="absolute z-20 bottom-full mb-1 left-0 w-64 max-h-48 overflow-y-auto bg-popover border border-border rounded-lg shadow-lg">
    <button
      v-for="(c, idx) in filtered"
      :key="`${c.type}-${c.id}`"
      class="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left transition-colors"
      :class="idx === selectedIdx ? 'bg-white/[0.07] text-foreground' : 'hover:bg-white/[0.04]'"
      @mousedown.prevent="select(c)"
    >
      <Bot v-if="c.type === 'agent'" class="w-3.5 h-3.5 text-primary shrink-0" />
      <User v-else class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
      <span class="truncate">{{ c.name }}</span>
      <span class="ml-auto text-xs text-muted-foreground shrink-0">{{ c.type === 'agent' ? 'AI' : '' }}</span>
    </button>
  </div>
</template>
