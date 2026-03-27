<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { Loader2, Save, Send, Eye, EyeOff, MailPlus } from 'lucide-vue-next'

const { t } = useI18n()
const toast = useToast()
const authStore = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const hasPassword = ref(false)
const showPassword = ref(false)

const form = ref({
  smtp_host: '',
  smtp_port: '587',
  smtp_username: '',
  smtp_password: '',
  smtp_from_email: '',
  smtp_from_name: '',
  smtp_use_tls: true,
})

const testEmail = ref('')

const verificationSubject = ref('')
const verificationTemplate = ref('')
const templateSaving = ref(false)

async function loadSettings() {
  loading.value = true
  try {
    const res = await api.get('/settings')
    const data = res.data.data as Record<string, string | null>
    form.value.smtp_host = data.smtp_host || ''
    form.value.smtp_port = data.smtp_port || '587'
    form.value.smtp_username = data.smtp_username || ''
    form.value.smtp_password = ''
    hasPassword.value = data.smtp_password === '******'
    form.value.smtp_from_email = data.smtp_from_email || ''
    form.value.smtp_from_name = data.smtp_from_name || ''
    form.value.smtp_use_tls = data.smtp_use_tls !== 'false'
    verificationSubject.value = data.verification_email_subject || ''
    verificationTemplate.value = data.verification_email_template || ''
  } catch {
    // first-time setup may have no config
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (!form.value.smtp_host || !form.value.smtp_username || !form.value.smtp_from_email) {
    toast.error(t('orgSettings.smtpFillRequired'))
    return
  }
  if (!hasPassword.value && !form.value.smtp_password) {
    toast.error(t('orgSettings.smtpPasswordRequired'))
    return
  }

  saving.value = true
  try {
    const promises = [
      api.put('/settings/smtp_host', { value: form.value.smtp_host.trim() || null }),
      api.put('/settings/smtp_port', { value: form.value.smtp_port.trim() || '587' }),
      api.put('/settings/smtp_username', { value: form.value.smtp_username.trim() || null }),
      api.put('/settings/smtp_from_email', { value: form.value.smtp_from_email.trim() || null }),
      api.put('/settings/smtp_from_name', { value: form.value.smtp_from_name.trim() || null }),
      api.put('/settings/smtp_use_tls', { value: form.value.smtp_use_tls ? 'true' : 'false' }),
    ]
    if (form.value.smtp_password) {
      promises.push(api.put('/settings/smtp_password', { value: form.value.smtp_password }))
    }
    await Promise.all(promises)
    form.value.smtp_password = ''
    hasPassword.value = true
    toast.success(t('orgSettings.smtpSaved'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.smtpSaveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  const email = testEmail.value.trim() || authStore.user?.email
  if (!email) {
    toast.error(t('orgSettings.smtpTestEmailRequired'))
    return
  }
  testing.value = true
  try {
    await api.post('/settings/smtp/test', { recipient_email: email })
    toast.success(t('orgSettings.smtpTestSent'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.smtpTestFailed')))
  } finally {
    testing.value = false
  }
}

async function handleSaveTemplate() {
  templateSaving.value = true
  try {
    await Promise.all([
      api.put('/settings/verification_email_subject', { value: verificationSubject.value.trim() || null }),
      api.put('/settings/verification_email_template', { value: verificationTemplate.value.trim() || null }),
    ])
    toast.success(t('orgSettings.templateSaved'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.smtpSaveFailed')))
  } finally {
    templateSaving.value = false
  }
}

onMounted(() => {
  loadSettings()
  testEmail.value = authStore.user?.email || ''
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">{{ t('orgSettings.smtpTitle') }}</h2>
      <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.smtpDescription') }}</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <!-- empty state -->
      <div v-if="!form.smtp_host && !hasPassword" class="text-center py-12 space-y-4">
        <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto">
          <MailPlus class="w-6 h-6 text-muted-foreground" />
        </div>
        <div>
          <p class="text-sm font-medium">{{ t('orgSettings.smtpEmpty') }}</p>
          <p class="text-xs text-muted-foreground mt-1">{{ t('orgSettings.smtpEmptyHint') }}</p>
        </div>
      </div>

      <!-- SMTP form -->
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpHost') }}</label>
            <input
              v-model="form.smtp_host"
              type="text"
              placeholder="smtp.example.com"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpPort') }}</label>
            <input
              v-model="form.smtp_port"
              type="text"
              placeholder="587"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.smtpUsername') }}</label>
          <input
            v-model="form.smtp_username"
            type="text"
            placeholder="user@example.com"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">
            {{ t('orgSettings.smtpPassword') }}
            <span v-if="hasPassword" class="text-xs text-muted-foreground font-normal ml-1">
              ({{ t('orgSettings.smtpPasswordHint') }})
            </span>
          </label>
          <div class="relative">
            <input
              v-model="form.smtp_password"
              :type="showPassword ? 'text' : 'password'"
              :placeholder="hasPassword ? t('orgSettings.smtpPasswordHint') : t('orgSettings.smtpPasswordPlaceholder')"
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

        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpFromEmail') }}</label>
            <input
              v-model="form.smtp_from_email"
              type="email"
              placeholder="noreply@example.com"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpFromName') }}</label>
            <input
              v-model="form.smtp_from_name"
              type="text"
              :placeholder="t('orgSettings.smtpFromNamePlaceholder')"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
        </div>

        <div class="flex items-center gap-2">
          <input
            id="use-tls"
            v-model="form.smtp_use_tls"
            type="checkbox"
            class="h-4 w-4 rounded border-input"
          />
          <label for="use-tls" class="text-sm font-medium">{{ t('orgSettings.smtpUseTls') }}</label>
        </div>

        <!-- action buttons -->
        <div class="flex items-center gap-3 pt-2">
          <button
            :disabled="saving"
            class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            @click="handleSave"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ t('orgSettings.smtpSave') }}
          </button>

          <template v-if="hasPassword || form.smtp_host">
            <input
              v-model="testEmail"
              type="email"
              :placeholder="t('orgSettings.smtpTestEmailPlaceholder')"
              class="h-9 w-52 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
            <button
              :disabled="testing || !form.smtp_host.trim()"
              class="h-9 px-4 rounded-md border border-input text-sm font-medium hover:bg-accent disabled:opacity-50 flex items-center gap-2"
              @click="handleTest"
            >
              <Loader2 v-if="testing" class="w-4 h-4 animate-spin" />
              <Send v-else class="w-4 h-4" />
              {{ t('orgSettings.smtpTest') }}
            </button>
          </template>
        </div>
      </div>

      <!-- email template -->
      <div class="border-t border-border pt-6 mt-6 space-y-4">
        <div>
          <h3 class="text-base font-semibold">{{ t('orgSettings.templateTitle') }}</h3>
          <p class="text-xs text-muted-foreground mt-1">
            {{ t('orgSettings.templateDescription') }}
          </p>
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.templateSubject') }}</label>
          <input
            v-model="verificationSubject"
            type="text"
            placeholder="TkClaw - 登录验证码"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.templateContent') }}</label>
          <textarea
            v-model="verificationTemplate"
            rows="8"
            :placeholder="t('orgSettings.templateContentPlaceholder')"
            class="w-full px-3 py-2 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 resize-y scrollbar-compact"
          />
        </div>

        <button
          :disabled="templateSaving"
          class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
          @click="handleSaveTemplate"
        >
          <Loader2 v-if="templateSaving" class="w-4 h-4 animate-spin" />
          <Save v-else class="w-4 h-4" />
          {{ t('orgSettings.templateSave') }}
        </button>
      </div>
    </template>
  </div>
</template>
