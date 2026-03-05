<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, Save, RotateCcw, Paintbrush } from 'lucide-vue-next'
import { FLOOR_ASSETS, FURNITURE_ASSETS, type DecorationAsset } from '@/config/decorationAssets'
import type { DecorationConfig, FurniturePlacement } from '@/stores/workspace'

const props = defineProps<{
  config: DecorationConfig | null
  saving?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:config', config: Partial<DecorationConfig>): void
  (e: 'save'): void
  (e: 'close'): void
  (e: 'select-furniture', assetId: string | null): void
}>()

const { t } = useI18n()

const localYScale = ref(props.config?.y_scale ?? 1.0)
const selectedFloor = ref(props.config?.floor_asset_id ?? null)
const activeFurnitureTool = ref<string | null>(null)

watch(() => props.config, (cfg) => {
  if (cfg) {
    localYScale.value = cfg.y_scale
    selectedFloor.value = cfg.floor_asset_id ?? null
  }
}, { deep: true })

const furniturePlacements = computed<FurniturePlacement[]>(
  () => props.config?.furniture ?? [],
)

function selectFloor(asset: DecorationAsset | null) {
  selectedFloor.value = asset?.id ?? null
  emit('update:config', { floor_asset_id: asset?.id ?? null })
}

function onYScaleChange(val: number) {
  localYScale.value = val
  emit('update:config', { y_scale: val })
}

function toggleFurnitureTool(assetId: string) {
  if (activeFurnitureTool.value === assetId) {
    activeFurnitureTool.value = null
    emit('select-furniture', null)
  } else {
    activeFurnitureTool.value = assetId
    emit('select-furniture', assetId)
  }
}

function resetDecoration() {
  localYScale.value = 1.0
  selectedFloor.value = null
  activeFurnitureTool.value = null
  emit('select-furniture', null)
  emit('update:config', { y_scale: 1.0, floor_asset_id: null, furniture: [] })
}

function placedCountFor(assetId: string) {
  return furniturePlacements.value.filter(f => f.asset_id === assetId).length
}
</script>

<template>
  <div class="flex flex-col h-full bg-gray-900/95 text-gray-200 w-64 border-l border-gray-700/50">
    <div class="flex items-center justify-between px-3 py-2 border-b border-gray-700/50">
      <div class="flex items-center gap-2">
        <Paintbrush class="w-4 h-4 text-purple-400" />
        <span class="font-medium text-sm">{{ t('decoration.panel_title') }}</span>
      </div>
      <button class="p-1 rounded hover:bg-gray-700/50" @click="emit('close')">
        <X class="w-4 h-4" />
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-3 py-3 space-y-4">
      <section>
        <h3 class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
          {{ t('decoration.y_scale') }}
        </h3>
        <div class="flex items-center gap-2">
          <input
            type="range"
            :min="0.3"
            :max="1.0"
            :step="0.05"
            :value="localYScale"
            class="flex-1 accent-purple-500"
            @input="onYScaleChange(parseFloat(($event.target as HTMLInputElement).value))"
          />
          <span class="text-xs text-gray-400 w-8 text-right">{{ localYScale.toFixed(2) }}</span>
        </div>
      </section>

      <section>
        <h3 class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
          {{ t('decoration.floor.title') }}
        </h3>
        <div class="grid grid-cols-3 gap-2">
          <button
            class="aspect-square rounded border-2 overflow-hidden transition-all"
            :class="selectedFloor === null ? 'border-purple-500 ring-1 ring-purple-500/50' : 'border-gray-700 hover:border-gray-500'"
            @click="selectFloor(null)"
          >
            <div class="w-full h-full bg-gray-800 flex items-center justify-center">
              <X class="w-4 h-4 text-gray-500" />
            </div>
          </button>
          <button
            v-for="asset in FLOOR_ASSETS"
            :key="asset.id"
            class="aspect-square rounded border-2 overflow-hidden transition-all"
            :class="selectedFloor === asset.id ? 'border-purple-500 ring-1 ring-purple-500/50' : 'border-gray-700 hover:border-gray-500'"
            @click="selectFloor(asset)"
          >
            <img :src="asset.url" :alt="t(asset.nameKey)" class="w-full h-full object-cover" />
          </button>
        </div>
      </section>

      <section>
        <h3 class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
          {{ t('decoration.furniture.title') }}
        </h3>
        <p class="text-xs text-gray-500 mb-2">{{ t('decoration.furniture.hint') }}</p>
        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="asset in FURNITURE_ASSETS"
            :key="asset.id"
            class="aspect-square rounded border-2 overflow-hidden transition-all relative"
            :class="activeFurnitureTool === asset.id ? 'border-green-500 ring-1 ring-green-500/50' : 'border-gray-700 hover:border-gray-500'"
            @click="toggleFurnitureTool(asset.id)"
          >
            <img :src="asset.url" :alt="t(asset.nameKey)" class="w-full h-full object-contain p-1" />
            <span
              v-if="placedCountFor(asset.id) > 0"
              class="absolute top-0.5 right-0.5 bg-purple-600 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center"
            >{{ placedCountFor(asset.id) }}</span>
          </button>
        </div>
      </section>
    </div>

    <div class="flex items-center gap-2 px-3 py-2 border-t border-gray-700/50">
      <button
        class="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs rounded bg-purple-600 hover:bg-purple-500 transition-colors"
        :disabled="saving"
        @click="emit('save')"
      >
        <Save class="w-3.5 h-3.5" />
        {{ saving ? t('common.saving') : t('common.save') }}
      </button>
      <button
        class="flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs rounded bg-gray-700 hover:bg-gray-600 transition-colors"
        @click="resetDecoration"
      >
        <RotateCcw class="w-3.5 h-3.5" />
        {{ t('decoration.reset') }}
      </button>
    </div>
  </div>
</template>
