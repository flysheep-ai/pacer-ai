import { createApp, watch } from 'vue'
import { createPinia } from 'pinia'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'
import { createRouter } from './router'
import { useAuthStore } from './stores/auth'
import { useChatStore } from './stores/chat'
import { startSSE } from './api/sse'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
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

reconcileSSE(auth.token)
watch(() => auth.token, reconcileSSE)

if (auth.isAuthenticated) {
  void auth.loadProfile()
}

app.mount('#app')
