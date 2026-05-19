export function mdToHtml(text: string): string {
  // Split on fenced code blocks so newlines inside <pre> are preserved.
  const parts = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .split(/(```\w*\n[\s\S]*?```)/g)

  return parts.map((part, i) => {
    if (i % 2 === 1) {
      // Fenced code block segment — extract language + body
      return part.replace(/```\w*\n([\s\S]*?)```/, '<pre><code>$1</code></pre>')
    }
    return part
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>')
  }).join('')
}
