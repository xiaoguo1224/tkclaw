<script setup lang="ts">
import { ref, computed, watch, inject, type ComputedRef, type Ref } from 'vue'
import { Loader2, Brain, Key, Trash2, Plus, RefreshCw, HardDrive, Save, ChevronDown, Check, Link, Star, X, AlertTriangle, Cpu } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import ModelSelect from '@/components/shared/ModelSelect.vue'
import type { ModelItem } from '@/components/shared/ModelSelect.vue'
import api from '@/services/api'
import { getRuntimeCaps } from '@/utils/runtimeCapabilities'
import {
  BUILTIN_PROVIDERS, WORKING_PLAN_PROVIDERS, ALL_KNOWN_PROVIDERS,
  isCodexProvider, defaultModelForProvider,
} from '@/utils/llmProviders'

const instanceId = inject<ComputedRef<string>>('instanceId')!
const instanceRuntime = inject<ComputedRef<string>>('instanceRuntime', computed(() => 'openclaw'))
const runtimeSupported = computed(() => getRuntimeCaps(instanceRuntime.value).llmConfig)
const instanceOrgId = inject<Ref<string | null>>('instanceOrgId')!
const myInstanceRole = inject<Ref<string | null>>('myInstanceRole', ref(null))
const ROLE_LEVEL: Record<string, number> = { viewer: 10, user: 20, editor: 30, admin: 40 }
const canEdit = computed(() => (ROLE_LEVEL[myInstanceRole.value ?? ''] ?? 0) >= ROLE_LEVEL.editor)

const loading = ref(true)
const saving = ref(false)
const restarting = ref(false)
const error = ref('')
const successMsg = ref('')
const nfsError = ref('')
const dataSource = ref('')
const dirty = ref(false)

// ── Constants ──

const LOCAL_MODEL_PROVIDER = 'volcengine-plan'
const LOCAL_MODEL_BASE_URL = 'https://ark.cn-beijing.volces.com/api/coding/v3'
const LOCAL_MODEL_API_KEY = '090f8038-0d0c-40f7-8d9b-8a2b35b6ad72'
const LOCAL_MODEL_API_TYPE = 'openai-completions'
const LOCAL_MODEL_DEFAULT: ModelItem = {
  id: 'kimi-k2.5',
  name: 'kimi-k2.5',
}

const PROVIDERS = ['minimax-openai', 'minimax-anthropic', 'openai', 'anthropic', 'gemini', 'openrouter', 'bailian-code', 'volcano-code'] as const
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
  'minimax-openai': 'MiniMax-OpenAI (CN)',
  'minimax-anthropic': 'MiniMax-Anthropic (CN)',
  'bailian-code': '阿里百炼 Code Plan',
  'volcano-code': '火山 Code Plan',
  [LOCAL_MODEL_PROVIDER]: t('llm.localModelLabel'),
}

const PROVIDER_DEFAULT_URLS: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com/v1',
  openrouter: 'https://openrouter.ai/api/v1',
  'minimax-openai': 'https://api.minimaxi.com/v1',
  'minimax-anthropic': 'https://api.minimaxi.com/anthropic',
  'bailian-code': 'https://coding.dashscope.aliyuncs.com/v1',
  'volcano-code': 'https://ark.cn-beijing.volces.com/api/v3',
}

// ── Types ──

interface PersonalKey {
  id: string
  provider: string
  api_key_masked: string
  base_url: string | null
  api_type: string | null
  is_active: boolean
}

interface ProviderConfig {
  provider: string
  keySource: 'org' | 'personal'
  personalKeyNew: string
  personalKeyMasked: string
  hasExistingPersonalKey: boolean
  baseUrl: string
  apiType: string
  isCustom: boolean
  showBaseUrl: boolean
  selectedModel: ModelItem | null
  isDefault: boolean
}

function normalizeModelItem(model: ModelItem | null): ModelItem | null {
  if (!model) return null
  return {
    ...model,
    input: model.input?.length ? [...model.input] : ['text', 'image'],
  }
}

function updateSelectedModel(cfg: ProviderConfig, model: ModelItem | null) {
  cfg.selectedModel = normalizeModelItem(model)
  dirty.value = true
}

function updateSelectedModelContextWindow(cfg: ProviderConfig, rawValue: string) {
  if (!cfg.selectedModel) return
  const value = rawValue.trim()
  const parsed = Number(value)
  cfg.selectedModel.context_window = Number.isFinite(parsed) && parsed > 0 ? parsed : null
  dirty.value = true
}

function toggleSelectedModelInput(cfg: ProviderConfig, inputType: 'text' | 'image', checked: boolean) {
  if (!cfg.selectedModel) return
  const current = new Set(cfg.selectedModel.input?.length ? cfg.selectedModel.input : ['text', 'image'])
  if (checked) {
    current.add(inputType)
  } else {
    current.delete(inputType)
  }
  cfg.selectedModel.input = Array.from(current)
  dirty.value = true
}

const orgKeyProviders = ref<Set<string>>(new Set())

const isWorkingPlanAvailable = (provider: string) =>
  WORKING_PLAN_PROVIDERS.has(provider) && orgKeyProviders.value.has(provider)

// ── State ──

const providerConfigs = ref<ProviderConfig[]>([])
const personalKeys = ref<PersonalKey[]>([])
const newProviderOpen = ref(false)
const showCustomForm = ref(false)
const customSlug = ref('')
const customSlugError = ref('')

const unusedProviders = computed(() =>
  PROVIDERS.filter(p => !providerConfigs.value.some(c => c.provider === p))
)

function personalKeyForProvider(provider: string) {
  return personalKeys.value.find(k => k.provider === provider)
}

// ── Data loading ──

async function loadAll() {
  loading.value = true
  error.value = ''
  nfsError.value = ''
  successMsg.value = ''

  try {
    const orgKeysPromise = instanceOrgId.value
      ? api.get(`/orgs/${instanceOrgId.value}/available-llm-keys`).catch(() => ({ data: { data: [] } }))
      : Promise.resolve({ data: { data: [] } })
    const [configsResult, keysResult, orgKeysResult] = await Promise.allSettled([
      api.get(`/instances/${instanceId.value}/llm-configs`),
      api.get('/users/me/llm-keys'),
      orgKeysPromise,
    ])
    if (orgKeysResult.status === 'fulfilled') {
      const keys = orgKeysResult.value.data.data ?? []
      orgKeyProviders.value = new Set(keys.map((k: any) => k.provider))
    }

    if (configsResult.status === 'fulfilled') {
      dataSource.value = 'pod'
    } else {
      const e = configsResult.reason
      const status = e?.response?.status
      const msg = e?.response?.data?.message || ''
      if (status === 503 && (msg.includes('NFS') || msg.includes('nfs') || msg.includes('mount') || msg.includes('挂载'))) {
        nfsError.value = msg
      }
    }

    if (keysResult.status === 'fulfilled') {
      personalKeys.value = keysResult.value.data.data ?? []
    }

    const podConfigs: {
      provider: string; key_source: string; selected_models?: any[];
      personal_key_masked?: string; base_url?: string | null; api_type?: string | null;
      is_default?: boolean;
    }[] = configsResult.status === 'fulfilled' ? (configsResult.value.data.data ?? []) : []

    const configs: ProviderConfig[] = []
    for (const c of podConfigs) {
      const pk = personalKeyForProvider(c.provider)
      const isCustom = !ALL_KNOWN_PROVIDERS.has(c.provider)
      configs.push({
        provider: c.provider,
        keySource: isCodexProvider(c.provider)
          ? 'personal'
          : ((c.key_source === 'org' || c.key_source === 'personal') ? c.key_source : 'org'),
        personalKeyNew: '',
        personalKeyMasked: pk?.api_key_masked ?? c.personal_key_masked ?? '',
        hasExistingPersonalKey: !!pk,
        baseUrl: c.base_url ?? pk?.base_url ?? '',
        apiType: c.api_type ?? pk?.api_type ?? (isCustom ? 'openai-completions' : ''),
        isCustom,
        showBaseUrl: isCustom || !!(c.base_url || pk?.base_url),
        selectedModel: normalizeModelItem((c.selected_models ?? [])[0] ?? defaultModelForProvider(c.provider)),
        isDefault: !!c.is_default,
      })
    }

    if (!configs.some(c => c.isDefault) && configs.length > 0) {
      configs[0].isDefault = true
    }

    for (const c of configs) {
      if (c.keySource === 'org' && !isWorkingPlanAvailable(c.provider)) {
        c.keySource = 'personal'
      }
    }
    providerConfigs.value = configs
    dirty.value = false
  } catch (e: any) {
    error.value = e?.response?.data?.message || '加载配置失败'
  } finally {
    loading.value = false
  }
}

// ── Provider management ──

function addProvider(provider: string) {
  if (providerConfigs.value.some(c => c.provider === provider)) return
  const pk = personalKeyForProvider(provider)
  const isCustom = !ALL_KNOWN_PROVIDERS.has(provider)
  providerConfigs.value.push({
    provider,
    keySource: isCodexProvider(provider)
      ? 'personal'
      : (isCustom ? 'personal' : (isWorkingPlanAvailable(provider) ? 'org' : 'personal')),
    personalKeyNew: '',
    personalKeyMasked: pk?.api_key_masked ?? '',
    hasExistingPersonalKey: !!pk,
    baseUrl: pk?.base_url ?? '',
    apiType: pk?.api_type ?? (isCustom ? 'openai-completions' : ''),
    isCustom,
    showBaseUrl: isCustom || !!pk?.base_url,
    selectedModel: normalizeModelItem(defaultModelForProvider(provider)),
    isDefault: providerConfigs.value.length === 0,
  })
  newProviderOpen.value = false
  dirty.value = true
}

function addLocalModelProvider() {
  if (providerConfigs.value.some(c => c.provider === LOCAL_MODEL_PROVIDER)) return
  providerConfigs.value.push({
    provider: LOCAL_MODEL_PROVIDER,
    keySource: 'personal',
    personalKeyNew: LOCAL_MODEL_API_KEY,
    personalKeyMasked: '',
    hasExistingPersonalKey: false,
    baseUrl: LOCAL_MODEL_BASE_URL,
    apiType: LOCAL_MODEL_API_TYPE,
    isCustom: true,
    showBaseUrl: true,
    selectedModel: normalizeModelItem({ ...LOCAL_MODEL_DEFAULT }),
    isDefault: providerConfigs.value.length === 0,
  })
  newProviderOpen.value = false
  showCustomForm.value = false
  customSlug.value = ''
  customSlugError.value = ''
  dirty.value = true
}

function addCustomProvider() {
  newProviderOpen.value = false
  const slug = customSlug.value.trim()
  if (!slug) return
  if (!/^[a-z][a-z0-9-]*[a-z0-9]$/.test(slug) || slug.length < 2 || slug.length > 32) {
    customSlugError.value = t('llm.providerSlugInvalid')
    return
  }
  if (ALL_KNOWN_PROVIDERS.has(slug) || providerConfigs.value.some(c => c.provider === slug)) {
    customSlugError.value = t('llm.providerSlugConflict')
    return
  }
  providerConfigs.value.push({
    provider: slug,
    keySource: 'personal',
    personalKeyNew: '',
    personalKeyMasked: '',
    hasExistingPersonalKey: false,
    baseUrl: '',
    apiType: 'openai-completions',
    isCustom: true,
    showBaseUrl: true,
    selectedModel: normalizeModelItem(null),
    isDefault: providerConfigs.value.length === 0,
  })
  customSlug.value = ''
  customSlugError.value = ''
  showCustomForm.value = false
  dirty.value = true
}

async function handleFetchModels(provider: string, callback: (models: ModelItem[], error?: string) => void) {
  const cfg = providerConfigs.value.find(c => c.provider === provider)
  const params: Record<string, string> = {}
  if (cfg?.keySource === 'personal' && cfg.personalKeyNew) {
    params.api_key = cfg.personalKeyNew
  }
  if (cfg?.baseUrl) {
    params.base_url = cfg.baseUrl
  }
  if (instanceOrgId.value) {
    params.org_id = instanceOrgId.value
  }
  try {
    const res = await api.get(`/llm/providers/${provider}/models`, { params })
    const msg = res.data?.message ?? ''
    callback(res.data.data?.models ?? [], msg || undefined)
  } catch (e: any) {
    callback([], e?.response?.data?.message ?? t('llm.fetchModelsFailed'))
  }
}

function removeProvider(idx: number) {
  const removedDefault = providerConfigs.value[idx]?.isDefault
  providerConfigs.value.splice(idx, 1)
  if (removedDefault && providerConfigs.value.length > 0) {
    providerConfigs.value[0].isDefault = true
  }
  dirty.value = true
}

function markDirty() {
  dirty.value = true
}

function setDefaultProvider(provider: string) {
  let changed = false
  for (const cfg of providerConfigs.value) {
    const next = cfg.provider === provider
    if (cfg.isDefault !== next) {
      cfg.isDefault = next
      changed = true
    }
  }
  if (changed) {
    dirty.value = true
  }
}

// ── Validation ──

function validateConfigs(): string | null {
  for (const cfg of providerConfigs.value) {
    const label = PROVIDER_LABELS[cfg.provider] || cfg.provider
    if (cfg.isCustom && !cfg.baseUrl) {
      return `${label}: Base URL ${t('common.noData')}`
    }
    if (cfg.keySource === 'personal' && !isCodexProvider(cfg.provider)) {
      if (!cfg.personalKeyNew && !cfg.hasExistingPersonalKey) {
        return `${label}: 请输入个人 API Key`
      }
    }
    if (!cfg.selectedModel) {
      return `${label}: 请选择一个模型`
    }
  }
  return null
}

const canSave = computed(() => {
  if (!dirty.value || providerConfigs.value.length === 0) return false
  return providerConfigs.value.every(c => !!c.selectedModel)
})

// ── Save ──

async function handleSave() {
  const validationError = validateConfigs()
  if (validationError) {
    error.value = validationError
    return
  }

  saving.value = true
  error.value = ''
  successMsg.value = ''

  try {
    // 1. Upsert personal keys (new key, or base_url/api_type update for existing key)
    for (const cfg of providerConfigs.value) {
      if (cfg.keySource !== 'personal') continue
      const needsUpsert = isCodexProvider(cfg.provider) || cfg.personalKeyNew || cfg.baseUrl || cfg.isCustom
      if (!needsUpsert) continue
      await api.post('/users/me/llm-keys', {
        provider: cfg.provider,
        api_key: isCodexProvider(cfg.provider) ? undefined : (cfg.personalKeyNew || undefined),
        base_url: isCodexProvider(cfg.provider) ? null : (cfg.baseUrl || null),
        api_type: cfg.isCustom ? cfg.apiType : null,
      })
      if (cfg.personalKeyNew) {
        cfg.personalKeyMasked = cfg.personalKeyNew.length > 8
          ? cfg.personalKeyNew.slice(0, 6) + '***' + cfg.personalKeyNew.slice(-3)
          : cfg.personalKeyNew.slice(0, 2) + '***'
        cfg.personalKeyNew = ''
      } else if (isCodexProvider(cfg.provider)) {
        cfg.personalKeyMasked = t('llm.codexCliLabel')
      }
      cfg.hasExistingPersonalKey = true
    }

    // 2. Write configs directly to Pod file
    const defaultCfg = providerConfigs.value.find(c => c.isDefault) ?? providerConfigs.value[0]
    const defaultModel = defaultCfg?.selectedModel ?? (defaultCfg ? defaultModelForProvider(defaultCfg.provider) : null)
    const defaultModelPrimary = defaultCfg
      ? (defaultModel?.id ? `${defaultCfg.provider}/${defaultModel.id}` : defaultCfg.provider)
      : null
    await api.put(`/instances/${instanceId.value}/llm-configs`, {
      configs: providerConfigs.value.map(c => {
        const selectedModel = c.selectedModel ?? defaultModelForProvider(c.provider)
        return {
          provider: c.provider,
          key_source: c.keySource,
          selected_models: selectedModel ? [selectedModel] : undefined,
          base_url: isCodexProvider(c.provider) ? null : (c.baseUrl || null),
          api_type: c.isCustom ? c.apiType : null,
        }
      }),
      default_model_primary: defaultModelPrimary,
    })

    // 3. Restart runtime
    restarting.value = true
    const res = await api.post(`/instances/${instanceId.value}/restart-runtime`, null, { timeout: 120000 })
    const result = res.data.data
    if (result?.status === 'ok') {
      successMsg.value = '配置已保存，TClaw已重启'
    } else if (result?.status === 'timeout') {
      successMsg.value = '配置已保存，但 TClaw 重启超时，请检查AI 员工状态'
    } else {
      successMsg.value = '配置已保存'
      if (result?.message) {
        error.value = result.message
      }
    }

    dirty.value = false
    const pkRes = await api.get('/users/me/llm-keys')
    personalKeys.value = pkRes.data.data ?? []
  } catch (e: any) {
    error.value = e?.response?.data?.message || '保存失败'
  } finally {
    saving.value = false
    restarting.value = false
  }
}

watch(() => instanceId.value, (val) => {
  if (val) loadAll()
}, { immediate: true })
</script>

<template>
  <div>
    <div v-if="!runtimeSupported" class="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
      <AlertTriangle class="w-10 h-10 opacity-50" />
      <p class="text-sm">{{ t('instanceSettings.unsupportedRuntime') }}</p>
    </div>

    <div v-else-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Brain class="w-4 h-4 text-violet-400" />
          <h2 class="text-sm font-medium">大模型配置</h2>
          <span v-if="dataSource === 'nfs' && !nfsError" class="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
            NFS
          </span>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-xs hover:bg-card transition-colors"
            :disabled="saving || restarting"
            @click="loadAll"
          >
            <RefreshCw class="w-3 h-3" />
            刷新
          </button>
          <button
            v-if="providerConfigs.length > 0 && canEdit"
            :disabled="saving || restarting || !canSave"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition-colors"
            :class="canSave
              ? 'bg-primary text-primary-foreground hover:bg-primary/90'
              : 'bg-muted text-muted-foreground'"
            @click="handleSave"
          >
            <Loader2 v-if="saving || restarting" class="w-3 h-3 animate-spin" />
            <Save v-else class="w-3 h-3" />
            {{ restarting ? '重启中...' : saving ? '保存中...' : '保存并重启' }}
          </button>
        </div>
      </div>

      <!-- Status messages -->
      <div v-if="restarting" class="flex items-center gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
        <RefreshCw class="w-4 h-4 text-amber-500 animate-spin" />
        <span class="text-xs">TClaw 正在完成当前任务并重启...</span>
      </div>
      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
      <p v-if="successMsg" class="text-sm text-green-500">{{ successMsg }}</p>

      <!-- NFS error -->
      <div v-if="nfsError" class="flex flex-col items-center gap-3 py-10 text-center">
        <HardDrive class="w-8 h-8 text-destructive/60" />
        <p class="text-sm text-destructive">NFS 存储不可用</p>
        <p class="text-xs text-muted-foreground max-w-sm">{{ nfsError }}</p>
      </div>

      <!-- Provider list -->
      <template v-if="!nfsError">
        <!-- Empty state: provider grid -->
        <div v-if="providerConfigs.length === 0 && !saving" class="space-y-3">
          <p class="text-xs text-muted-foreground">
            当前AI 员工未配置大模型 Provider，选择一个开始配置
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="p in unusedProviders"
              :key="p"
              class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
              @click="addProvider(p)"
            >
              <div class="flex items-center gap-1.5">
                {{ PROVIDER_LABELS[p] || p }}
                <span v-if="WORKING_PLAN_PROVIDERS.has(p)" class="inline-flex items-center gap-0.5 text-[10px] text-amber-500">
                  <Star class="w-3 h-3 fill-amber-500 text-amber-500" />
                  Working Plan
                </span>
              </div>
            </button>
            <button
              class="px-4 py-3 rounded-lg border border-dashed border-violet-400/50 bg-card text-sm text-left hover:border-violet-400 hover:bg-violet-500/5 transition-colors text-violet-400 cursor-pointer"
              @click="showCustomForm = true"
            >
              <div class="flex items-center gap-1.5">
                <Plus class="w-3.5 h-3.5" />
                {{ t('llm.addCustomProvider') }}
              </div>
            </button>
            <button
              class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
              @click="addLocalModelProvider"
            >
              <div class="flex items-center gap-1.5">
                <Cpu class="w-3.5 h-3.5" />
                {{ t('llm.addLocalModel') }}
              </div>
            </button>
          </div>
        </div>

        <!-- Provider cards -->
        <div v-else class="space-y-3">
          <div
            v-for="(cfg, idx) in providerConfigs"
            :key="cfg.provider"
            class="rounded-lg border border-border bg-card p-4 space-y-3"
          >
            <!-- Provider header -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="font-medium text-sm">{{ PROVIDER_LABELS[cfg.provider] || cfg.provider }}</span>
                <span v-if="cfg.isCustom" class="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400">{{ t('llm.customProvider') }}</span>
                <span v-if="cfg.isDefault" class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-500">{{ t('instanceSettings.currentDefaultModel') }}</span>
              </div>
              <button
                class="text-muted-foreground hover:text-destructive transition-colors"
                @click="removeProvider(idx)"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>

            <!-- API type selector (custom only) -->
            <div v-if="cfg.isCustom" class="flex gap-4 text-sm">
              <label class="text-xs text-muted-foreground">{{ t('llm.apiType') }}:</label>
              <label class="flex items-center gap-1.5 cursor-pointer text-xs">
                <input type="radio" :name="`apitype-${cfg.provider}`" value="openai-completions" v-model="cfg.apiType" class="accent-primary" @change="markDirty" />
                {{ t('llm.apiTypeOpenai') }}
              </label>
              <label class="flex items-center gap-1.5 cursor-pointer text-xs">
                <input type="radio" :name="`apitype-${cfg.provider}`" value="anthropic-messages" v-model="cfg.apiType" class="accent-primary" @change="markDirty" />
                {{ t('llm.apiTypeAnthropic') }}
              </label>
            </div>

            <!-- Key source selection -->
            <div class="space-y-2">
              <div v-if="!cfg.isCustom && !isCodexProvider(cfg.provider)" class="flex gap-4 text-sm">
                <span class="relative group">
                  <label
                    class="flex items-center gap-1.5"
                    :class="isWorkingPlanAvailable(cfg.provider) ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'"
                  >
                    <input
                      type="radio"
                      :name="`ks-${cfg.provider}`"
                      value="org"
                      v-model="cfg.keySource"
                      class="accent-primary"
                      :disabled="!isWorkingPlanAvailable(cfg.provider)"
                      @change="markDirty"
                    />
                    Working Plan
                  </label>
                  <span
                    v-if="!isWorkingPlanAvailable(cfg.provider)"
                    class="pointer-events-none absolute z-50 top-full left-1/2 -translate-x-1/2 mt-1.5 whitespace-nowrap rounded bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md border border-border invisible group-hover:visible"
                  >
                    {{ WORKING_PLAN_PROVIDERS.has(cfg.provider) ? t('llm.workingPlanNotConfigured') : t('llm.workingPlanUnavailable') }}
                  </span>
                </span>
                <label class="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    :name="`ks-${cfg.provider}`"
                    value="personal"
                    v-model="cfg.keySource"
                    class="accent-primary"
                    @change="markDirty"
                  />
                  个人 Key
                </label>
              </div>

              <p v-else-if="isCodexProvider(cfg.provider)" class="text-xs text-muted-foreground pl-0.5">
                {{ t('llm.codexCliHint') }}
              </p>

              <!-- Working Plan hint -->
              <p v-if="!cfg.isCustom && cfg.keySource === 'org'" class="text-xs text-muted-foreground pl-0.5">
                使用组织统一配置的 Key，无需自行输入
              </p>

              <!-- Personal key -->
              <div v-if="cfg.keySource === 'personal'" class="space-y-1.5">
                <template v-if="isCodexProvider(cfg.provider)">
                  <div v-if="cfg.hasExistingPersonalKey" class="flex items-center gap-2 text-xs">
                    <Check class="w-3 h-3 text-green-400" />
                    <span class="text-muted-foreground">{{ t('llm.codexCliCurrentAuth') }}:</span>
                    <span class="font-mono">{{ cfg.personalKeyMasked }}</span>
                  </div>
                  <div class="rounded-md border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                    {{ t('llm.codexCliRuntimeHint') }}
                  </div>
                </template>
                <template v-else>
                  <div v-if="cfg.hasExistingPersonalKey" class="flex items-center gap-2 text-xs">
                    <Check class="w-3 h-3 text-green-400" />
                    <span class="text-muted-foreground">当前 Key:</span>
                    <span class="font-mono">{{ cfg.personalKeyMasked }}</span>
                  </div>
                  <div class="relative">
                    <Key class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                    <input
                      v-model="cfg.personalKeyNew"
                      type="password"
                      :placeholder="cfg.hasExistingPersonalKey ? '输入新 Key 以替换' : '输入 API Key'"
                      class="w-full pl-9 pr-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                      @input="markDirty"
                    />
                  </div>

                  <div v-if="cfg.isCustom || cfg.showBaseUrl">
                    <div class="relative">
                      <Link class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                      <input
                        v-model="cfg.baseUrl"
                        type="text"
                        :placeholder="cfg.isCustom ? t('llm.baseUrlPlaceholder') : t('llm.defaultBaseUrl', { url: PROVIDER_DEFAULT_URLS[cfg.provider] || '' })"
                        :class="cfg.isCustom ? 'pr-3' : 'pr-8'"
                        class="w-full pl-9 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                        @input="markDirty"
                      />
                      <button
                        v-if="!cfg.isCustom"
                        class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        @click="cfg.baseUrl = ''; cfg.showBaseUrl = false; markDirty()"
                      >
                        <X class="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <button
                    v-if="!cfg.isCustom && !cfg.showBaseUrl"
                    class="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    @click="cfg.showBaseUrl = true"
                  >
                    {{ t('llm.customBaseUrl') }}
                  </button>
                </template>
              </div>
            </div>

            <!-- Model selection -->
            <ModelSelect
              :provider="cfg.provider"
              :model-value="cfg.selectedModel"
              :allow-manual-input="!!cfg.isCustom"
              @fetch-models="handleFetchModels"
              @update:model-value="(value) => updateSelectedModel(cfg, value)"
            />
            <div v-if="cfg.selectedModel" class="space-y-2 rounded-md border border-border/60 bg-background/40 p-3">
              <div class="grid gap-3 md:grid-cols-2">
                <div class="space-y-1">
                  <label class="text-xs text-muted-foreground">{{ t('llm.contextWindow') }}</label>
                  <input
                    :value="cfg.selectedModel.context_window ?? ''"
                    type="number"
                    min="1"
                    :placeholder="t('llm.contextWindowPlaceholder')"
                    class="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                    @input="updateSelectedModelContextWindow(cfg, ($event.target as HTMLInputElement).value)"
                  />
                </div>
                <div class="space-y-1">
                  <label class="text-xs text-muted-foreground">{{ t('llm.modelInputTypes') }}</label>
                  <div class="flex h-[38px] items-center gap-4 rounded-md border border-border bg-background px-3">
                    <label class="flex items-center gap-1.5 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        value="text"
                        class="accent-primary"
                        :checked="cfg.selectedModel.input?.includes('text')"
                        @change="toggleSelectedModelInput(cfg, 'text', ($event.target as HTMLInputElement).checked)"
                      />
                      text
                    </label>
                    <label class="flex items-center gap-1.5 text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        value="image"
                        class="accent-primary"
                        :checked="cfg.selectedModel.input?.includes('image')"
                        @change="toggleSelectedModelInput(cfg, 'image', ($event.target as HTMLInputElement).checked)"
                      />
                      image
                    </label>
                  </div>
                </div>
              </div>
            </div>
            <div class="flex justify-end">
              <button
                type="button"
                class="inline-flex items-center gap-1.5 text-xs transition-colors"
                :class="cfg.isDefault ? 'text-amber-500' : 'text-muted-foreground hover:text-foreground'"
                :disabled="!cfg.selectedModel"
                @click="setDefaultProvider(cfg.provider)"
              >
                <Star class="w-3.5 h-3.5" :class="cfg.isDefault ? 'fill-amber-500 text-amber-500' : ''" />
                {{ cfg.isDefault ? t('instanceSettings.currentDefaultModel') : t('instanceSettings.setDefaultModel') }}
              </button>
            </div>
            <p v-if="(cfg.isCustom || isCodexProvider(cfg.provider) || !BUILTIN_PROVIDERS.has(cfg.provider)) && !cfg.selectedModel" class="text-[10px] text-amber-500">
              {{ t('llm.modelRequired') }}
            </p>
          </div>

          <!-- Add provider -->
          <div class="flex gap-2 items-start">
            <div v-if="unusedProviders.length > 0" class="relative">
              <button
                class="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                @click="newProviderOpen = !newProviderOpen"
              >
                <Plus class="w-3.5 h-3.5" />
                添加 Provider
                <ChevronDown class="w-3 h-3 transition-transform" :class="newProviderOpen ? 'rotate-180' : ''" />
              </button>
              <div
                v-if="newProviderOpen"
                class="absolute z-50 mt-1 w-56 rounded-lg border border-border bg-card shadow-lg overflow-hidden"
              >
                <button
                  v-for="p in unusedProviders"
                  :key="p"
                  class="w-full px-4 py-2 text-left text-sm hover:bg-accent transition-colors"
                  @click="addProvider(p)"
                >
                  <div class="flex items-center gap-1.5">
                    {{ PROVIDER_LABELS[p] || p }}
                    <span v-if="WORKING_PLAN_PROVIDERS.has(p)" class="inline-flex items-center gap-0.5 text-[10px] text-amber-500">
                      <Star class="w-3 h-3 fill-amber-500 text-amber-500" />
                      Working Plan
                    </span>
                  </div>
                </button>
              </div>
            </div>
            <button
              v-if="!providerConfigs.some(c => c.provider === LOCAL_MODEL_PROVIDER)"
              class="flex items-center gap-1 text-xs hover:text-foreground transition-colors cursor-pointer"
              @click="addLocalModelProvider"
            >
              <Cpu class="w-3.5 h-3.5" />
              {{ t('llm.addLocalModel') }}
            </button>
            <button
              class="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors cursor-pointer"
              @click="newProviderOpen = false; showCustomForm = true"
            >
              <Plus class="w-3.5 h-3.5" />
              {{ t('llm.addCustomProvider') }}
            </button>
          </div>

        </div>

        <!-- Custom Provider form -->
        <div v-if="showCustomForm" class="rounded-lg border border-violet-400/30 bg-violet-500/5 p-4 space-y-3">
          <div class="flex items-center justify-between">
            <span class="font-medium text-sm text-violet-400">{{ t('llm.customProvider') }}</span>
            <button class="text-muted-foreground hover:text-foreground text-xs" @click="showCustomForm = false; customSlug = ''; customSlugError = ''">
              {{ t('common.cancel') }}
            </button>
          </div>
          <div class="space-y-1.5">
            <label class="text-xs text-muted-foreground">{{ t('llm.providerSlug') }}</label>
            <input
              v-model="customSlug"
              type="text"
              maxlength="32"
              :placeholder="t('llm.providerSlugPlaceholder')"
              class="w-full px-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
              @keydown.enter="addCustomProvider"
            />
            <p v-if="customSlugError" class="text-[10px] text-destructive">{{ customSlugError }}</p>
            <p v-else class="text-[10px] text-muted-foreground">{{ t('llm.providerSlugHint') }}</p>
          </div>
          <button
            class="px-4 py-1.5 rounded-md bg-violet-500/10 text-violet-400 text-sm hover:bg-violet-500/20 transition-colors"
            :disabled="!customSlug.trim()"
            @click="addCustomProvider"
          >
            {{ t('common.add') }}
          </button>
        </div>

      </template>
    </div>

    <!-- Close dropdown overlay -->
    <Teleport to="body">
      <div v-if="newProviderOpen" class="fixed inset-0 z-40" @click="newProviderOpen = false" />
    </Teleport>
  </div>
</template>
