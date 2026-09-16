import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { Annotation, AnnotationDraft, Message } from './api'
import { CopyButton } from './components/CopyButton'
import {
  MarkdownOutline,
  MarkdownRenderer,
} from './components/MarkdownRenderer'
import { extractHeadings, scrollToHeadingAfterLayout } from './markdown'

function displayTime(value: string | null) {
  if (!value) return 'Unknown time'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

export const MessageCard = memo(function MessageCard({
  annotations,
  bookmarked,
  collapsed,
  focusAnnotationId,
  message,
  onAnnotationFocused,
  onAnnotate,
  onBookmark,
  onToggle,
}: {
  annotations: Annotation[]
  bookmarked: boolean
  collapsed: boolean
  focusAnnotationId?: number | null
  message: Message
  onAnnotationFocused: (annotationId: number) => void
  onAnnotate: (message: Message, draft: AnnotationDraft) => Promise<void>
  onBookmark: (message: Message) => void
  onToggle: (messageIndex: number) => void
}) {
  const [outlineOpen, setOutlineOpen] = useState(false)
  const [showBackToTop, setShowBackToTop] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const messageRef = useRef<HTMLElement>(null)
  const scope = `message-${message.message_index}`
  const headings = useMemo(
    () => extractHeadings(message.markdown, scope),
    [message.markdown, scope],
  )

  useEffect(() => {
    const content = contentRef.current
    if (collapsed || !content) return

    function measure() {
      const viewportHeight =
        content?.closest<HTMLElement>('.virtual-transcript')?.clientHeight ??
        window.innerHeight
      const contentHeight = content?.getBoundingClientRect().height ?? 0
      setShowBackToTop(contentHeight > Math.max(viewportHeight * 1.4, 800))
    }

    const frame = requestAnimationFrame(measure)
    const observer = new ResizeObserver(measure)
    observer.observe(content)
    window.addEventListener('resize', measure)

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [collapsed])

  return (
    <article
      className={`message message--${message.role}${collapsed ? ' message--collapsed' : ''}`}
      ref={messageRef}
    >
      <header>
        <strong>
          [{message.message_index}] {message.role === 'assistant' ? 'AGENT' : 'USER'}
        </strong>
        <div className="message-controls">
          <time>{displayTime(message.timestamp)}</time>
          <button
            aria-label={`${bookmarked ? 'Remove bookmark from' : 'Bookmark'} message ${message.message_index}`}
            aria-pressed={bookmarked}
            className={`bookmark-button${bookmarked ? ' bookmark-button--active' : ''}`}
            onClick={() => onBookmark(message)}
            title={bookmarked ? 'Remove bookmark' : 'Bookmark message'}
            type="button"
          >
            {bookmarked ? '★' : '☆'}
          </button>
          <CopyButton
            className="copy-button--message"
            label="Copy message as Markdown"
            text={message.markdown}
          />
          {!collapsed && headings.length >= 2 && (
            <button
              aria-expanded={outlineOpen}
              className="outline-button"
              onClick={() => setOutlineOpen((open) => !open)}
              title={outlineOpen ? 'Hide message outline' : 'Show message outline'}
              type="button"
            >
              {outlineOpen ? 'Hide outline' : 'Outline'}
            </button>
          )}
          <button
            aria-expanded={!collapsed}
            className="fold-button"
            onClick={() => onToggle(message.message_index)}
            title={collapsed ? 'Expand message' : 'Collapse message'}
            type="button"
          >
            {collapsed ? 'Expand' : 'Fold'}
          </button>
        </div>
      </header>
      {!collapsed && (
        <div className="markdown-body">
          <div className="message-markdown-content" ref={contentRef}>
            {outlineOpen && headings.length >= 2 && (
              <MarkdownOutline
                headings={headings}
                label={`Message ${message.message_index} outline`}
                onNavigate={(heading) => {
                  setOutlineOpen(false)
                  scrollToHeadingAfterLayout(heading.id)
                }}
                title="In this message"
              />
            )}
            <MarkdownRenderer
              annotations={annotations}
              focusAnnotationId={focusAnnotationId}
              headings={headings}
              markdown={message.markdown}
              onAnnotationFocused={onAnnotationFocused}
              onCreateAnnotation={(draft) => onAnnotate(message, draft)}
              scope={scope}
            />
          </div>
          {showBackToTop && (
            <div className="message-back-to-top">
              <button
                onClick={() => messageRef.current?.scrollIntoView({ block: 'start' })}
                title="Go to the top of this message"
                type="button"
              >
                ↑ Top of message
              </button>
            </div>
          )}
        </div>
      )}
    </article>
  )
})
