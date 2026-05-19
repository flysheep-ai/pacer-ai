import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import plaintext from 'highlight.js/lib/languages/plaintext'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('plaintext', plaintext)
hljs.registerLanguage('text', plaintext)

export function loadHighlightTheme(isDark: boolean): void {
  if (typeof window === 'undefined') return
  const id = 'hljs-theme'
  const existing = document.getElementById(id)
  if (existing) existing.remove()
  const link = document.createElement('link')
  link.id = id
  link.rel = 'stylesheet'
  link.href = isDark
    ? 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css'
    : 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css'
  document.head.appendChild(link)
}

export { hljs }
