import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createDocumentAnnotation,
  deleteAnnotation,
  fetchDocument,
  fetchDocumentAnnotations,
  updateAnnotation,
  type Annotation,
  type AnnotationDraft,
  type DocumentSummary,
} from './api'
import { AnnotationsMenu } from './components/AnnotationsMenu'
import { CopyButton } from './components/CopyButton'
import {
  MarkdownOutline,
  MarkdownRenderer,
} from './components/MarkdownRenderer'
import { extractHeadings, scrollToHeadingAfterLayout } from './markdown'

function displaySize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MiB`
}

function displayModified(value: string) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

export function DocumentViewer({ document }: { document: DocumentSummary }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [markdown, setMarkdown] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloading, setReloading] = useState(false)
  const [outlineOpen, setOutlineOpen] = useState(false)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [focusAnnotationId, setFocusAnnotationId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const scope = `document-${document.id}`
  const headings = useMemo(
    () => (markdown === null ? [] : extractHeadings(markdown, scope)),
    [markdown, scope],
  )

  useEffect(() => {
    let active = true
    fetchDocument(document)
      .then((content) => {
        if (active) {
          setMarkdown(content)
          setError(null)
        }
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : String(caught))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [document])

  useEffect(() => {
    let active = true
    fetchDocumentAnnotations(document)
      .then((loaded) => {
        if (active) setAnnotations(loaded)
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : String(caught))
      })
    return () => {
      active = false
    }
  }, [document])

  async function annotate(draft: AnnotationDraft) {
    const created = await createDocumentAnnotation(document, draft)
    setAnnotations((current) => [...current, created].sort((a, b) => a.start_line - b.start_line))
  }

  async function editAnnotation(annotation: Annotation, note: string) {
    const updated = await updateAnnotation(annotation.id, note)
    setAnnotations((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    )
  }

  async function removeAnnotation(annotation: Annotation) {
    await deleteAnnotation(annotation.id)
    setAnnotations((current) => current.filter((item) => item.id !== annotation.id))
  }

  const annotationFocused = useCallback(() => setFocusAnnotationId(null), [])

  async function reload() {
    if (reloading) return
    setReloading(true)
    setError(null)
    try {
      setMarkdown(await fetchDocument(document, true))
      scrollRef.current?.scrollTo({ top: 0 })
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setReloading(false)
    }
  }

  return (
    <>
      <header className="session-header document-header">
        <div className="session-heading">
          <span className="eyebrow">Markdown document</span>
          <h2>{document.title}</h2>
          <p>
            <code>{document.path}</code> · {displaySize(document.size)} · modified{' '}
            {displayModified(document.modified_at)}
          </p>
        </div>
        <div className="session-actions">
          <button onClick={() => scrollRef.current?.scrollTo({ top: 0 })} type="button">
            Beginning
          </button>
          <button
            onClick={() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })}
            type="button"
          >
            End
          </button>
          {headings.length >= 2 && (
            <button
              aria-expanded={outlineOpen}
              onClick={() => setOutlineOpen((current) => !current)}
              type="button"
            >
              {outlineOpen ? 'Hide outline' : 'Outline'}
            </button>
          )}
          <AnnotationsMenu
            annotations={annotations}
            onDelete={removeAnnotation}
            onNavigate={(annotation) => setFocusAnnotationId(annotation.id)}
            onUpdate={editAnnotation}
          />
          <CopyButton
            disabled={markdown === null}
            label="Copy document as Markdown"
            text={markdown ?? ''}
          />
          <button disabled={reloading} onClick={() => void reload()} type="button">
            {reloading ? 'Reloading…' : 'Reload'}
          </button>
        </div>
      </header>
      {error && <div className="status status--error">{error}</div>}
      <div className="document-scroll" ref={scrollRef}>
        {loading ? (
          <div className="empty-transcript">Loading Markdown document…</div>
        ) : markdown !== null ? (
          <article className="document-page markdown-body">
            <div className="message-markdown-content">
              {outlineOpen && headings.length >= 2 && (
                <MarkdownOutline
                  headings={headings}
                  label="Document outline"
                  onNavigate={(heading) => {
                    setOutlineOpen(false)
                    scrollToHeadingAfterLayout(heading.id)
                  }}
                  title="In this document"
                />
              )}
              <MarkdownRenderer
                annotations={annotations}
                focusAnnotationId={focusAnnotationId}
                headings={headings}
                markdown={markdown}
                onAnnotationFocused={annotationFocused}
                onCreateAnnotation={annotate}
                scope={scope}
              />
            </div>
            <div className="message-back-to-top">
              <button
                onClick={() => scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' })}
                type="button"
              >
                ↑ Top of document
              </button>
            </div>
          </article>
        ) : (
          <div className="empty-transcript">The document could not be loaded.</div>
        )}
      </div>
    </>
  )
}
