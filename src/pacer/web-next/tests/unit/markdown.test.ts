import { describe, it, expect } from 'vitest'
import { mdToHtml } from '@/utils/markdown'

describe('mdToHtml', () => {
  it('escapes HTML entities', () => {
    const out = mdToHtml('<script>x</script>')
    expect(out).toContain('&lt;script&gt;x&lt;/script&gt;')
    expect(out).not.toContain('<script>')
  })

  it('renders inline code', () => {
    const out = mdToHtml('use `let x = 1`')
    expect(out).toContain('<code>let x = 1</code>')
  })

  it('renders fenced code blocks', () => {
    const out = mdToHtml('```js\nconst a = 1\n```')
    expect(out).toContain('<pre><code')
    expect(out).toContain('hljs')
  })

  it('renders bold', () => {
    expect(mdToHtml('this is **bold**')).toContain('<strong>bold</strong>')
  })

  it('converts newlines to <br>', () => {
    expect(mdToHtml('line1\nline2')).toContain('<br>')
  })

  it('handles ampersand correctly before other replacements', () => {
    expect(mdToHtml('a & b')).toContain('a &amp; b')
  })

  it('handles empty input', () => {
    expect(mdToHtml('')).toBe('')
  })
})
