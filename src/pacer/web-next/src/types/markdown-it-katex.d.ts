declare module 'markdown-it-katex' {
  import type MarkdownIt from 'markdown-it'
  function markdownItKatex(md: MarkdownIt, options?: Record<string, unknown>): void
  export default markdownItKatex
}
