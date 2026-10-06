import type { Annotation } from './api'

export type AnnotationQuote =
  | { kind: 'code'; language: string; text: string }
  | { kind: 'quote'; text: string; rendered: boolean }

export type AnnotationParts = {
  label: string | null
  headings: string[]
  quote: AnnotationQuote
  note: string
}

const FENCE_OPEN = /^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)/
const FENCE_CLOSE = /^ {0,3}(`{3,}|~{3,})[ \t]*$/

function fencedBlock(sourceText: string) {
  const lines = sourceText.split('\n')
  const opening = FENCE_OPEN.exec(lines[0] ?? '')
  if (!opening) return null
  const closed = lines.length > 1 && FENCE_CLOSE.test(lines[lines.length - 1])
  return {
    language: opening[2],
    body: lines.slice(1, closed ? -1 : undefined).join('\n'),
  }
}

function codeQuote(annotation: Annotation, selected: string): AnnotationQuote | null {
  const source = annotation.source_text
  if (source === null) return null
  let language: string
  let body: string
  if (annotation.source_fence !== null) {
    language = annotation.source_fence
    body = source
  } else {
    const block = fencedBlock(source)
    if (!block) return null
    language = block.language
    body = block.body
  }
  const wanted = selected.replace(/\n+$/, '')
  return {
    kind: 'code',
    language,
    text: wanted.trim() && body.includes(wanted) ? wanted : body,
  }
}

function annotationQuote(annotation: Annotation): AnnotationQuote {
  const selected = annotation.selected_text
  const source = annotation.source_text
  if (source === null) return { kind: 'quote', text: selected.trim(), rendered: true }
  const code = codeQuote(annotation, selected)
  if (code) return code
  // Rendered text matches the source for plain prose; math and inline formatting
  // render differently, so those fall back to the whole source block.
  const wanted = selected.trim()
  return {
    kind: 'quote',
    text: wanted && source.includes(wanted) ? wanted : source,
    rendered: false,
  }
}

function annotationLabel(annotation: Annotation) {
  if (annotation.message_index !== null) return `Message #${annotation.message_index}`
  if (annotation.document_path) return `Document ${annotation.document_path}`
  return null
}

export function annotationParts(annotation: Annotation): AnnotationParts {
  return {
    label: annotationLabel(annotation),
    headings: annotation.source_context
      ? annotation.source_context.split('\n').filter(Boolean)
      : [],
    quote: annotationQuote(annotation),
    note: annotation.note,
  }
}

function fenced(text: string, language: string) {
  const longest = Math.max(2, ...(text.match(/`+/g) ?? []).map((run) => run.length))
  const fence = '`'.repeat(longest + 1)
  return `${fence}${language}\n${text}\n${fence}`
}

function blockquote(text: string) {
  return text
    .split('\n')
    .map((line) => (line ? `> ${line}` : '>'))
    .join('\n')
}

export function formatAnnotation(annotation: Annotation) {
  const { label, headings, quote, note } = annotationParts(annotation)
  const quoted =
    quote.kind === 'code' ? fenced(quote.text, quote.language) : blockquote(quote.text)
  const head = [label === null ? null : `**${label}**`, ...headings, quoted]
  return `${head.filter((line) => line !== null).join('\n')}\n\n${note}`
}

export function formatAnnotations(annotations: Annotation[]) {
  return annotations.map(formatAnnotation).join('\n\n---\n\n')
}
