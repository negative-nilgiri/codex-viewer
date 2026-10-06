import { useState, type FormEvent } from 'react'
import type { Annotation } from '../api'
import { annotationParts, formatAnnotations } from '../annotationCopy'
import { CopyButton } from './CopyButton'

function lineRange(annotation: Annotation) {
  return annotation.start_line === annotation.end_line
    ? `line ${annotation.start_line}`
    : `lines ${annotation.start_line}–${annotation.end_line}`
}

function groupAnnotations(annotations: Annotation[]) {
  const groups: Array<{ key: string; label: string; items: Annotation[] }> = []
  for (const annotation of annotations) {
    const key = String(annotation.message_index ?? annotation.document_path ?? '')
    const current = groups.at(-1)
    if (current?.key === key) {
      current.items.push(annotation)
    } else {
      groups.push({
        key,
        label: annotationParts(annotation).label ?? 'Annotations',
        items: [annotation],
      })
    }
  }
  return groups
}

export function AnnotationsToggle({
  count,
  onToggle,
  open,
}: {
  count: number
  onToggle: () => void
  open: boolean
}) {
  return (
    <button aria-expanded={open} onClick={onToggle} type="button">
      Annotations{count ? ` (${count})` : ''}
    </button>
  )
}

export function AnnotationsPanel({
  annotations,
  onClose,
  onDelete,
  onNavigate,
  onUpdate,
}: {
  annotations: Annotation[]
  onClose: () => void
  onDelete: (annotation: Annotation) => Promise<void>
  onNavigate: (annotation: Annotation) => void
  onUpdate: (annotation: Annotation, note: string) => Promise<void>
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [editing, setEditing] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const [working, setWorking] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const selectedAnnotations = annotations.filter((annotation) =>
    selected.has(annotation.id),
  )
  const allSelected =
    annotations.length > 0 && selectedAnnotations.length === annotations.length

  function toggleSelected(id: number) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

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
    <aside aria-label="Annotations" className="annotations-panel">
      <header className="annotations-panel-header">
        <strong>Annotations{annotations.length ? ` (${annotations.length})` : ''}</strong>
        <button aria-label="Close annotations" onClick={onClose} title="Close" type="button">
          ×
        </button>
      </header>
      {annotations.length > 0 && (
        <div className="annotations-toolbar">
          <label className="annotation-select">
            <input
              checked={allSelected}
              onChange={() =>
                setSelected(
                  allSelected ? new Set() : new Set(annotations.map((item) => item.id)),
                )
              }
              ref={(input) => {
                if (input) {
                  input.indeterminate = !allSelected && selectedAnnotations.length > 0
                }
              }}
              type="checkbox"
            />
            <span>All</span>
          </label>
          <CopyButton
            disabled={selectedAnnotations.length === 0}
            idleLabel={`Copy selected (${selectedAnnotations.length})`}
            label="Copy selected annotations as Markdown"
            text={formatAnnotations(selectedAnnotations)}
          />
          <CopyButton
            idleLabel="Copy all"
            label="Copy all annotations as Markdown"
            text={formatAnnotations(annotations)}
          />
        </div>
      )}
      <div className="annotations-panel-scroll">
        {error && <p className="annotation-menu-error">{error}</p>}
        {annotations.length === 0 && (
          <p className="annotations-empty">
            Select text in the rendered Markdown to add an annotation.
          </p>
        )}
        {groupAnnotations(annotations).map((group) => (
          <section className="annotation-group" key={group.key}>
            <header>
              <strong>{group.label}</strong>
              <CopyButton
                idleLabel="Copy group"
                label={`Copy the annotations of ${group.label} as Markdown`}
                text={formatAnnotations(group.items)}
              />
            </header>
            {group.items.map((annotation) => {
              const parts = annotationParts(annotation)
              return (
                <article className="annotation-item" key={annotation.id}>
                  <div className="annotation-item-bar">
                    <label className="annotation-select">
                      <input
                        checked={selected.has(annotation.id)}
                        onChange={() => toggleSelected(annotation.id)}
                        type="checkbox"
                      />
                      <span>{lineRange(annotation)}</span>
                    </label>
                    <div className="annotation-item-actions">
                      <button
                        onClick={() => onNavigate(annotation)}
                        title="Jump to annotated passage"
                        type="button"
                      >
                        Jump
                      </button>
                      <CopyButton
                        label="Copy annotation as Markdown"
                        text={formatAnnotations([annotation])}
                      />
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
                  </div>
                  <div className="annotation-preview">
                    {parts.headings.length > 0 && (
                      <div className="annotation-headings">
                        {parts.headings.map((heading, index) => (
                          <div key={`${index}-${heading}`}>{heading}</div>
                        ))}
                      </div>
                    )}
                    {parts.quote.kind === 'code' ? (
                      <pre className="annotation-quote annotation-quote--code">
                        <code>{parts.quote.text}</code>
                      </pre>
                    ) : (
                      <blockquote
                        className="annotation-quote"
                        title={
                          parts.quote.rendered
                            ? 'Rendered text: the Markdown source was not saved for this annotation'
                            : undefined
                        }
                      >
                        {parts.quote.text}
                      </blockquote>
                    )}
                    {editing === annotation.id ? (
                      <form onSubmit={(event) => void save(event, annotation)}>
                        <textarea
                          aria-label={`Edit annotation ${annotation.id}`}
                          autoFocus
                          className="annotation-panel-textarea"
                          maxLength={20_000}
                          onChange={(event) => setDraft(event.target.value)}
                          rows={3}
                          value={draft}
                        />
                        <div className="annotation-item-actions">
                          <button onClick={() => setEditing(null)} type="button">
                            Cancel
                          </button>
                          <button disabled={working !== null || !draft.trim()} type="submit">
                            {working === annotation.id ? 'Saving…' : 'Save'}
                          </button>
                        </div>
                      </form>
                    ) : (
                      <p className="annotation-note">{parts.note}</p>
                    )}
                  </div>
                </article>
              )
            })}
          </section>
        ))}
      </div>
    </aside>
  )
}
