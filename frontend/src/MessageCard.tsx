import {
  Children,
  isValidElement,
  memo,
  type ComponentProps,
  type ReactNode,
} from 'react'
import Markdown, { type Components } from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import rehypeRaw from 'rehype-raw'
import remarkGfm from 'remark-gfm'
import type { Message } from './api'
import { CopyButton } from './components/CopyButton'
import { MermaidDiagram } from './components/MermaidDiagram'
import 'highlight.js/styles/github-dark-dimmed.css'

function textContent(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textContent).join('')
  if (isValidElement<{ children?: ReactNode }>(node)) return textContent(node.props.children)
  return ''
}

function MarkdownPre({ children }: { children?: ReactNode }) {
  const code = Children.toArray(children)[0]
  const className = isValidElement<{ className?: string }>(code)
    ? code.props.className ?? ''
    : ''
  const source = textContent(code).replace(/\n$/, '')

  if (className.split(' ').includes('language-mermaid')) {
    return <MermaidDiagram source={source} />
  }

  return (
    <div className="code-block">
      <CopyButton className="copy-button--code" label="Copy code" text={source} />
      <pre>{children}</pre>
    </div>
  )
}

function MarkdownLink({ children, href, title }: ComponentProps<'a'>) {
  const external = href?.startsWith('http://') || href?.startsWith('https://')
  return (
    <a
      href={href}
      rel={external ? 'noreferrer' : undefined}
      target={external ? '_blank' : undefined}
      title={title}
    >
      {children}
    </a>
  )
}

function MarkdownTable({ children }: ComponentProps<'table'>) {
  return (
    <div className="table-scroll">
      <table>{children}</table>
    </div>
  )
}

const markdownComponents: Components = {
  a: MarkdownLink,
  pre: MarkdownPre,
  table: MarkdownTable,
}

function displayTime(value: string | null) {
  if (!value) return 'Unknown time'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

export const MessageCard = memo(function MessageCard({
  bookmarked,
  collapsed,
  message,
  onBookmark,
  onToggle,
}: {
  bookmarked: boolean
  collapsed: boolean
  message: Message
  onBookmark: (message: Message) => void
  onToggle: (messageIndex: number) => void
}) {
  return (
    <article className={`message message--${message.role}${collapsed ? ' message--collapsed' : ''}`}>
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
          <Markdown
            components={markdownComponents}
            rehypePlugins={[
              rehypeRaw,
              [rehypeHighlight, { detect: false, plainText: ['mermaid'] }],
            ]}
            remarkPlugins={[remarkGfm]}
            urlTransform={(url) => url}
          >
            {message.markdown}
          </Markdown>
        </div>
      )}
    </article>
  )
})
