import MarkdownIt from 'markdown-it'
import markdownItKatex from 'markdown-it-katex'
import { loadKatex } from './katex'
import { hljs, loadHighlightTheme } from './highlight'

let _md: MarkdownIt | null = null
let _katexLoaded = false
let _theme: 'light' | 'dark' = 'light'

export function getMarkdownRenderer(theme?: 'light' | 'dark'): MarkdownIt {
  if (theme && theme !== _theme) {
    loadHighlightTheme(theme === 'dark')
    _theme = theme
  }
  if (!_md) {
    _md = new MarkdownIt({
      html: false,
      linkify: false,
      breaks: true,
      typographer: false,
      highlight: (str: string, lang: string): string => {
        if (lang && hljs.getLanguage(lang)) {
          try {
            return `<pre><code class="hljs language-${lang}">${hljs.highlight(str, { language: lang }).value}</code></pre>`
          } catch { /* fall through */ }
        }
        return `<pre><code>${_md!.utils.escapeHtml(str)}</code></pre>`
      },
    })
    _md.use(markdownItKatex, { throwOnError: false, errorColor: 'var(--seal)' })
  }
  return _md
}

export function mdToHtml(text: string): string {
  if (!_katexLoaded) {
    _katexLoaded = true
    void loadKatex()
  }
  return getMarkdownRenderer().render(text)
}

export function setMarkdownTheme(theme: 'light' | 'dark'): void {
  _theme = theme
  loadHighlightTheme(theme === 'dark')
}
