import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    currentSid: null as number | null,
  }),
  actions: {
    reset(): void { this.currentSid = null },
  },
})
