<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ChevronRight, Download, File, FileCode, FileText,
  Folder, FolderPlus, Loader2, Search, Trash2, Upload, X,
} from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'

const props = defineProps<{ workspaceId: string }>()
const { t, locale } = useI18n()

interface FileItem {
  id: string
  name: string
  is_directory: boolean
  file_size: number
  content_type: string
  uploader_name: string
  created_at: string
}

interface FileContentResponse {
  content: string
  content_type: string
}

const CODE_EXTENSIONS = new Set([
  'ts', 'js', 'tsx', 'jsx', 'vue', 'py', 'sh', 'bash', 'css', 'scss', 'html', 'sql',
])

const TEXT_EXTENSIONS = new Set([
  'md', 'txt', 'json', 'yaml', 'yml', 'toml', 'xml', 'csv', 'log', 'env',
  'gitignore', 'dockerfile', 'conf', 'cfg', 'ini',
])

const TEXT_PREVIEW_LIMIT = 512 * 1024

const currentPath = ref('/')
const files = ref<FileItem[]>([])
const loading = ref(false)
const error = ref('')
const filterText = ref('')

const showMkdir = ref(false)
const newDirName = ref('')
const creating = ref(false)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const panelVisible = ref(false)
const panelLoading = ref(false)
const panelContent = ref('')
const panelFileName = ref('')
const panelError = ref('')
const panelTruncated = ref(false)
const panelBinary = ref(false)

const breadcrumbs = computed(() => {
  const parts = currentPath.value.split('/').filter(Boolean)
  const crumbs = [{ name: '/', path: '/' }]
  let acc = '/'
  for (const part of parts) {
    acc += `${part}/`
    crumbs.push({ name: part, path: acc })
  }
  return crumbs
})

const filteredItems = computed(() => {
  if (!filterText.value.trim()) return files.value
  const q = filterText.value.toLowerCase()
  return files.value.filter(item => item.name.toLowerCase().includes(q))
})

function fileExt(name: string) {
  return name.split('.').pop()?.toLowerCase() ?? ''
}

function getFileIcon(item: FileItem) {
  if (item.is_directory) return Folder
  const ext = fileExt(item.name)
  if (CODE_EXTENSIONS.has(ext)) return FileCode
  if (TEXT_EXTENSIONS.has(ext)) return FileText
  return File
}

function isTextLike(item: FileItem) {
  const normalized = (item.content_type || '').toLowerCase()
  return (
    normalized.startsWith('text/')
    || normalized.includes('json')
    || normalized.includes('xml')
    || normalized.includes('yaml')
    || normalized.includes('javascript')
    || normalized.includes('typescript')
    || normalized.includes('shellscript')
    || normalized.includes('toml')
    || normalized.includes('sql')
    || normalized.includes('x-python')
    || normalized.includes('x-java')
    || normalized.includes('x-go')
    || normalized.includes('x-rust')
    || normalized.includes('x-vue')
    || normalized.includes('markdown')
    || TEXT_EXTENSIONS.has(fileExt(item.name))
    || CODE_EXTENSIONS.has(fileExt(item.name))
  )
}

function formatSize(bytes: number) {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const val = bytes / Math.pow(1024, i)
  return `${val < 10 ? val.toFixed(1) : Math.round(val)} ${units[i]}`
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const loc = locale.value === 'zh-CN' ? 'zh-CN' : 'en-US'
  return d.toLocaleDateString(loc, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function decodeBase64Utf8(content: string) {
  const binary = window.atob(content)
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
  if (
    bytes.length >= 3
    && bytes[0] === 0xef
    && bytes[1] === 0xbb
    && bytes[2] === 0xbf
  ) {
    return new TextDecoder('utf-8').decode(bytes.slice(3))
  }
  return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
}

async function fetchFiles() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files`, {
      params: { parent_path: currentPath.value },
    })
    files.value = res.data.data || []
  } catch (e: unknown) {
    error.value = resolveApiErrorMessage(e)
  } finally {
    loading.value = false
  }
}

function navigateTo(path: string) {
  currentPath.value = path
  filterText.value = ''
  fetchFiles()
}

function handleItemClick(item: FileItem) {
  if (item.is_directory) {
    navigateTo(`${currentPath.value}${item.name}/`)
    return
  }
  openPanel(item)
}

async function mkdir() {
  if (!newDirName.value.trim()) return
  creating.value = true
  try {
    await api.post(`/workspaces/${props.workspaceId}/blackboard/files/mkdir`, {
      parent_path: currentPath.value,
      name: newDirName.value.trim(),
    })
    newDirName.value = ''
    showMkdir.value = false
    await fetchFiles()
  } catch (e) {
    console.error('mkdir error:', e)
  } finally {
    creating.value = false
  }
}

async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('parent_path', currentPath.value)
    formData.append('file', file)
    await api.post(`/workspaces/${props.workspaceId}/blackboard/files/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    await fetchFiles()
  } catch (e: unknown) {
    error.value = resolveApiErrorMessage(e)
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function deleteFile(item: FileItem) {
  try {
    await api.delete(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}`)
    await fetchFiles()
  } catch (e) {
    console.error('delete error:', e)
  }
}

function getDownloadFilename(contentDisposition: string | undefined, fallback: string) {
  if (!contentDisposition) return fallback
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  const plainMatch = contentDisposition.match(/filename="?([^"]+)"?/i)
  return plainMatch?.[1] || fallback
}

async function downloadFile(item: FileItem) {
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}/url`)
    const url = res.data.data?.url
    if (!url) return
    window.open(url, '_blank')
  } catch (e) {
    console.error('download error:', e)
  }
}

async function downloadDirectory(item: FileItem) {
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}/archive`, {
      responseType: 'blob',
    })
    const blob = new Blob([res.data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const filename = getDownloadFilename(
      res.headers['content-disposition'],
      `${item.name}.zip`,
    )
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('download directory error:', e)
  }
}

async function openPanel(item: FileItem) {
  panelVisible.value = true
  panelLoading.value = true
  panelContent.value = ''
  panelFileName.value = item.name
  panelError.value = ''
  panelTruncated.value = false
  panelBinary.value = false
  try {
    if (!isTextLike(item)) {
      panelBinary.value = true
      return
    }
    if (item.file_size > TEXT_PREVIEW_LIMIT) {
      panelTruncated.value = true
      return
    }
    const { data } = await api.get(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}/content`)
    const result = data.data as FileContentResponse | null
    if (!result?.content) {
      panelBinary.value = true
      return
    }
    try {
      panelContent.value = decodeBase64Utf8(result.content)
    } catch {
      panelBinary.value = true
    }
  } catch (e: unknown) {
    panelError.value = resolveApiErrorMessage(e)
  } finally {
    panelLoading.value = false
  }
}

function closePanel() {
  panelVisible.value = false
}

onMounted(fetchFiles)
watch(() => props.workspaceId, () => {
  currentPath.value = '/'
  filterText.value = ''
  fetchFiles()
})
</script>

<template>
  <div>
    <div class="flex items-center gap-1 mb-4 text-sm flex-wrap">
      <button
        v-for="(crumb, idx) in breadcrumbs"
        :key="crumb.path"
        class="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
        @click="navigateTo(crumb.path)"
      >
        <ChevronRight v-if="idx > 0" class="w-3 h-3 shrink-0" />
        <span>{{ crumb.name }}</span>
      </button>
    </div>

    <div class="flex items-center justify-between mb-4 gap-3">
      <div class="relative max-w-xs flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          v-model="filterText"
          :placeholder="t('instanceFiles.filterPlaceholder')"
          class="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <button
          class="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg hover:bg-muted transition-colors"
          @click="showMkdir = !showMkdir"
        >
          <FolderPlus class="w-3.5 h-3.5" />
        </button>
        <button
          class="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg hover:bg-muted transition-colors"
          :disabled="uploading"
          @click="fileInputRef?.click()"
        >
          <Loader2 v-if="uploading" class="w-3.5 h-3.5 animate-spin" />
          <Upload v-else class="w-3.5 h-3.5" />
        </button>
        <input ref="fileInputRef" type="file" class="hidden" @change="uploadFile" />
      </div>
    </div>

    <div v-if="showMkdir" class="flex items-center gap-2 mb-4">
      <input
        v-model="newDirName"
        class="flex-1 bg-background border border-border rounded px-2.5 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
        :placeholder="t('blackboard.dirNamePlaceholder')"
        @keydown.enter="mkdir"
      />
      <button
        class="px-2.5 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
        :disabled="creating || !newDirName.trim()"
        @click="mkdir"
      >
        {{ t('blackboard.create') }}
      </button>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
      <span class="ml-2 text-sm text-muted-foreground">{{ t('instanceFiles.loading') }}</span>
    </div>

    <div v-else-if="error" class="text-center py-20 space-y-4">
      <p class="text-sm text-red-400">{{ error }}</p>
      <button
        class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
        @click="fetchFiles"
      >
        {{ t('instanceList.retry') }}
      </button>
    </div>

    <div
      v-else-if="files.length === 0"
      class="text-center py-20 text-sm text-muted-foreground"
    >
      {{ t('instanceFiles.emptyDir') }}
    </div>

    <div v-else class="rounded-xl border border-border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border bg-card/60">
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">
              {{ t('instanceFiles.fileName') }}
            </th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground w-24">
              {{ t('instanceFiles.fileSize') }}
            </th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground w-44">
              {{ t('instanceFiles.fileModified') }}
            </th>
            <th class="w-24" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in filteredItems"
            :key="item.id"
            class="border-b border-border last:border-b-0 hover:bg-accent/50 transition-colors"
            :class="item.is_directory ? 'cursor-pointer' : 'cursor-pointer'"
            @click="handleItemClick(item)"
          >
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <component
                  :is="getFileIcon(item)"
                  class="w-4 h-4 shrink-0"
                  :class="item.is_directory ? 'text-primary' : 'text-muted-foreground'"
                />
                <span class="truncate" :class="item.is_directory ? 'font-medium' : ''">
                  {{ item.name }}
                </span>
              </div>
            </td>
            <td class="px-4 py-3 text-muted-foreground tabular-nums">
              {{ item.is_directory ? '-' : formatSize(item.file_size) }}
            </td>
            <td class="px-4 py-3 text-muted-foreground">
              {{ formatTime(item.created_at) }}
            </td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-1">
                <button
                  v-if="item.is_directory"
                  class="p-1 rounded hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
                  :title="t('blackboard.downloadFolder')"
                  @click.stop="downloadDirectory(item)"
                >
                  <Download class="w-4 h-4" />
                </button>
                <button
                  v-else
                  class="p-1 rounded hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
                  :title="t('instanceFiles.download')"
                  @click.stop="downloadFile(item)"
                >
                  <Download class="w-4 h-4" />
                </button>
                <button
                  class="p-1 rounded hover:bg-destructive/20 text-destructive transition-colors"
                  @click.stop="deleteFile(item)"
                >
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Teleport to="body">
      <Transition name="slide-right">
        <div
          v-if="panelVisible"
          class="fixed inset-y-0 right-0 w-xl max-w-full bg-background border-l border-border shadow-xl z-50 flex flex-col"
        >
          <div class="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
            <div class="flex items-center gap-2 min-w-0">
              <h3 class="font-medium text-sm truncate">{{ panelFileName }}</h3>
            </div>
            <button
              class="p-1 rounded hover:bg-accent transition-colors ml-1"
              @click="closePanel"
            >
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="flex-1 overflow-auto p-4">
            <div v-if="panelLoading" class="flex items-center justify-center py-10">
              <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
            <div v-else-if="panelError" class="text-sm text-red-400">{{ panelError }}</div>
            <div v-else-if="panelTruncated" class="text-sm text-muted-foreground">
              {{ t('instanceFiles.fileTooLarge') }}
            </div>
            <div v-else-if="panelBinary" class="text-sm text-muted-foreground">
              {{ t('instanceFiles.binaryFile') }}
            </div>
            <pre
              v-else
              class="text-xs leading-relaxed font-mono whitespace-pre-wrap break-all text-foreground"
            >{{ panelContent }}</pre>
          </div>
        </div>
      </Transition>
      <Transition name="fade">
        <div
          v-if="panelVisible"
          class="fixed inset-0 bg-black/30 z-40"
          @click="closePanel"
        />
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.25s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
