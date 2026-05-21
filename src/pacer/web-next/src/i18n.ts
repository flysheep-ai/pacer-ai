import { createI18n } from 'vue-i18n'
import zhCN from '@/locales/zh-CN'
import en from '@/locales/en'

const STORAGE_KEY = 'pacer_lang'

function savedLocale(): string {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'en' || v === 'zh-CN') return v
  } catch { /* localStorage unavailable */ }
  return 'zh-CN'
}

export const i18n = createI18n({
  legacy: false,
  locale: savedLocale(),
  fallbackLocale: 'zh-CN',
  messages: { 'zh-CN': zhCN, en },
})

export function switchLang(): string {
  const next = i18n.global.locale.value === 'zh-CN' ? 'en' : 'zh-CN'
  i18n.global.locale.value = next
  try { localStorage.setItem(STORAGE_KEY, next) } catch { /* noop */ }
  return next
}
