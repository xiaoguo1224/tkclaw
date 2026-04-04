export function resolveLocale(locale: string): string {
  return String(locale).startsWith('zh') ? 'zh-CN' : 'en-US'
}

export function formatDateTime(value: string | number | Date, locale: string, options?: Intl.DateTimeFormatOptions): string {
  return new Date(value).toLocaleString(resolveLocale(locale), options)
}

export function formatNumber(value: number, locale: string, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(resolveLocale(locale), options).format(value)
}
