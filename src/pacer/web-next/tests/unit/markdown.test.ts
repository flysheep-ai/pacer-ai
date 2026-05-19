import { describe, it, expect } from 'vitest'
import { mdToHtml } from '@/utils/markdown'

describe('mdToHtml', () => {
  it('escapes HTML entities', () => {
    expect(mdToHtml('<script>x</script>'))
      .toBe('&lt;script&gt;x&lt;/script&gt;')
  })

  it('renders inline code', () => {
    expect(mdToHtml('use `let x = 1`'))
      .toBe('use <code>let x = 1</code>')
  })

  it('renders fenced code blocks', () => {
    const out = mdToHtml('```js\nconst a = 1\n```')
    expect(out).toBe('<pre><code>const a = 1\n</code></pre>')
  })

  it('renders bold', () => {
    expect(mdToHtml('this is **bold**'))
      .toBe('this is <strong>bold</strong>')
  })

  it('converts newlines to <br>', () => {
    expect(mdToHtml('line1\nline2'))
      .toBe('line1<br>line2')
  })

  it('handles ampersand correctly before other replacements', () => {
    expect(mdToHtml('a & b'))
      .toBe('a &amp; b')
  })

  it('handles empty input', () => {
    expect(mdToHtml('')).toBe('')
  })
})
