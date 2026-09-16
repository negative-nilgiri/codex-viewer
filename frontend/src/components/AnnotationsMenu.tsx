import { useRef, useState, type FormEvent } from 'react'
import type { Annotation } from '../api'

function location(annotation: Annotation) {
  const lines =
    annotation.start_line === annotation.end_line
      ? `line ${annotation.start_line}`
      : `lines ${annotation.start_line}–${annotation.end_line}`
  return annotation.message_index ? `#${annotation.message_index} · ${lines}` : lines
}

function excerpt(value: string) {
  const compact = value.replace(/\s+/g, ' ').trim()
  return compact.length > 110 ? `${compact.slice(0, 109)}…` : compact
}

export function AnnotationsMenu({
  annotations,
  onDelete,
  onNavigate,
  onUpdate,
}: {
  annotations: Annotation[]
  onDelete: (annotation: Annotation) => Promise<void>
  onNavigate: (annotation: Annotation) => void
  onUpdate: (annotation: Annotation, note: string) => Promise<void>
}) {
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [working, setWorking] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const menu = useRef<HTMLDetailsElement>(null)

  async function save(event: FormEvent, annotation: Annotation) {
    event.preventDefault()
    if (!draft.trim() || working !== null) return
    setWorking(annotation.id)
    setError(null)
    try {
      await onUpdate(annotation, draft.trim())
      setEditing(null)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setWorking(null)
    }
  }

  async function remove(annotation: Annotation) {
    if (working !== null) return
    if (!window.confirm('Delete this annotation?')) return
    setWorking(annotation.id)
    setError(null)
    try {
      await onDelete(annotation)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setWorking(null)
    }
  }

  return (
    <details className="annotations-menu" ref={menu}>
      <summary>Annotations{annotations.length ? ` (${annotations.length})` : ''}</summary>
      <div className="annotations-popover">
        {error && <p className="annotation-menu-error">{error}</p>}
        {annotations.length ? (
          annotations.map((annotation) => (
            <div className="annotation-row" key={annotation.id}>
              {editing === annotation.id ? (
                <form onSubmit={(event) => void save(event, annotation)}>
                  <textarea
                    aria-label={`Edit annotation ${annotation.id}`}
                    autoFocus
                    maxLength={20_000}
                    onChange={(event) => setDraft(event.target.value)}
                    rows={3}
                    value={draft}
                  />
                  <div className="annotation-row-actions">
                    <button onClick={() => setEditing(null)} type="button">Cancel</button>
                    <button disabled={working !== null || !draft.trim()} type="submit">
                      {working === annotation.id ? 'Saving…' : 'Save'}
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <button
                    className="annotation-jump"
                    onClick={() => {
                      if (menu.current) menu.current.open = false
                      onNavigate(annotation)
                    }}
                    title="Jump to annotated passage"
                    type="button"
                  >
                    <span>{location(annotation)}</span>
                    <strong>{annotation.note}</strong>
                    <q>{excerpt(annotation.selected_text)}</q>
                  </button>
                  <div className="annotation-row-actions">
                    <button
                      aria-label="Edit annotation"
                      onClick={() => {
                        setDraft(annotation.note)
                        setEditing(annotation.id)
                      }}
                      title="Edit annotation"
                      type="button"
                    >
                      ✎
                    </button>
                    <button
                      aria-label="Delete annotation"
                      disabled={working !== null}
                      onClick={() => void remove(annotation)}
                      title="Delete annotation"
                      type="button"
                    >
                      ×
                    </button>
                  </div>
                </>
              )}
            </div>
          ))
        ) : (
          <p className="annotations-empty">
            Select text in the rendered Markdown to add an annotation.
          </p>
        )}
      </div>
    </details>
  )
}
