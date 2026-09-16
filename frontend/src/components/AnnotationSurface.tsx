import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import type { Annotation, AnnotationDraft } from '../api'

type IndexedText = {
  node: Text
  start: number
  end: number
  startLine: number | null
  endLine: number | null
}

type TextIndex = {
  content: string
  items: IndexedText[]
}

type PendingSelection = Omit<AnnotationDraft, 'note'> & {
  left: number
  top: number
}

type HighlightRegistry = {
  delete: (name: string) => void
  set: (name: string, highlight: unknown) => void
}

type HighlightConstructor = new (...ranges: Range[]) => unknown

const annotationRanges = new Map<string, Range[]>()
const focusedRanges = new Map<string, Range[]>()

function registry() {
  return (CSS as unknown as { highlights?: HighlightRegistry }).highlights
}

function highlightConstructor() {
  return (window as unknown as { Highlight?: HighlightConstructor }).Highlight
}

function refreshHighlight(name: string, owners: Map<string, Range[]>) {
  const highlights = registry()
  const Highlight = highlightConstructor()
  if (!highlights || !Highlight) return false
  const ranges = [...owners.values()].flat()
  if (ranges.length) highlights.set(name, new Highlight(...ranges))
  else highlights.delete(name)
  return true
}

function setOwnerRanges(
  owner: string,
  ranges: Range[],
  focused: Range[],
) {
  if (ranges.length) annotationRanges.set(owner, ranges)
  else annotationRanges.delete(owner)
  if (focused.length) focusedRanges.set(owner, focused)
  else focusedRanges.delete(owner)
  const supported = refreshHighlight('viewer-annotations', annotationRanges)
  refreshHighlight('viewer-annotation-focus', focusedRanges)
  return supported
}

function clearOwnerRanges(owner: string) {
  annotationRanges.delete(owner)
  focusedRanges.delete(owner)
  refreshHighlight('viewer-annotations', annotationRanges)
  refreshHighlight('viewer-annotation-focus', focusedRanges)
}

function sourceLines(node: Text) {
  const positioned = node.parentElement?.closest<HTMLElement>('[data-source-start-line]')
  if (!positioned) return { startLine: null, endLine: null }
  const startLine = Number(positioned.dataset.sourceStartLine)
  const endLine = Number(positioned.dataset.sourceEndLine)
  return {
    startLine: Number.isInteger(startLine) ? startLine : null,
    endLine: Number.isInteger(endLine) ? endLine : null,
  }
}

function ignoredText(node: Text, root: HTMLElement) {
  const parent = node.parentElement
  if (!parent || !root.contains(parent)) return true
  return Boolean(
    parent.closest(
      'button, [data-annotation-ignore="true"], .mermaid-toolbar, .mermaid-svg',
    ),
  )
}

function indexText(root: HTMLElement): TextIndex {
  const items: IndexedText[] = []
  const parts: string[] = []
  let offset = 0
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let current = walker.nextNode()
  while (current) {
    const node = current as Text
    if (!ignoredText(node, root) && node.data.length) {
      const lines = sourceLines(node)
      items.push({
        node,
        start: offset,
        end: offset + node.data.length,
        ...lines,
      })
      parts.push(node.data)
      offset += node.data.length
    }
    current = walker.nextNode()
  }
  return { content: parts.join(''), items }
}

function rangeForOffsets(index: TextIndex, start: number, end: number) {
  const first = index.items.find((item) => start >= item.start && start < item.end)
  const last = [...index.items]
    .reverse()
    .find((item) => end > item.start && end <= item.end)
  if (!first || !last) return null
  const range = document.createRange()
  range.setStart(first.node, start - first.start)
  range.setEnd(last.node, end - last.start)
  return range
}

function candidateScore(
  annotation: Annotation,
  index: TextIndex,
  start: number,
) {
  const end = start + annotation.selected_text.length
  let score = 0
  if (index.content.slice(Math.max(0, start - annotation.prefix.length), start) === annotation.prefix) {
    score += 8
  }
  if (index.content.slice(end, end + annotation.suffix.length) === annotation.suffix) {
    score += 8
  }
  const item = index.items.find((candidate) => start >= candidate.start && start < candidate.end)
  if (
    item &&
    item.startLine !== null &&
    item.endLine !== null &&
    annotation.start_line >= item.startLine &&
    annotation.start_line <= item.endLine
  ) {
    score += 4
  }
  return score
}

function resolveAnnotation(annotation: Annotation, index: TextIndex) {
  let occurrence = index.content.indexOf(annotation.selected_text)
  let best: { start: number; score: number } | null = null
  while (occurrence >= 0) {
    const score = candidateScore(annotation, index, occurrence)
    if (!best || score > best.score) best = { start: occurrence, score }
    occurrence = index.content.indexOf(annotation.selected_text, occurrence + 1)
  }
  if (!best) return null
  return rangeForOffsets(
    index,
    best.start,
    best.start + annotation.selected_text.length,
  )
}

function localOffset(node: Text, container: Node, offset: number, edge: 'start' | 'end') {
  if (container === node) return Math.min(offset, node.data.length)
  return edge === 'start' ? 0 : node.data.length
}

function refinedLines(
  markdown: string,
  selectedText: string,
  prefix: string,
  suffix: string,
  blockStart: number,
  blockEnd: number,
) {
  const candidates: Array<{ startLine: number; endLine: number; score: number }> = []
  let occurrence = markdown.indexOf(selectedText)
  while (occurrence >= 0) {
    const startLine = markdown.slice(0, occurrence).split('\n').length
    const endLine = startLine + selectedText.split('\n').length - 1
    if (startLine >= blockStart && startLine <= blockEnd) {
      const before = markdown.slice(Math.max(0, occurrence - prefix.length), occurrence)
      const after = markdown.slice(
        occurrence + selectedText.length,
        occurrence + selectedText.length + suffix.length,
      )
      candidates.push({
        startLine,
        endLine,
        score: (before === prefix ? 1 : 0) + (after === suffix ? 1 : 0),
      })
    }
    occurrence = markdown.indexOf(selectedText, occurrence + 1)
  }
  candidates.sort((left, right) => right.score - left.score)
  if (candidates.length === 1 || candidates[0]?.score > candidates[1]?.score) {
    return candidates[0]
  }
  return null
}

function captureSelection(root: HTMLElement, markdown: string): PendingSelection | null {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null

  const index = indexText(root)
  const selectedItems = index.items.filter((item) => {
    try {
      return range.intersectsNode(item.node)
    } catch {
      return false
    }
  })
  if (!selectedItems.length) return null
  const first = selectedItems[0]
  const last = selectedItems[selectedItems.length - 1]
  const start = first.start + localOffset(first.node, range.startContainer, range.startOffset, 'start')
  const end = last.start + localOffset(last.node, range.endContainer, range.endOffset, 'end')
  const selectedText = index.content.slice(start, end)
  const startLine = first.startLine
  const endLine = last.endLine
  if (!selectedText.trim() || startLine === null || endLine === null) return null
  if (selectedText.length > 100_000) return null

  const prefix = index.content.slice(Math.max(0, start - 160), start)
  const suffix = index.content.slice(end, end + 160)
  const blockStart = Math.min(startLine, endLine)
  const blockEnd = Math.max(startLine, endLine)
  const exactLines = refinedLines(
    markdown,
    selectedText,
    prefix,
    suffix,
    blockStart,
    blockEnd,
  )
  const rectangle = range.getBoundingClientRect()
  return {
    start_line: exactLines?.startLine ?? blockStart,
    end_line: exactLines?.endLine ?? blockEnd,
    selected_text: selectedText,
    prefix,
    suffix,
    left: rectangle.left,
    top: rectangle.bottom + 8,
  }
}

function lineTarget(root: HTMLElement, annotation: Annotation) {
  return [...root.querySelectorAll<HTMLElement>('[data-source-start-line]')].find(
    (element) => {
      const start = Number(element.dataset.sourceStartLine)
      const end = Number(element.dataset.sourceEndLine)
      return start <= annotation.start_line && end >= annotation.start_line
    },
  )
}

export function AnnotationSurface({
  annotations,
  children,
  contentKey,
  focusAnnotationId,
  onCreate,
  onFocused,
  owner,
}: {
  annotations: Annotation[]
  children: ReactNode
  contentKey: string
  focusAnnotationId?: number | null
  onCreate: (draft: AnnotationDraft) => Promise<void>
  onFocused?: (annotationId: number) => void
  owner: string
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [pending, setPending] = useState<PendingSelection | null>(null)
  const [editing, setEditing] = useState(false)
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return
    const index = indexText(root)
    const resolved = new Map<number, Range>()
    for (const annotation of annotations) {
      const range = resolveAnnotation(annotation, index)
      if (range) resolved.set(annotation.id, range)
    }
    const focused = focusAnnotationId ? resolved.get(focusAnnotationId) : undefined
    const supported = setOwnerRanges(owner, [...resolved.values()], focused ? [focused] : [])

    const fallbackTargets: HTMLElement[] = []
    if (!supported) {
      for (const annotation of annotations) {
        const target = lineTarget(root, annotation)
        if (target && !fallbackTargets.includes(target)) {
          target.classList.add('annotation-line-fallback')
          fallbackTargets.push(target)
        }
      }
    }

    let focusTimer: number | undefined
    let focusTarget: HTMLElement | undefined
    if (focusAnnotationId) {
      const annotation = annotations.find((item) => item.id === focusAnnotationId)
      const target = focused?.startContainer.parentElement?.closest<HTMLElement>(
        '[data-source-start-line]',
      ) ?? (annotation ? lineTarget(root, annotation) : undefined)
      if (target) {
        focusTarget = target
        target.scrollIntoView({ block: 'center' })
        target.classList.add('annotation-focus-target')
        focusTimer = window.setTimeout(() => {
          target.classList.remove('annotation-focus-target')
          onFocused?.(focusAnnotationId)
        }, 1800)
      } else {
        onFocused?.(focusAnnotationId)
      }
    }

    return () => {
      fallbackTargets.forEach((target) => target.classList.remove('annotation-line-fallback'))
      if (focusTimer !== undefined) {
        window.clearTimeout(focusTimer)
        focusTarget?.classList.remove('annotation-focus-target')
      }
      clearOwnerRanges(owner)
    }
  }, [annotations, contentKey, focusAnnotationId, onFocused, owner])

  useEffect(() => () => clearOwnerRanges(owner), [owner])

  useEffect(() => {
    if (!pending || editing) return

    function dismissOnPointer(event: PointerEvent) {
      if (triggerRef.current?.contains(event.target as Node)) return
      setPending(null)
    }

    function dismissOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setPending(null)
    }

    function dismissOnScroll() {
      setPending(null)
    }

    document.addEventListener('pointerdown', dismissOnPointer, true)
    window.addEventListener('keydown', dismissOnEscape)
    window.addEventListener('scroll', dismissOnScroll, true)
    return () => {
      document.removeEventListener('pointerdown', dismissOnPointer, true)
      window.removeEventListener('keydown', dismissOnEscape)
      window.removeEventListener('scroll', dismissOnScroll, true)
    }
  }, [editing, pending])

  function inspectSelection() {
    const root = rootRef.current
    if (!root) return
    const captured = captureSelection(root, contentKey)
    if (!captured) {
      if (!editing) setPending(null)
      return
    }
    setPending(captured)
    setEditing(false)
    setNote('')
    setError(null)
  }

  function closeEditor() {
    setPending(null)
    setEditing(false)
    setNote('')
    setError(null)
    window.getSelection()?.removeAllRanges()
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!pending || !note.trim() || saving) return
    setSaving(true)
    setError(null)
    try {
      await onCreate({
        start_line: pending.start_line,
        end_line: pending.end_line,
        selected_text: pending.selected_text,
        prefix: pending.prefix,
        suffix: pending.suffix,
        note: note.trim(),
      })
      closeEditor()
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setSaving(false)
    }
  }

  function editorKeyDown(event: ReactKeyboardEvent<HTMLFormElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeEditor()
    }
  }

  return (
    <>
      <div
        className="rendered-markdown"
        onKeyUp={inspectSelection}
        onMouseUp={inspectSelection}
        ref={rootRef}
      >
        {children}
      </div>
      {pending && !editing &&
        createPortal(
          <button
            className="annotation-trigger"
            onClick={() => setEditing(true)}
            onMouseDown={(event) => event.preventDefault()}
            ref={triggerRef}
            style={{
              left: Math.max(8, Math.min(pending.left, window.innerWidth - 100)),
              top: Math.max(8, Math.min(pending.top, window.innerHeight - 42)),
            }}
            type="button"
          >
            Annotate
          </button>,
          document.body,
        )}
      {pending && editing &&
        createPortal(
          <form
            className="annotation-editor"
            onKeyDown={editorKeyDown}
            onSubmit={save}
            style={{
              left: Math.max(12, Math.min(pending.left, window.innerWidth - 372)),
              top: Math.max(12, Math.min(pending.top, window.innerHeight - 240)),
            }}
          >
            <div className="annotation-editor-heading">
              <strong>Annotate selection</strong>
              <span>
                lines {pending.start_line}
                {pending.end_line === pending.start_line ? '' : `–${pending.end_line}`}
              </span>
            </div>
            <blockquote>{pending.selected_text.trim().slice(0, 240)}</blockquote>
            <textarea
              aria-label="Annotation note"
              autoFocus
              maxLength={20_000}
              onChange={(event) => setNote(event.target.value)}
              placeholder="What do you want to remember or ask later?"
              required
              rows={3}
              value={note}
            />
            {error && <span className="annotation-editor-error">{error}</span>}
            <div className="annotation-editor-actions">
              <button disabled={saving} onClick={closeEditor} type="button">
                Cancel
              </button>
              <button disabled={saving || !note.trim()} type="submit">
                {saving ? 'Saving…' : 'Save annotation'}
              </button>
            </div>
          </form>,
          document.body,
        )}
    </>
  )
}
