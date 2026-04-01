<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { Folder, File, FolderPlus, Upload, Trash2, Download, Loader2, ChevronRight, Eye, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import api from '@/services/api'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ workspaceId: string }>()
const { t } = useI18n()

interface FileItem {
  id: string
  name: string
  is_directory: boolean
  file_size: number
  content_type: string
  uploader_name: string
  created_at: string
}

interface FilePreview {
  filename: string
  content_type: string
  preview_type: 'text' | 'image' | 'pdf' | 'unsupported'
  encoding: 'utf-8' | 'utf-8-bom' | 'unknown'
  text_content: string | null
  download_url: string | null
  is_previewable: boolean
  file_size: number
}

const currentPath = ref('/')
const files = ref<FileItem[]>([])
const loading = ref(false)
const showMkdir = ref(false)
const newDirName = ref('')
const creating = ref(false)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const previewLoading = ref(false)
const previewItem = ref<FilePreview | null>(null)
const previewError = ref('')

const breadcrumbs = computed(() => {
  const parts = currentPath.value.split('/').filter(Boolean)
  const crumbs = [{ name: '/', path: '/' }]
  let acc = '/'
  for (const p of parts) {
    acc += p + '/'
    crumbs.push({ name: p, path: acc })
  }
  return crumbs
})

async function fetchFiles() {
  loading.value = true
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files`, {
      params: { parent_path: currentPath.value },
    })
    files.value = res.data.data || []
  } catch (e) {
    console.error('fetch files error:', e)
  } finally {
    loading.value = false
  }
}

function navigate(item: FileItem) {
  if (item.is_directory) {
    currentPath.value = currentPath.value + item.name + '/'
    fetchFiles()
  }
}

function navigateTo(path: string) {
  currentPath.value = path
  fetchFiles()
}

async function mkdir() {
  if (!newDirName.value.trim()) return
  creating.value = true
  try {
    await api.post(`/workspaces/${props.workspaceId}/blackboard/files/mkdir`, {
      parent_path: currentPath.value,
      name: newDirName.value.trim(),
    })
    showMkdir.value = false
    newDirName.value = ''
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
    const reader = new FileReader()
    const b64 = await new Promise<string>((resolve) => {
      reader.onload = () => {
        const result = reader.result as string
        resolve(result.split(',')[1] || '')
      }
      reader.readAsDataURL(file)
    })
    await api.post(`/workspaces/${props.workspaceId}/blackboard/files/upload`, {
      parent_path: currentPath.value,
      filename: file.name,
      content: b64,
      content_type: file.type || 'application/octet-stream',
    })
    await fetchFiles()
  } catch (e) {
    console.error('upload error:', e)
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function downloadFile(item: FileItem) {
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}/url`)
    const url = res.data.data?.url
    if (url) window.open(url, '_blank')
  } catch (e) {
    console.error('download error:', e)
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

async function deleteFile(item: FileItem) {
  try {
    await api.delete(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}`)
    await fetchFiles()
  } catch (e) {
    console.error('delete error:', e)
  }
}

async function previewFile(item: FileItem) {
  previewLoading.value = true
  previewError.value = ''
  previewItem.value = null
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}/preview`)
    previewItem.value = res.data.data || null
  } catch (e) {
    console.error('preview error:', e)
    previewError.value = t('blackboard.previewLoadFailed')
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  previewLoading.value = false
  previewError.value = ''
  previewItem.value = null
}

const previewMarkdownHtml = computed(() => {
  if (!previewItem.value?.text_content || !isMarkdown(previewItem.value.content_type)) return ''
  return renderMarkdown(previewItem.value.text_content)
})

function isMarkdown(contentType: string) {
  return contentType.includes('markdown')
}

function formatContentType(contentType: string) {
  return contentType || 'application/octet-stream'
}

function previewMessage(preview: FilePreview) {
  if (preview.file_size > 512 * 1024) return t('blackboard.previewTooLarge')
  if (preview.preview_type !== 'text') return t('blackboard.previewUnsupported')
  if (preview.encoding === 'unknown' || !preview.is_previewable) return t('blackboard.previewEncodingUnknown')
  return ''
}

function openPreviewDownload(url: string | null) {
  if (!url) return
  window.open(url, '_blank')
}

function formatSize(bytes: number) {
  if (bytes === 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

onMounted(fetchFiles)
watch(() => props.workspaceId, () => { currentPath.value = '/'; fetchFiles() })
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-0.5 text-sm text-muted-foreground overflow-x-auto">
        <button
          v-for="(crumb, idx) in breadcrumbs"
          :key="crumb.path"
          class="flex items-center gap-0.5 hover:text-foreground transition-colors shrink-0"
          @click="navigateTo(crumb.path)"
        >
          <ChevronRight v-if="idx > 0" class="w-3 h-3" />
          <span class="text-xs">{{ crumb.name }}</span>
        </button>
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

    <div v-if="showMkdir" class="flex items-center gap-2">
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

    <div v-if="loading && files.length === 0" class="flex items-center justify-center py-8">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="files.length === 0" class="text-sm text-muted-foreground py-6 text-center">
      {{ t('blackboard.noFiles') }}
    </div>

    <div v-else class="space-y-0.5">
      <div
        v-for="item in files"
        :key="item.id"
        class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/50 transition-colors group"
        :class="item.is_directory ? 'cursor-pointer' : ''"
        @click="item.is_directory && navigate(item)"
      >
        <Folder v-if="item.is_directory" class="w-4 h-4 text-primary shrink-0" />
        <File v-else class="w-4 h-4 text-muted-foreground shrink-0" />
        <span class="text-sm flex-1 truncate">{{ item.name }}</span>
        <span class="text-xs text-muted-foreground shrink-0">{{ formatSize(item.file_size) }}</span>
        <span class="text-xs text-muted-foreground shrink-0 hidden sm:inline">{{ item.uploader_name }}</span>
        <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            v-if="!item.is_directory"
            class="p-1 rounded hover:bg-muted transition-colors"
            :title="t('blackboard.previewFile')"
            @click.stop="previewFile(item)"
          >
            <Eye class="w-3.5 h-3.5" />
          </button>
          <button
            v-if="item.is_directory"
            class="p-1 rounded hover:bg-muted transition-colors"
            :title="t('blackboard.downloadFolder')"
            @click.stop="downloadDirectory(item)"
          >
            <Download class="w-3.5 h-3.5" />
          </button>
          <button
            v-else
            class="p-1 rounded hover:bg-muted transition-colors"
            :title="t('blackboard.downloadFile')"
            @click.stop="downloadFile(item)"
          >
            <Download class="w-3.5 h-3.5" />
          </button>
          <button
            class="p-1 rounded hover:bg-destructive/20 text-destructive transition-colors"
            @click.stop="deleteFile(item)"
          >
            <Trash2 class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>

    <div v-if="previewLoading || previewItem || previewError" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" @click.self="closePreview">
      <div class="w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-xl border border-border bg-card shadow-2xl flex flex-col">
        <div class="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <div class="min-w-0">
            <h3 class="text-sm font-semibold truncate">{{ previewItem?.filename || t('blackboard.previewTitle') }}</h3>
            <p v-if="previewItem" class="text-xs text-muted-foreground mt-1">
              {{ t('blackboard.previewType') }}: {{ formatContentType(previewItem.content_type) }}
              <span class="mx-2">·</span>
              {{ t('blackboard.previewEncoding') }}: {{ previewItem.encoding }}
            </p>
          </div>
          <button class="p-1.5 rounded hover:bg-muted transition-colors" @click="closePreview">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="flex-1 min-h-0 overflow-auto p-4">
          <div v-if="previewLoading" class="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 class="w-5 h-5 animate-spin" />
          </div>

          <div v-else-if="previewError" class="text-sm text-destructive">
            {{ previewError }}
          </div>

          <template v-else-if="previewItem">
            <div v-if="previewItem.preview_type === 'image' && previewItem.download_url" class="flex items-center justify-center">
              <img :src="previewItem.download_url" :alt="previewItem.filename" class="max-w-full max-h-[65vh] rounded-lg border border-border" />
            </div>

            <div v-else-if="previewItem.preview_type === 'pdf' && previewItem.download_url" class="h-[65vh] rounded-lg overflow-hidden border border-border">
              <iframe :src="previewItem.download_url" class="w-full h-full bg-background" />
            </div>

            <div v-else-if="previewItem.preview_type === 'text' && previewItem.is_previewable && previewItem.text_content !== null">
              <div v-if="isMarkdown(previewItem.content_type)" class="prose prose-sm prose-invert max-w-none" v-html="previewMarkdownHtml" />
              <pre v-else class="rounded-lg border border-border bg-muted/40 p-4 text-sm leading-6 whitespace-pre-wrap break-words overflow-auto font-mono">{{ previewItem.text_content }}</pre>
            </div>

            <div v-else class="space-y-3">
              <p class="text-sm text-muted-foreground">{{ previewMessage(previewItem) }}</p>
              <button
                v-if="previewItem.download_url"
                class="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                @click="openPreviewDownload(previewItem.download_url)"
              >
                <Download class="w-4 h-4" />
                {{ t('blackboard.downloadFile') }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
