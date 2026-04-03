<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { useNetworkConfig } from '@/composables/useNetworkConfig'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { Loader2, Save, Globe, AlertTriangle, Shield } from 'lucide-vue-next'

const { t } = useI18n()
const toast = useToast()
const { invalidate } = useNetworkConfig()

const loading = ref(false)
const saving = ref(false)
const savingEgress = ref(false)

const form = ref({
  ingress_base_domain: '',
  ingress_subdomain_suffix: '',
  tls_secret_name: '',
  ingress_tls_enabled: true,
})

const egressForm = ref({
  egress_deny_cidrs: '',
  egress_allow_ports: '',
})

const previewProtocol = computed(() => form.value.ingress_tls_enabled ? 'https' : 'http')

const previewUrl = computed(() => {
  if (!form.value.ingress_base_domain) return ''
  const suffix = form.value.ingress_subdomain_suffix
    ? `-${form.value.ingress_subdomain_suffix}`
    : ''
  return `${previewProtocol.value}://<instance-name>${suffix}.${form.value.ingress_base_domain}`
})

async function loadSettings() {
  loading.value = true
  try {
    const res = await api.get('/settings')
    const data = res.data.data as Record<string, string | null>
    form.value.ingress_base_domain = data.ingress_base_domain || ''
    form.value.ingress_subdomain_suffix = data.ingress_subdomain_suffix || ''
    form.value.tls_secret_name = data.tls_secret_name || ''
    form.value.ingress_tls_enabled = data.ingress_tls_enabled !== 'false'
    egressForm.value.egress_deny_cidrs = data.egress_deny_cidrs ?? ''
    egressForm.value.egress_allow_ports = data.egress_allow_ports ?? ''
  } catch {
    // first-time setup may have no config
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    await Promise.all([
      api.put('/settings/ingress_base_domain', { value: form.value.ingress_base_domain.trim() || null }),
      api.put('/settings/ingress_subdomain_suffix', { value: form.value.ingress_subdomain_suffix.trim() || null }),
      api.put('/settings/tls_secret_name', { value: form.value.tls_secret_name.trim() || null }),
      api.put('/settings/ingress_tls_enabled', { value: form.value.ingress_tls_enabled ? 'true' : 'false' }),
    ])
    invalidate()
    toast.success(t('orgSettings.networkSaved'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.networkSaveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleSaveEgress() {
  savingEgress.value = true
  try {
    await Promise.all([
      api.put('/settings/egress_deny_cidrs', { value: egressForm.value.egress_deny_cidrs.trim() }),
      api.put('/settings/egress_allow_ports', { value: egressForm.value.egress_allow_ports.trim() }),
    ])
    toast.success(t('orgSettings.npSaved'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.npSaveFailed')))
  } finally {
    savingEgress.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">{{ t('orgSettings.networkTitle') }}</h2>
      <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.networkDescription') }}</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <div v-if="!form.ingress_base_domain" class="text-center py-12 space-y-4">
        <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto">
          <Globe class="w-6 h-6 text-muted-foreground" />
        </div>
        <div>
          <p class="text-sm font-medium">{{ t('orgSettings.networkEmpty') }}</p>
          <p class="text-xs text-muted-foreground mt-1">{{ t('orgSettings.networkEmptyHint') }}</p>
        </div>
      </div>

      <div class="space-y-4">
        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.networkBaseDomain') }}</label>
          <input
            v-model="form.ingress_base_domain"
            type="text"
            placeholder="example.com"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
          <p class="text-xs text-muted-foreground">{{ t('orgSettings.networkBaseDomainHint') }}</p>
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.networkSubdomainSuffix') }}</label>
          <input
            v-model="form.ingress_subdomain_suffix"
            type="text"
            placeholder="staging"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
          <p class="text-xs text-muted-foreground">{{ t('orgSettings.networkSubdomainSuffixHint') }}</p>
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.networkTlsSecretName') }}</label>
          <input
            v-model="form.tls_secret_name"
            type="text"
            placeholder="wildcard-tls"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
          <p class="text-xs text-muted-foreground">{{ t('orgSettings.networkTlsSecretHint') }}</p>
        </div>

        <div class="flex items-center gap-2">
          <input
            id="enable-https"
            v-model="form.ingress_tls_enabled"
            type="checkbox"
            class="h-4 w-4 rounded border-input"
          />
          <label for="enable-https" class="text-sm font-medium">{{ t('orgSettings.networkEnableHttps') }}</label>
          <span class="text-xs text-muted-foreground">{{ t('orgSettings.networkEnableHttpsHint') }}</span>
        </div>

        <div class="flex items-center gap-3 pt-2">
          <button
            :disabled="saving"
            class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            @click="handleSave"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ t('orgSettings.networkSave') }}
          </button>
        </div>

        <div v-if="previewUrl" class="text-xs text-muted-foreground bg-muted/30 rounded-lg p-3">
          {{ t('orgSettings.networkPreview') }}<span class="font-mono text-foreground ml-1">{{ previewUrl }}</span>
        </div>
      </div>
    </template>

    <!-- Egress NetworkPolicy -->
    <div v-if="!loading" class="border-t pt-6 space-y-4">
      <div>
        <div class="flex items-center gap-2">
          <Shield class="w-5 h-5 text-muted-foreground" />
          <h3 class="text-base font-semibold">{{ t('orgSettings.npTitle') }}</h3>
        </div>
        <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.npDescription') }}</p>
      </div>

      <div class="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30 p-3">
        <AlertTriangle class="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
        <p class="text-xs text-amber-700 dark:text-amber-300">{{ t('orgSettings.npWarning') }}</p>
      </div>

      <div class="space-y-1.5">
        <label class="text-sm font-medium">{{ t('orgSettings.npDenyCidrs') }}</label>
        <input
          v-model="egressForm.egress_deny_cidrs"
          type="text"
          placeholder="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
          class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
        />
        <p class="text-xs text-muted-foreground">{{ t('orgSettings.npDenyCidrsHint') }}</p>
      </div>

      <div class="space-y-1.5">
        <label class="text-sm font-medium">{{ t('orgSettings.npAllowPorts') }}</label>
        <input
          v-model="egressForm.egress_allow_ports"
          type="text"
          placeholder="80,443"
          class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
        />
        <p class="text-xs text-muted-foreground">{{ t('orgSettings.npAllowPortsHint') }}</p>
      </div>

      <div class="flex items-center gap-3 pt-2">
        <button
          :disabled="savingEgress"
          class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
          @click="handleSaveEgress"
        >
          <Loader2 v-if="savingEgress" class="w-4 h-4 animate-spin" />
          <Save v-else class="w-4 h-4" />
          {{ t('orgSettings.npSave') }}
        </button>
      </div>
    </div>
  </div>
</template>
