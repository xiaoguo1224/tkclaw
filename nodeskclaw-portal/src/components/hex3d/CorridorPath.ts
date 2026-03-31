import * as THREE from 'three'
import { axialToWorld, HEX_SIZE } from '@/composables/useHexLayout'

const AXIAL_DIRS: [number, number][] = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]

const CORRIDOR_RADIUS = HEX_SIZE * 0.88
const ARM_LENGTH = CORRIDOR_RADIUS * Math.sqrt(3) / 2
const RAIL_STRIP_WIDTH = 0.04
const RAIL_GAP = 0.12
const STRIP_HEIGHT = 0.015
const JUNCTION_RADIUS = 0.10
const HALF_GAP = (RAIL_GAP + RAIL_STRIP_WIDTH) / 2

const DIR_UNIT_VECTORS: [number, number][] = AXIAL_DIRS.map(([dq, dr]) => {
  const { x, y } = axialToWorld(dq, dr)
  const len = Math.sqrt(x * x + y * y)
  return [x / len, y / len] as [number, number]
})

const railStripGeo = new THREE.BoxGeometry(RAIL_STRIP_WIDTH, STRIP_HEIGHT, ARM_LENGTH)
const junctionGeo = new THREE.CircleGeometry(JUNCTION_RADIUS, 16)
const raycastGeo = new THREE.CylinderGeometry(CORRIDOR_RADIUS, CORRIDOR_RADIUS, 0.01, 6)

const allSharedGeos: THREE.BufferGeometry[] = [railStripGeo, junctionGeo, raycastGeo]

export function createCorridorPath(
  q: number,
  r: number,
  occupied: Set<string>,
  hexId: string,
): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(q, r)
  group.position.set(x, 0.02, y)
  group.userData = { hexId, isHex: true, hexQ: q, hexR: r }

  const junctionMat = new THREE.MeshStandardMaterial({
    color: 0x1a2d4a,
    emissive: new THREE.Color(0x38bdf8),
    emissiveIntensity: 0.2,
    metalness: 0.4,
    roughness: 0.5,
    transparent: true,
    opacity: 0.8,
    side: THREE.DoubleSide,
  })

  const armMaterials: THREE.MeshStandardMaterial[] = []
  const armNeighborKeys: string[] = []

  for (let i = 0; i < 6; i++) {
    const [dq, dr] = AXIAL_DIRS[i]
    if (!occupied.has(`${q + dq}:${r + dr}`)) continue

    const armMat = new THREE.MeshStandardMaterial({
      color: 0x1a2d4a,
      emissive: new THREE.Color(0x38bdf8),
      emissiveIntensity: 0.15,
      metalness: 0.5,
      roughness: 0.4,
      transparent: true,
      opacity: 0.7,
    })
    armMaterials.push(armMat)
    armNeighborKeys.push(`${q + dq},${r + dr}`)

    const [dx, dz] = DIR_UNIT_VECTORS[i]
    const angle = Math.atan2(dx, dz)
    const midX = dx * ARM_LENGTH / 2
    const midZ = dz * ARM_LENGTH / 2
    const perpX = -dz
    const perpZ = dx

    const rail1 = new THREE.Mesh(railStripGeo, armMat)
    rail1.position.set(midX + perpX * HALF_GAP, 0, midZ + perpZ * HALF_GAP)
    rail1.rotation.y = angle
    group.add(rail1)

    const rail2 = new THREE.Mesh(railStripGeo, armMat)
    rail2.position.set(midX - perpX * HALF_GAP, 0, midZ - perpZ * HALF_GAP)
    rail2.rotation.y = angle
    group.add(rail2)
  }

  const junction = new THREE.Mesh(junctionGeo, junctionMat)
  junction.rotation.x = -Math.PI / 2
  junction.position.y = STRIP_HEIGHT / 2
  group.add(junction)

  const rayTarget = new THREE.Mesh(
    raycastGeo,
    new THREE.MeshBasicMaterial({ visible: false }),
  )
  rayTarget.userData = { hexId, isHex: true }
  group.add(rayTarget)

  group.userData.armMaterials = armMaterials
  group.userData.armNeighborKeys = armNeighborKeys
  group.userData.junctionMat = junctionMat

  return group
}

export function disposeCorridorPath(group: THREE.Group): void {
  const armMats = group.userData.armMaterials as THREE.MeshStandardMaterial[] | undefined
  if (armMats) for (const m of armMats) m.dispose()
  const junctionMat = group.userData.junctionMat as THREE.MeshStandardMaterial | undefined
  junctionMat?.dispose()
}

export function disposeCorridorPathShared(): void {
  for (const g of allSharedGeos) g.dispose()
}
