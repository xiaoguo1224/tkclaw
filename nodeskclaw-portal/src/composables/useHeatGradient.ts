const STOPS = [
  { pos: 0.0, r: 59, g: 130, b: 246 },
  { pos: 0.2, r: 6, g: 182, b: 212 },
  { pos: 0.4, r: 34, g: 197, b: 94 },
  { pos: 0.6, r: 234, g: 179, b: 8 },
  { pos: 0.8, r: 249, g: 115, b: 22 },
  { pos: 1.0, r: 239, g: 68, b: 68 },
]

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function heatColorRgb(t: number): [number, number, number] {
  const clamped = Math.max(0, Math.min(1, t))
  for (let i = 0; i < STOPS.length - 1; i++) {
    const s0 = STOPS[i]
    const s1 = STOPS[i + 1]
    if (clamped >= s0.pos && clamped <= s1.pos) {
      const local = (clamped - s0.pos) / (s1.pos - s0.pos)
      return [
        Math.round(lerp(s0.r, s1.r, local)),
        Math.round(lerp(s0.g, s1.g, local)),
        Math.round(lerp(s0.b, s1.b, local)),
      ]
    }
  }
  const last = STOPS[STOPS.length - 1]
  return [last.r, last.g, last.b]
}

export function heatColor(t: number): string {
  const [r, g, b] = heatColorRgb(t)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}
