<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOrgStore } from '@/stores/org'
import { Plus, Pencil, Trash2, Loader2, KeyRound, ChevronDown } from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { resolveApiErrorMessage } from '@/i18n/error'
import { PROVIDERS, PROVIDER_LABELS } from '@/utils/llmProviders'

const { t } = useI18n()
const orgStore = useOrgStore()
const toast = useToast()
const { confirm } = useConfirm()

const orgId = computed(() => orgStore.currentOrgId)

interface OrgLlmKey {
  id: string
  org_id: string
  provider: string
  label: string
  api_key_masked: string
  base_url: string | null
  org_token_limit: number | null
  system_token_limit: number | null
  is_active: boolean
  usage_total_tokens: number
  created_by: string
}

const NON_CODEX_PROVIDERS = PROVIDERS.filter(p => p !== 'codex')

const keys = ref<OrgLlmKey[]>([])
const loading = ref(true)

const showDialog = ref(false)
const isEditing = ref(false)
const editingKey = ref<OrgLlmKey | null>(null)
const saving = ref(false)
const providerDropdownOpen = ref(false)

const form = ref({
  provider: '',
  label: '',
  api_key: '',
  base_url: '',
  org_token_limit: '',
  system_token_limit: '',
  is_active: true,
})

function resetForm() {
  form.value = { provider: '', label: '', api_key: '', base_url: '', org_token_limit: '', system_token_limit: '', is_active: true }
}

async function fetchKeys() {
  if (!orgId.value) return
  loading.value = true
  try {
    const res = await api.get(`/orgs/${orgId.value}/llm-keys`)
    keys.value = res.data.data ?? []
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  resetForm()
  isEditing.value = false
  editingKey.value = null
  showDialog.value = true
}

function openEdit(key: OrgLlmKey) {
  editingKey.value = key
  isEditing.value = true
  form.value = {
    provider: key.provider,
    label: key.label,
    api_key: '',
    base_url: key.base_url || '',
    org_token_limit: key.org_token_limit?.toString() ?? '',
    system_token_limit: key.system_token_limit?.toString() ?? '',
    is_active: key.is_active,
  }
  showDialog.value = true
}

async function handleSave() {
  if (!orgId.value) return
  saving.value = true
  try {
    if (isEditing.value && editingKey.value) {
      const payload: Record<string, any> = { label: form.value.label, is_active: form.value.is_active }
      if (form.value.api_key) payload.api_key = form.value.api_key
      if (form.value.base_url !== (editingKey.value.base_url || '')) payload.base_url = form.value.base_url || null
      payload.org_token_limit = form.value.org_token_limit ? Number(form.value.org_token_limit) : null
      payload.system_token_limit = form.value.system_token_limit ? Number(form.value.system_token_limit) : null
      await api.patch(`/orgs/${orgId.value}/llm-keys/${editingKey.value.id}`, payload)
      toast.success(t('orgSettings.llmKeysUpdated'))
    } else {
      await api.post(`/orgs/${orgId.value}/llm-keys`, {
        provider: form.value.provider,
        label: form.value.label,
        api_key: form.value.api_key,
        base_url: form.value.base_url || undefined,
        org_token_limit: form.value.org_token_limit ? Number(form.value.org_token_limit) : undefined,
        system_token_limit: form.value.system_token_limit ? Number(form.value.system_token_limit) : undefined,
      })
      toast.success(t('orgSettings.llmKeysCreated'))
    }
    showDialog.value = false
    await fetchKeys()
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e) || t(isEditing.value ? 'orgSettings.llmKeysUpdateFailed' : 'orgSettings.llmKeysCreateFailed'))
  } finally {
    saving.value = false
  }
}

async function handleDelete(key: OrgLlmKey) {
  const ok = await confirm({
    title: t('common.delete'),
    description: t('orgSettings.llmKeysDeleteConfirm'),
    variant: 'danger',
    confirmText: t('common.delete'),
  })
  if (!ok) return
  try {
    await api.delete(`/orgs/${orgId.value}/llm-keys/${key.id}`)
    toast.success(t('orgSettings.llmKeysDeleted'))
    await fetchKeys()
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e) || t('orgSettings.llmKeysDeleteFailed'))
  }
}

function formatTokens(n: number | null): string {
  if (n == null) return t('orgSettings.llmKeysNoLimit')
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toString()
}

function usagePercent(used: number, limit: number | null): number {
  if (!limit || limit === 0) return 0
  return Math.min(100, (used / limit) * 100)
}

const canSave = computed(() => {
  if (isEditing.value) return !!form.value.label
  return !!form.value.provider && !!form.value.label && !!form.value.api_key
})

onMounted(fetchKeys)
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <KeyRound class="w-5 h-5" />
          {{ t('orgSettings.llmKeysTitle') }}
        </h2>
        <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.llmKeysDescription') }}</p>
      </div>
      <button
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors"
        @click="openCreate"
      >
        <Plus class="w-4 h-4" />
        {{ t('orgSettings.llmKeysAdd') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty state -->
    <div v-else-if="keys.length === 0" class="text-center py-12">
      <KeyRound class="w-10 h-10 mx-auto text-muted-foreground/50 mb-3" />
      <p class="text-sm text-muted-foreground">{{ t('orgSettings.llmKeysEmpty') }}</p>
      <p class="text-xs text-muted-foreground/70 mt-1">{{ t('orgSettings.llmKeysEmptyHint') }}</p>
    </div>

    <!-- Key table -->
    <div v-else class="rounded-lg border border-border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border bg-muted/30">
            <th class="text-left px-4 py-2.5 font-medium text-muted-foreground">{{ t('orgSettings.llmKeysColProvider') }}</th>
            <th class="text-left px-4 py-2.5 font-medium text-muted-foreground">{{ t('orgSettings.llmKeysColLabel') }}</th>
            <th class="text-left px-4 py-2.5 font-medium text-muted-foreground">{{ t('orgSettings.llmKeysColKey') }}</th>
            <th class="text-left px-4 py-2.5 font-medium text-muted-foreground">{{ t('orgSettings.llmKeysColUsage') }}</th>
            <th class="text-left px-4 py-2.5 font-medium text-muted-foreground">{{ t('orgSettings.llmKeysColStatus') }}</th>
            <th class="text-left px-4 py-2.5 font-medium text-muted-foreground w-20">{{ t('orgSettings.llmKeysColActions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="key in keys" :key="key.id" class="border-b border-border last:border-0 hover:bg-muted/20 transition-colors">
            <td class="px-4 py-3">
              <span class="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-primary/10 text-primary">
                {{ PROVIDER_LABELS[key.provider] || key.provider }}
              </span>
            </td>
            <td class="px-4 py-3 font-medium">{{ key.label }}</td>
            <td class="px-4 py-3 font-mono text-xs text-muted-foreground">{{ key.api_key_masked }}</td>
            <td class="px-4 py-3">
              <div class="space-y-1">
                <div class="text-xs">
                  {{ formatTokens(key.usage_total_tokens) }} / {{ formatTokens(key.org_token_limit) }}
                </div>
                <div v-if="key.org_token_limit" class="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="usagePercent(key.usage_total_tokens, key.org_token_limit) > 90 ? 'bg-destructive' : 'bg-primary'"
                    :style="{ width: usagePercent(key.usage_total_tokens, key.org_token_limit) + '%' }"
                  />
                </div>
              </div>
            </td>
            <td class="px-4 py-3">
              <span
                class="inline-flex px-2 py-0.5 rounded text-xs font-medium"
                :class="key.is_active ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'"
              >
                {{ key.is_active ? t('orgSettings.llmKeysStatusActive') : t('orgSettings.llmKeysStatusInactive') }}
              </span>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center gap-1">
                <button
                  class="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                  @click="openEdit(key)"
                >
                  <Pencil class="w-3.5 h-3.5" />
                </button>
                <button
                  class="p-1.5 rounded hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                  @click="handleDelete(key)"
                >
                  <Trash2 class="w-3.5 h-3.5" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create / Edit Dialog -->
    <Teleport to="body">
      <div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showDialog = false" />
        <div class="relative w-full max-w-md mx-4 rounded-lg border border-border bg-card shadow-lg">
          <div class="px-6 pt-6 pb-4">
            <h3 class="text-lg font-semibold">
              {{ isEditing ? t('orgSettings.llmKeysEditTitle') : t('orgSettings.llmKeysAddTitle') }}
            </h3>
          </div>

          <div class="px-6 space-y-4">
            <!-- Provider (create only) -->
            <div v-if="!isEditing" class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.llmKeysProvider') }}</label>
              <div class="relative">
                <button
                  class="w-full flex items-center justify-between px-3 py-2 rounded-md border border-border bg-background text-sm hover:border-primary/50 transition-colors"
                  @click="providerDropdownOpen = !providerDropdownOpen"
                >
                  <span :class="form.provider ? '' : 'text-muted-foreground'">
                    {{ form.provider ? (PROVIDER_LABELS[form.provider] || form.provider) : t('orgSettings.llmKeysProvider') }}
                  </span>
                  <ChevronDown class="w-4 h-4 text-muted-foreground" />
                </button>
                <div
                  v-if="providerDropdownOpen"
                  class="absolute z-10 mt-1 w-full rounded-lg border border-border bg-card shadow-lg overflow-hidden"
                >
                  <button
                    v-for="p in NON_CODEX_PROVIDERS"
                    :key="p"
                    class="w-full px-4 py-2 text-left text-sm hover:bg-accent transition-colors"
                    @click="form.provider = p; providerDropdownOpen = false"
                  >
                    {{ PROVIDER_LABELS[p] || p }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Label -->
            <div class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.llmKeysLabel') }}</label>
              <input
                v-model="form.label"
                class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                :placeholder="t('orgSettings.llmKeysLabelPlaceholder')"
              />
            </div>

            <!-- API Key -->
            <div class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.llmKeysApiKey') }}</label>
              <input
                v-model="form.api_key"
                type="password"
                class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                :placeholder="isEditing ? t('orgSettings.llmKeysApiKeyEditHint') : t('orgSettings.llmKeysApiKeyPlaceholder')"
              />
            </div>

            <!-- Base URL -->
            <div class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.llmKeysBaseUrl') }}</label>
              <input
                v-model="form.base_url"
                class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                :placeholder="t('orgSettings.llmKeysBaseUrlPlaceholder')"
              />
            </div>

            <!-- Token limits -->
            <div class="grid grid-cols-2 gap-3">
              <div class="space-y-1.5">
                <label class="text-sm font-medium">{{ t('orgSettings.llmKeysOrgTokenLimit') }}</label>
                <input
                  v-model="form.org_token_limit"
                  type="number"
                  class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  :placeholder="t('orgSettings.llmKeysOrgTokenLimitHint')"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-sm font-medium">{{ t('orgSettings.llmKeysSysTokenLimit') }}</label>
                <input
                  v-model="form.system_token_limit"
                  type="number"
                  class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  :placeholder="t('orgSettings.llmKeysSysTokenLimitHint')"
                />
              </div>
            </div>

            <!-- Active toggle (edit only) -->
            <div v-if="isEditing" class="flex items-center gap-2">
              <input type="checkbox" id="edit-active" v-model="form.is_active" class="accent-primary" />
              <label for="edit-active" class="text-sm cursor-pointer">{{ t('orgSettings.llmKeysStatusActive') }}</label>
            </div>
          </div>

          <div class="flex justify-end gap-2 px-6 py-4 mt-2">
            <button
              class="px-4 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              @click="showDialog = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!canSave || saving"
              @click="handleSave"
            >
              <span v-if="saving" class="flex items-center gap-1.5">
                <Loader2 class="w-3.5 h-3.5 animate-spin" />
                {{ t('common.saving') }}
              </span>
              <span v-else>{{ isEditing ? t('common.save') : t('common.create') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
