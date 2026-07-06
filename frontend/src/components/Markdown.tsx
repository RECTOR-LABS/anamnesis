import type { ReactNode } from 'react'

/** A tiny, dependency-free renderer for the markdown subset the agent emits — headings (`#`…),
 * unordered / ordered lists, paragraphs, and inline **bold**, `code`, and [text](url) links. It
 * builds React elements directly (never `dangerouslySetInnerHTML`), so any raw HTML in the model's
 * output is escaped as text, and link hrefs are restricted to relative / http(s) / mailto — the
 * chat renders untrusted LLM output, so it must be safe by construction (see
 * anamnesis-render-escaping-poisoning-xss). Unrecognised markdown degrades to plain (escaped)
 * text, never a crash. Chosen over a markdown library to keep this zero-runtime-dep frontend so. */

// Inline: link | bold | code. First matching alternative wins; everything else stays plain text.
const INLINE = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+?)\*\*|`([^`]+?)`/g

/** Allow only relative (`/…`, `#…`) or http(s) / mailto hrefs; reject `javascript:`, `data:`, … */
function safeHref(url: string): string | null {
  const u = url.trim()
  if (u.startsWith('/') || u.startsWith('#')) return u
  if (/^(https?:\/\/|mailto:)/i.test(u)) return u
  return null
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let n = 0
  let m: RegExpExecArray | null
  INLINE.lastIndex = 0
  while ((m = INLINE.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const key = `${keyPrefix}-${n++}`
    if (m[1] !== undefined) {
      const href = safeHref(m[2])
      out.push(
        href ? (
          <a key={key} href={href} target="_blank" rel="noopener noreferrer">
            {m[1]}
          </a>
        ) : (
          m[1] // unsafe URL → drop the link, keep the visible text
        ),
      )
    } else if (m[3] !== undefined) {
      out.push(<strong key={key}>{m[3]}</strong>)
    } else {
      out.push(<code key={key}>{m[4]}</code>)
    }
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const HEADING = /^(#{1,6})\s+(.*)$/
const BULLET = /^\s*[-*]\s+/
const ORDERED = /^\s*\d+\.\s+/

export function Markdown({ text }: { text: string }): ReactNode {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let key = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.trim() === '') {
      i++
      continue
    }
    const h = HEADING.exec(line)
    if (h) {
      blocks.push(
        <div key={key++} className="md-h">
          {renderInline(h[2], `h${key}`)}
        </div>,
      )
      i++
      continue
    }
    if (BULLET.test(line) || ORDERED.test(line)) {
      const ordered = ORDERED.test(line)
      const items: ReactNode[] = []
      while (i < lines.length && (BULLET.test(lines[i]) || ORDERED.test(lines[i]))) {
        const itemText = lines[i].replace(/^\s*(?:[-*]|\d+\.)\s+/, '')
        items.push(<li key={items.length}>{renderInline(itemText, `li${key}-${items.length}`)}</li>)
        i++
      }
      blocks.push(
        ordered ? (
          <ol key={key++} className="md-ul">
            {items}
          </ol>
        ) : (
          <ul key={key++} className="md-ul">
            {items}
          </ul>
        ),
      )
      continue
    }
    // Paragraph: gather consecutive plain lines (joined with a space, matching markdown soft-wrap).
    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !HEADING.test(lines[i]) &&
      !BULLET.test(lines[i]) &&
      !ORDERED.test(lines[i])
    ) {
      para.push(lines[i])
      i++
    }
    blocks.push(<p key={key++}>{renderInline(para.join(' '), `p${key}`)}</p>)
  }
  return <>{blocks}</>
}
