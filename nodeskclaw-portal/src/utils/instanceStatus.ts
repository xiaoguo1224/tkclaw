export interface StatusDisplay {
  key: string
  color: string
  bgColor: string
  pulse: boolean
}

const STATUS_MAP: Record<string, Omit<StatusDisplay, 'key'>> = {
  ready:       { color: 'text-green-400',  bgColor: 'bg-green-400',  pulse: false },
  unreachable: { color: 'text-orange-400', bgColor: 'bg-orange-400', pulse: false },
  checking:    { color: 'text-yellow-400', bgColor: 'bg-yellow-400', pulse: false },
  preparing:   { color: 'text-yellow-400', bgColor: 'bg-yellow-400', pulse: true },
  restarting:  { color: 'text-yellow-400', bgColor: 'bg-yellow-400', pulse: true },
  updating:    { color: 'text-blue-400',   bgColor: 'bg-blue-400',   pulse: true },
  learning:    { color: 'text-blue-400',   bgColor: 'bg-blue-400',   pulse: true },
  error:       { color: 'text-red-400',    bgColor: 'bg-red-400',    pulse: false },
  leaving:     { color: 'text-gray-400',   bgColor: 'bg-gray-400',   pulse: true },
}

const FALLBACK: Omit<StatusDisplay, 'key'> = { color: 'text-gray-400', bgColor: 'bg-gray-400', pulse: false }

export function getStatusDisplay(displayStatus: string): StatusDisplay {
  const cfg = STATUS_MAP[displayStatus] ?? FALLBACK
  return { key: displayStatus, ...cfg }
}
