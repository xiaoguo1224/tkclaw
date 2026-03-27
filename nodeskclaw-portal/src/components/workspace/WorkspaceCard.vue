<script setup lang="ts">
import { computed } from 'vue'
import { Bot, Building2, Users } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import MiniHexPreview from './MiniHexPreview.vue'
import type { WorkspaceListItem } from '@/stores/workspace'

const props = defineProps<{ workspace: WorkspaceListItem }>()
const emit = defineEmits<{ (e: 'click'): void }>()
const { t } = useI18n()

const statusSummary = computed(() => {
  const agents = props.workspace.agents || []
  const active = agents.filter((a) => a.status === 'running' || a.status === 'active').length
  if (agents.length === 0) return ''
  if (active === agents.length) return t('workspaceCard.allActive')
  return t('workspaceCard.activeCount', { active, total: agents.length })
})

const departmentSummary = computed(() => {
  const departmentNames = props.workspace.department_names || []
  if (!departmentNames.length) return t('workspaceCard.noDepartments')
  return departmentNames.join(' / ')
})
</script>

<template>
  <div
    class="group relative bg-card border border-border rounded-xl overflow-hidden cursor-pointer hover:border-primary/30 transition-all hover:shadow-lg hover:shadow-primary/5"
    @click="emit('click')"
  >
    <!-- Mini 3D preview area -->
    <div class="h-36 bg-linear-to-b from-primary/5 to-transparent flex items-center justify-center overflow-hidden">
      <MiniHexPreview :agents="workspace.agents" :color="workspace.color" />
    </div>

    <!-- Info -->
    <div class="p-4 space-y-2">
      <div class="flex items-center gap-2">
        <div
          class="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
          :style="{ backgroundColor: workspace.color + '22', color: workspace.color }"
        >
          <Bot v-if="workspace.icon === 'bot'" class="w-4 h-4" />
          <span v-else>{{ workspace.icon }}</span>
        </div>
        <div class="flex-1 min-w-0">
          <h3 class="font-semibold text-sm truncate">{{ workspace.name }}</h3>
          <p class="text-xs text-muted-foreground truncate">{{ workspace.description || t('workspaceCard.noDescription') }}</p>
        </div>
      </div>

      <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Building2 class="w-3 h-3" />
        <span class="truncate">{{ t('workspaceCard.departmentsLabel') }}: {{ departmentSummary }}</span>
      </div>

      <div class="flex items-center gap-3 text-xs text-muted-foreground">
        <span class="flex items-center gap-1">
          <Bot class="w-3 h-3" />
          {{ t('workspaceCard.agentCount', { count: workspace.agent_count }) }}
        </span>
        <span class="flex items-center gap-1">
          <Users class="w-3 h-3" />
          {{ t('workspaceCard.memberCount', { count: workspace.member_count || 0 }) }}
        </span>
        <span>{{ statusSummary }}</span>
      </div>
    </div>
  </div>
</template>
