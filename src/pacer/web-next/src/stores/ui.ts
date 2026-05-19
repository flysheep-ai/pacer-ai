import { defineStore } from 'pinia'

type Theme = 'light' | 'dark'

const KEY = 'pacer_theme'

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: (localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light') as Theme,
  }),
  actions: {
    applyTheme(): void {
      if (this.theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark')
      } else {
        document.documentElement.removeAttribute('data-theme')
      }
    },
    toggleTheme(): void {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem(KEY, this.theme)
      this.applyTheme()
    },
  },
})
