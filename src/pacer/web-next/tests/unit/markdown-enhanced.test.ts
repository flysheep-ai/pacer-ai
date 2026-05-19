import { describe, it, expect } from 'vitest'
import { mdToHtml } from '@/utils/markdown'

describe('mdToHtml (markdown-it enhanced)', () => {
  it('renders tables', () => {
    const out = mdToHtml('|a|b|\n|-|-|\n|1|2|')
    expect(out).toContain('<table>')
  })
  it('renders headings', () => {
    expect(mdToHtml('# Title')).toContain('<h1')
  })
  it('renders inline math', () => {
    expect(mdToHtml('$x^2$')).toContain('katex')
  })
  it('renders block math', () => {
    expect(mdToHtml('$$\nx^2\n$$')).toContain('katex')
  })
  it('renders fenced code with syntax highlighting', () => {
    const out = mdToHtml('```python\nprint(1)\n```')
    expect(out).toContain('hljs')
    expect(out).toContain('language-python')
  })
  it('escapes HTML', () => {
    const out = mdToHtml('<script>alert(1)</script>')
    expect(out).not.toContain('<script>')
  })
  it('renders bold', () => {
    expect(mdToHtml('**bold**')).toContain('<strong>')
  })
  it('handles empty input', () => {
    expect(mdToHtml('')).toBe('')
  })
})
