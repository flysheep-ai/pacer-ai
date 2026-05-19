import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './styles/reset.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'
import { createRouter } from './router'

const app = createApp(App)
app.use(createPinia())
app.use(createRouter())
app.mount('#app')
