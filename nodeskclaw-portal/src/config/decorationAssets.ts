export interface DecorationAsset {
  id: string
  nameKey: string
  category: 'floor' | 'furniture'
  url: string
  thumbnailUrl?: string
}

export const FLOOR_ASSETS: DecorationAsset[] = [
  {
    id: 'carpet-warm',
    nameKey: 'decoration.floor.carpet_warm',
    category: 'floor',
    url: '/assets/hex2d/floors/carpet-warm.svg',
  },
  {
    id: 'carpet-cool',
    nameKey: 'decoration.floor.carpet_cool',
    category: 'floor',
    url: '/assets/hex2d/floors/carpet-cool.svg',
  },
  {
    id: 'carpet-marble',
    nameKey: 'decoration.floor.carpet_marble',
    category: 'floor',
    url: '/assets/hex2d/floors/carpet-marble.svg',
  },
]

export const FURNITURE_ASSETS: DecorationAsset[] = [
  {
    id: 'office-chair',
    nameKey: 'decoration.furniture.office_chair',
    category: 'furniture',
    url: '/assets/hex2d/furniture/office-chair.svg',
  },
  {
    id: 'office-desk',
    nameKey: 'decoration.furniture.office_desk',
    category: 'furniture',
    url: '/assets/hex2d/furniture/office-desk.svg',
  },
  {
    id: 'desk-lamp',
    nameKey: 'decoration.furniture.desk_lamp',
    category: 'furniture',
    url: '/assets/hex2d/furniture/desk-lamp.svg',
  },
  {
    id: 'stool',
    nameKey: 'decoration.furniture.stool',
    category: 'furniture',
    url: '/assets/hex2d/furniture/stool.svg',
  },
]

export function findAssetById(id: string): DecorationAsset | undefined {
  return [...FLOOR_ASSETS, ...FURNITURE_ASSETS].find(a => a.id === id)
}

export function findFloorAssetById(id: string): DecorationAsset | undefined {
  return FLOOR_ASSETS.find(a => a.id === id)
}
