export type MarkdownHeading = {
  depth: number
  id: string
  line: number
  slug: string
  text: string
}

function headingText(value: string) {
  return value
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/<[^>]+>/g, '')
    .replace(/[`*_~]/g, '')
    .replace(/\\([^\s])/g, '$1')
    .trim()
}

export function headingSlug(value: string) {
  return value
    .trim()
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}\p{Mark}\s_-]/gu, '')
    .replace(/\s+/g, '-')
}

export function extractHeadings(markdown: string, scope: string): MarkdownHeading[] {
  const lines = markdown.split(/\r?\n/)
  const candidates: Array<{ depth: number; line: number; text: string }> = []
  let fence: { character: string; length: number } | null = null

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})/)
    if (fenceMatch) {
      const marker = fenceMatch[1]
      if (!fence) {
        fence = { character: marker[0], length: marker.length }
      } else if (marker[0] === fence.character && marker.length >= fence.length) {
        fence = null
      }
      continue
    }
    if (fence) continue

    const atx = line.match(/^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$/)
    if (atx) {
      const source = (atx[2] ?? '').replace(/[ \t]+#+[ \t]*$/, '')
      const text = headingText(source)
      if (text) candidates.push({ depth: atx[1].length, line: index + 1, text })
      continue
    }

    if (index + 1 < lines.length && line.trim()) {
      const setext = lines[index + 1].match(/^ {0,3}(=+|-+)[ \t]*$/)
      if (setext) {
        const text = headingText(line.trim())
        if (text) {
          candidates.push({ depth: setext[1][0] === '=' ? 1 : 2, line: index + 1, text })
          index += 1
        }
      }
    }
  }

  const occurrences = new Map<string, number>()
  return candidates.map((heading) => {
    const base = headingSlug(heading.text) || 'heading'
    const occurrence = occurrences.get(base) ?? 0
    occurrences.set(base, occurrence + 1)
    const slug = occurrence === 0 ? base : `${base}-${occurrence}`
    return { ...heading, id: `${scope}--${slug}`, slug }
  })
}

export function scrollHeadingIntoView(id: string) {
  document.getElementById(id)?.scrollIntoView({ block: 'start' })
}

export function scrollToHeadingAfterLayout(id: string) {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => scrollHeadingIntoView(id))
  })
}
