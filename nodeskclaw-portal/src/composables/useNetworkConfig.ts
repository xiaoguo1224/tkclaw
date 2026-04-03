import { ref } from 'vue'
import api from '@/services/api'

const _cache = ref<'https' | 'http' | null>(null)

export function useNetworkConfig() {
  async function ensureLoaded() {
    if (_cache.value !== null) return
    try {
      const res = await api.get('/settings')
      const data = res.data.data
      _cache.value = data.ingress_tls_enabled === 'false' ? 'http' : 'https'
    } catch {
      _cache.value = 'https'
    }
  }

  function buildInstanceUrl(domain: string) {
    return `${_cache.value ?? 'https'}://${domain}`
  }

  function invalidate() {
    _cache.value = null
  }

  return { protocol: _cache, ensureLoaded, buildInstanceUrl, invalidate }
}
