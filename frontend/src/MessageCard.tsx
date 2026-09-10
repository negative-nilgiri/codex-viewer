import {
  Children,
  isValidElement,
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type MouseEvent,
  type ReactNode,
} from 'react'
import Markdown, { type Components, type ExtraProps } from 'react-markdown'
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

type MessageHeading = {
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

function headingSlug(value: string) {
  return value
    .trim()
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}\p{Mark}\s_-]/gu, '')
    .replace(/\s+/g, '-')
}

function extractHeadings(markdown: string, messageIndex: number): MessageHeading[] {
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
    return {
      ...heading,
      id: `message-${messageIndex}--${slug}`,
      slug,
    }
  })
}

function scrollHeadingIntoView(id: string) {
  const target = document.getElementById(id)
  if (!target) return
  target.scrollIntoView({ block: 'start' })
}

function scrollToHeading(event: MouseEvent<HTMLAnchorElement>, id: string) {
  event.preventDefault()
  scrollHeadingIntoView(id)
}

function scrollToHeadingAfterLayout(id: string) {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => scrollHeadingIntoView(id))
  })
}

function fragmentValue(href: string) {
  try {
    return decodeURIComponent(href.slice(1)).toLocaleLowerCase()
  } catch {
    return href.slice(1).toLocaleLowerCase()
  }
}

function MarkdownTable({ children }: ComponentProps<'table'>) {
  return (
    <div className="table-scroll">
      <table>{children}</table>
    </div>
  )
}

function ScopedHeading({
  children,
  headings,
  messageIndex,
  node,
  tag: Heading,
  ...props
}: ComponentProps<'h1'> &
  ExtraProps & {
    headings: MessageHeading[]
    messageIndex: number
    tag: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'
  }) {
  const line = node?.position?.start.line
  const known = headings.find((heading) => heading.line === line)
  const fallback = headingSlug(textContent(children)) || `line-${line ?? 'unknown'}`
  const id = known?.id ?? `message-${messageIndex}--${fallback}`

  return (
    <Heading {...props} className="markdown-heading" id={id}>
      <a
        aria-label={`Link to ${known?.text ?? textContent(children)}`}
        className="heading-anchor"
        href={`#${id}`}
        onClick={(event) => scrollToHeading(event, id)}
        title="Link to this heading"
      >
        #
      </a>
      {children}
    </Heading>
  )
}

function createMarkdownComponents(
  headings: MessageHeading[],
  messageIndex: number,
): Components {
  function MarkdownLink({ children, href, title }: ComponentProps<'a'>) {
    const external = href?.startsWith('http://') || href?.startsWith('https://')
    const fragment = href?.startsWith('#') ? fragmentValue(href) : null
    const target = fragment
      ? headings.find(
          (heading) => heading.slug === fragment || heading.slug === headingSlug(fragment),
        )
      : undefined
    const resolvedHref = target ? `#${target.id}` : href

    return (
      <a
        href={resolvedHref}
        onClick={target ? (event) => scrollToHeading(event, target.id) : undefined}
        rel={external ? 'noreferrer' : undefined}
        target={external ? '_blank' : undefined}
        title={title}
      >
        {children}
      </a>
    )
  }

  const scopedHeading = (tag: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6') =>
    function MessageScopedHeading(props: ComponentProps<'h1'> & ExtraProps) {
      return (
        <ScopedHeading
          {...props}
          headings={headings}
          messageIndex={messageIndex}
          tag={tag}
        />
      )
    }

  return {
    a: MarkdownLink,
    h1: scopedHeading('h1'),
    h2: scopedHeading('h2'),
    h3: scopedHeading('h3'),
    h4: scopedHeading('h4'),
    h5: scopedHeading('h5'),
    h6: scopedHeading('h6'),
    pre: MarkdownPre,
    table: MarkdownTable,
  }
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
  const [outlineOpen, setOutlineOpen] = useState(false)
  const [showBackToTop, setShowBackToTop] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const messageRef = useRef<HTMLElement>(null)
  const headings = useMemo(
    () => extractHeadings(message.markdown, message.message_index),
    [message.markdown, message.message_index],
  )
  const markdownComponents = useMemo(
    () => createMarkdownComponents(headings, message.message_index),
    [headings, message.message_index],
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
              <nav aria-label={`Message ${message.message_index} outline`} className="message-outline">
                <strong>In this message</strong>
                <ol>
                  {headings.map((heading) => (
                    <li
                      key={`${heading.line}-${heading.id}`}
                      style={{
                        paddingInlineStart: `${Math.max(heading.depth - 1, 0) * 0.8}rem`,
                      }}
                    >
                      <a
                        href={`#${heading.id}`}
                        onClick={(event) => {
                          event.preventDefault()
                          setOutlineOpen(false)
                          scrollToHeadingAfterLayout(heading.id)
                        }}
                      >
                        {heading.text}
                      </a>
                    </li>
                  ))}
                </ol>
              </nav>
            )}
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
