<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOrgStore } from '@/stores/org'
import { Settings, Loader2, KeyRound, Check, X } from 'lucide-vue-next'
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

interface ModelProvider {
  id: string
  org_id: string
  provider: string
  label: string | null
  api_key_masked: string
  base_url: string | null
  org_token_limit: number | null
  system_token_limit: number | null
  is_active: boolean
  usage_total_tokens: number
  created_by: string
}

const NON_CODEX_PROVIDERS = PROVIDERS.filter(p => p !== 'codex')

const providers = ref<ModelProvider[]>([])
const loading = ref(true)

const showDialog = ref(false)
const dialogProvider = ref('')
const isEditing = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)

const form = ref({
  api_key: '',
  base_url: '',
  org_token_limit: '',
  system_token_limit: '',
  is_active: true,
})

function resetForm() {
  form.value = { api_key: '', base_url: '', org_token_limit: '', system_token_limit: '', is_active: true }
}

function configuredMap(): Record<string, ModelProvider> {
  const map: Record<string, ModelProvider> = {}
  for (const p of providers.value) {
    map[p.provider] = p
  }
  return map
}

async function fetchProviders() {
  if (!orgId.value) return
  loading.value = true
  try {
    const res = await api.get(`/orgs/${orgId.value}/model-providers`)
    providers.value = res.data.data ?? []
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}

function openConfigure(providerName: string) {
  resetForm()
  dialogProvider.value = providerName
  const existing = configuredMap()[providerName]
  if (existing) {
    isEditing.value = true
    editingId.value = existing.id
    form.value = {
      api_key: '',
      base_url: existing.base_url || '',
      org_token_limit: existing.org_token_limit?.toString() ?? '',
      system_token_limit: existing.system_token_limit?.toString() ?? '',
      is_active: existing.is_active,
    }
  } else {
    isEditing.value = false
    editingId.value = null
  }
  showDialog.value = true
}

async function handleSave() {
  if (!orgId.value) return
  saving.value = true
  try {
    if (isEditing.value && editingId.value) {
      const payload: Record<string, any> = { is_active: form.value.is_active }
      if (form.value.api_key) payload.api_key = form.value.api_key
      payload.base_url = form.value.base_url || null
      payload.org_token_limit = form.value.org_token_limit ? Number(form.value.org_token_limit) : null
      payload.system_token_limit = form.value.system_token_limit ? Number(form.value.system_token_limit) : null
      await api.patch(`/orgs/${orgId.value}/model-providers/${editingId.value}`, payload)
      toast.success(t('orgSettings.llmKeysUpdated'))
    } else {
      await api.post(`/orgs/${orgId.value}/model-providers`, {
        provider: dialogProvider.value,
        api_key: form.value.api_key,
        base_url: form.value.base_url || undefined,
        org_token_limit: form.value.org_token_limit ? Number(form.value.org_token_limit) : undefined,
        system_token_limit: form.value.system_token_limit ? Number(form.value.system_token_limit) : undefined,
      })
      toast.success(t('orgSettings.llmKeysCreated'))
    }
    showDialog.value = false
    await fetchProviders()
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e) || t(isEditing.value ? 'orgSettings.llmKeysUpdateFailed' : 'orgSettings.llmKeysCreateFailed'))
  } finally {
    saving.value = false
  }
}

async function handleDelete(providerName: string) {
  const existing = configuredMap()[providerName]
  if (!existing) return
  const ok = await confirm({
    title: t('common.delete'),
    description: t('orgSettings.llmKeysDeleteConfirm'),
    variant: 'danger',
    confirmText: t('common.delete'),
  })
  if (!ok) return
  try {
    await api.delete(`/orgs/${orgId.value}/model-providers/${existing.id}`)
    toast.success(t('orgSettings.llmKeysDeleted'))
    await fetchProviders()
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e) || t('orgSettings.llmKeysDeleteFailed'))
  }
}

function formatTokens(n: number | null | undefined): string {
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
  if (isEditing.value) return true
  return !!form.value.api_key
})

onMounted(fetchProviders)
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold flex items-center gap-2">
        <KeyRound class="w-5 h-5" />
        {{ t('orgSettings.llmKeysTitle') }}
      </h2>
      <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.llmKeysDescription') }}</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="providerName in NON_CODEX_PROVIDERS"
        :key="providerName"
        class="rounded-lg border border-border bg-card p-4 hover:border-primary/30 transition-colors"
      >
        <div class="flex items-center justify-between mb-3">
          <span class="font-medium text-sm">{{ PROVIDER_LABELS[providerName] || providerName }}</span>
          <span
            v-if="configuredMap()[providerName]"
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
            :class="configuredMap()[providerName].is_active
              ? 'bg-green-500/10 text-green-500'
              : 'bg-muted text-muted-foreground'"
          >
            <Check v-if="configuredMap()[providerName].is_active" class="w-3 h-3" />
            <X v-else class="w-3 h-3" />
            {{ configuredMap()[providerName].is_active ? t('orgSettings.llmKeysConfigured') : t('orgSettings.llmKeysDisabled') }}
          </span>
        </div>

        <template v-if="configuredMap()[providerName]">
          <div class="space-y-2 text-xs text-muted-foreground">
            <div class="font-mono">{{ configuredMap()[providerName].api_key_masked }}</div>
            <div class="flex items-center gap-2">
              <span>{{ formatTokens(configuredMap()[providerName].usage_total_tokens) }} / {{ formatTokens(configuredMap()[providerName].org_token_limit) }}</span>
              <div v-if="configuredMap()[providerName].org_token_limit" class="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="usagePercent(configuredMap()[providerName].usage_total_tokens, configuredMap()[providerName].org_token_limit) > 90 ? 'bg-destructive' : 'bg-primary'"
                  :style="{ width: usagePercent(configuredMap()[providerName].usage_total_tokens, configuredMap()[providerName].org_token_limit) + '%' }"
                />
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-3">
            <button
              class="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              @click="openConfigure(providerName)"
            >
              <Settings class="w-3.5 h-3.5" />
              {{ t('orgSettings.llmKeysSettings') }}
            </button>
            <button
              class="px-3 py-1.5 rounded-md text-sm text-destructive hover:bg-destructive/10 transition-colors"
              @click="handleDelete(providerName)"
            >
              {{ t('common.delete') }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="text-xs text-muted-foreground/60 mb-3">{{ t('orgSettings.llmKeysNotConfigured') }}</div>
          <button
            class="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors"
            @click="openConfigure(providerName)"
          >
            {{ t('orgSettings.llmKeysConfigure') }}
          </button>
        </template>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showDialog = false" />
        <div class="relative w-full max-w-md mx-4 rounded-lg border border-border bg-card shadow-lg">
          <div class="px-6 pt-6 pb-4">
            <h3 class="text-lg font-semibold">
              {{ PROVIDER_LABELS[dialogProvider] || dialogProvider }}
              <span class="text-sm font-normal text-muted-foreground ml-2">
                {{ isEditing ? t('orgSettings.llmKeysEditTitle') : t('orgSettings.llmKeysAddTitle') }}
              </span>
            </h3>
          </div>

          <div class="px-6 space-y-4">
            <div class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.llmKeysApiKey') }}</label>
              <input
                v-model="form.api_key"
                type="password"
                class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                :placeholder="isEditing ? t('orgSettings.llmKeysApiKeyEditHint') : t('orgSettings.llmKeysApiKeyPlaceholder')"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.llmKeysBaseUrl') }}</label>
              <input
                v-model="form.base_url"
                class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                :placeholder="t('orgSettings.llmKeysBaseUrlPlaceholder')"
              />
            </div>

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
              <span v-else>{{ t('common.save') }}</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
