import { createApp, watch } from 'vue'
import { createPinia } from 'pinia'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'
import { createRouter } from './router'
import { i18n } from './i18n'
import { useAuthStore } from './stores/auth'
import { useChatStore } from './stores/chat'
import { startSSE } from './api/sse'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(i18n)
app.use(createRouter())

const auth = useAuthStore(pinia)
const chat = useChatStore(pinia)

let stopSSE: (() => void) | null = null

function reconcileSSE(token: string | null): void {
  if (stopSSE) { stopSSE(); stopSSE = null }
  if (token !== null) {
    stopSSE = startSSE(token, {
      onAssistantMessage: (p) => chat.receiveAssistantMessage(p),
      onAssistantDelta: (p) => chat.receiveDelta(p),
      onAssistantDone: (p) => chat.receiveDone(p),
    })
  }
}

watch(() => auth.token, reconcileSSE)

// Defer SSE and profile loading until router resolves auth state.
// If a stale token is in localStorage, loadProfile() will fail → logout() → token→null → SSE stays off.
app.mount('#app')

if (auth.isAuthenticated) {
  auth.loadProfile().then(() => {
    if (auth.isAuthenticated) reconcileSSE(auth.token)
  })
}
