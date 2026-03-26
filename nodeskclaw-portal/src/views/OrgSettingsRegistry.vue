<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { Loader2, Save, Plug, Eye, EyeOff, Container, RefreshCw, AlertCircle } from 'lucide-vue-next'

const { t } = useI18n()
const toast = useToast()

const loading = ref(false)
const saving = ref(false)
const hasPassword = ref(false)
const showPassword = ref(false)

const registryUsername = ref('')
const registryPassword = ref('')

interface EngineItem {
  runtime_id: string
  display_name: string
  image_registry_key: string
  default_registry_url: string
}

const engines = ref<EngineItem[]>([])
const engineRegistryUrls = ref<Record<string, string>>({})
const testingEngine = ref<string | null>(null)

async function loadSettings() {
  loading.value = true
  try {
    const [settingsRes, enginesRes] = await Promise.all([
      api.get('/settings'),
      api.get('/engines'),
    ])
    const data = settingsRes.data.data as Record<string, string | null>
    engines.value = (enginesRes.data.data ?? []) as EngineItem[]

    registryUsername.value = data.registry_username || ''
    registryPassword.value = ''
    hasPassword.value = data.registry_password === '******'

    const urls: Record<string, string> = {}
    for (const eng of engines.value) {
      urls[eng.runtime_id] = data[eng.image_registry_key] || ''
    }
    engineRegistryUrls.value = urls
  } catch {
    // first-time setup may have no config
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  const hasAnyUrl = Object.values(engineRegistryUrls.value).some(u => u.trim())
  if (!hasAnyUrl) {
    toast.error(t('orgSettings.registryFillRequired'))
    return
  }

  saving.value = true
  try {
    const promises: Promise<unknown>[] = []
    for (const eng of engines.value) {
      const url = engineRegistryUrls.value[eng.runtime_id]?.trim() || null
      promises.push(api.put(`/settings/${eng.image_registry_key}`, { value: url }))
    }
    promises.push(api.put('/settings/registry_username', { value: registryUsername.value.trim() || null }))
    if (registryPassword.value) {
      promises.push(api.put('/settings/registry_password', { value: registryPassword.value }))
    }
    await Promise.all(promises)
    registryPassword.value = ''
    await loadSettings()
    toast.success(t('orgSettings.registrySaved'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.registrySaveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleTestEngine(engineId: string) {
  const url = engineRegistryUrls.value[engineId]?.trim()
  if (!url) {
    toast.error(t('orgSettings.registryFillRequired'))
    return
  }

  testingEngine.value = engineId
  try {
    const res = await api.get('/registry/tags', { params: { registry_url: url } })
    const tags = (res.data.data ?? []) as { tag: string }[]
    toast.success(t('orgSettings.registryTestSuccess', { count: tags.length }))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.registryTestFailed')))
  } finally {
    testingEngine.value = null
  }
}

const hasCredentials = computed(() =>
  registryUsername.value.trim() !== '' || registryPassword.value !== '' || hasPassword.value
)

const isUsingDefaultPublicRegistry = computed(() =>
  engines.value.some(eng => {
    const current = engineRegistryUrls.value[eng.runtime_id]?.trim()
    return current && eng.default_registry_url && current === eng.default_registry_url
  })
)

const showPublicRegistryWarning = computed(() =>
  hasCredentials.value && isUsingDefaultPublicRegistry.value
)

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">{{ t('orgSettings.registryTitle') }}</h2>
      <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.registryDescription') }}</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <div v-if="engines.length === 0 && !Object.values(engineRegistryUrls).some(u => u)" class="text-center py-12 space-y-4">
        <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto">
          <Container class="w-6 h-6 text-muted-foreground" />
        </div>
        <div>
          <p class="text-sm font-medium">{{ t('orgSettings.registryEmpty') }}</p>
          <p class="text-xs text-muted-foreground mt-1">{{ t('orgSettings.registryEmptyHint') }}</p>
        </div>
      </div>

      <div class="space-y-5">
        <div v-for="eng in engines" :key="eng.runtime_id" class="space-y-1.5">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium">{{ eng.display_name }}</label>
            <button
              v-if="engineRegistryUrls[eng.runtime_id]?.trim()"
              :disabled="testingEngine === eng.runtime_id"
              class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              @click="handleTestEngine(eng.runtime_id)"
            >
              <Loader2 v-if="testingEngine === eng.runtime_id" class="w-3 h-3 animate-spin" />
              <Plug v-else class="w-3 h-3" />
              {{ t('orgSettings.registryTest') }}
            </button>
          </div>
          <input
            v-model="engineRegistryUrls[eng.runtime_id]"
            type="text"
            :placeholder="`cr.example.com/namespace/${eng.runtime_id}`"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
        </div>

        <div class="border-t border-border pt-5 space-y-4">
          <div v-if="showPublicRegistryWarning"
            class="flex items-start gap-3 p-4 rounded-lg border border-amber-500/30 bg-amber-500/5">
            <AlertCircle class="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <p class="text-sm">{{ t('orgSettings.registryPublicWarning') }}</p>
          </div>

          <p class="text-xs text-muted-foreground">{{ t('orgSettings.registryCredentialsHint') }}</p>

          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.registryUsername') }}</label>
            <input
              v-model="registryUsername"
              type="text"
              placeholder="username"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>

          <div class="space-y-1.5">
            <label class="text-sm font-medium">
              {{ t('orgSettings.registryPassword') }}
              <span v-if="hasPassword" class="text-xs text-muted-foreground font-normal ml-1">
                ({{ t('orgSettings.registryPasswordHint') }})
              </span>
            </label>
            <div class="relative">
              <input
                v-model="registryPassword"
                :type="showPassword ? 'text' : 'password'"
                :placeholder="hasPassword ? t('orgSettings.registryPasswordHint') : t('orgSettings.registryPasswordPlaceholder')"
                class="w-full h-9 px-3 pr-10 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              />
              <button
                type="button"
                tabindex="-1"
                class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                @click="showPassword = !showPassword"
              >
                <EyeOff v-if="showPassword" class="w-4 h-4" />
                <Eye v-else class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-3 pt-2">
          <button
            :disabled="saving"
            class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            @click="handleSave"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ t('orgSettings.registrySave') }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
