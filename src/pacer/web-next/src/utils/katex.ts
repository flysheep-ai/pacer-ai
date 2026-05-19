let _katexCssLoaded = false

export async function loadKatex(): Promise<void> {
  if (typeof window === 'undefined') return
  if (!_katexCssLoaded) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css'
    document.head.appendChild(link)
    _katexCssLoaded = true
  }
}
