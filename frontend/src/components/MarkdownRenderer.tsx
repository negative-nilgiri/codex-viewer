import {
  Children,
  isValidElement,
  memo,
  type ComponentProps,
  type MouseEvent,
  type ReactNode,
} from 'react'
import Markdown, { type Components, type ExtraProps } from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { CopyButton } from './CopyButton'
import { MermaidDiagram } from './MermaidDiagram'
import { AnnotationSurface } from './AnnotationSurface'
import type { Annotation, AnnotationDraft } from '../api'
import {
  headingSlug,
  scrollHeadingIntoView,
  type MarkdownHeading,
} from '../markdown'
import 'highlight.js/styles/github-dark-dimmed.css'
import 'katex/dist/katex.min.css'

function textContent(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textContent).join('')
  if (isValidElement<{ children?: ReactNode }>(node)) return textContent(node.props.children)
  return ''
}

function sourcePosition(node: ExtraProps['node']) {
  const start = node?.position?.start.line
  const end = node?.position?.end.line
  return start && end
    ? {
        'data-source-start-line': String(start),
        'data-source-end-line': String(end),
      }
    : {}
}

function MarkdownPre({ children, node }: { children?: ReactNode } & ExtraProps) {
  const code = Children.toArray(children)[0]
  const className = isValidElement<{ className?: string }>(code)
    ? code.props.className ?? ''
    : ''
  const source = textContent(code).replace(/\n$/, '')

  if (className.split(' ').includes('language-mermaid')) {
    return (
      <div {...sourcePosition(node)}>
        <MermaidDiagram source={source} />
      </div>
    )
  }

  return (
    <div className="code-block" {...sourcePosition(node)}>
      <CopyButton className="copy-button--code" label="Copy code" text={source} />
      <pre>{children}</pre>
    </div>
  )
}

function scrollToHeading(event: MouseEvent<HTMLAnchorElement>, id: string) {
  event.preventDefault()
  scrollHeadingIntoView(id)
}

function fragmentValue(href: string) {
  try {
    return decodeURIComponent(href.slice(1)).toLocaleLowerCase()
  } catch {
    return href.slice(1).toLocaleLowerCase()
  }
}

function MarkdownTable({ children, node }: ComponentProps<'table'> & ExtraProps) {
  return (
    <div className="table-scroll" {...sourcePosition(node)}>
      <table>{children}</table>
    </div>
  )
}

function PositionedParagraph({ node, ...props }: ComponentProps<'p'> & ExtraProps) {
  return <p {...props} {...sourcePosition(node)} />
}

function PositionedListItem({ node, ...props }: ComponentProps<'li'> & ExtraProps) {
  return <li {...props} {...sourcePosition(node)} />
}

function PositionedUnorderedList({ node, ...props }: ComponentProps<'ul'> & ExtraProps) {
  return <ul {...props} {...sourcePosition(node)} />
}

function PositionedOrderedList({ node, ...props }: ComponentProps<'ol'> & ExtraProps) {
  return <ol {...props} {...sourcePosition(node)} />
}

function PositionedBlockquote({ node, ...props }: ComponentProps<'blockquote'> & ExtraProps) {
  return <blockquote {...props} {...sourcePosition(node)} />
}

function PositionedTableCell({ node, ...props }: ComponentProps<'td'> & ExtraProps) {
  return <td {...props} {...sourcePosition(node)} />
}

function PositionedTableHeading({ node, ...props }: ComponentProps<'th'> & ExtraProps) {
  return <th {...props} {...sourcePosition(node)} />
}

function PositionedRule({ node, ...props }: ComponentProps<'hr'> & ExtraProps) {
  return <hr {...props} {...sourcePosition(node)} />
}

function ScopedHeading({
  children,
  headings,
  node,
  scope,
  tag: Heading,
  ...props
}: ComponentProps<'h1'> &
  ExtraProps & {
    headings: MarkdownHeading[]
    scope: string
    tag: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'
  }) {
  const line = node?.position?.start.line
  const known = headings.find((heading) => heading.line === line)
  const fallback = headingSlug(textContent(children)) || `line-${line ?? 'unknown'}`
  const id = known?.id ?? `${scope}--${fallback}`

  return (
    <Heading
      {...props}
      {...sourcePosition(node)}
      className="markdown-heading"
      id={id}
    >
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

function createMarkdownComponents(headings: MarkdownHeading[], scope: string): Components {
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
    function ScopedMarkdownHeading(props: ComponentProps<'h1'> & ExtraProps) {
      return <ScopedHeading {...props} headings={headings} scope={scope} tag={tag} />
    }

  return {
    a: MarkdownLink,
    h1: scopedHeading('h1'),
    h2: scopedHeading('h2'),
    h3: scopedHeading('h3'),
    h4: scopedHeading('h4'),
    h5: scopedHeading('h5'),
    h6: scopedHeading('h6'),
    blockquote: PositionedBlockquote,
    hr: PositionedRule,
    li: PositionedListItem,
    ol: PositionedOrderedList,
    p: PositionedParagraph,
    pre: MarkdownPre,
    table: MarkdownTable,
    td: PositionedTableCell,
    th: PositionedTableHeading,
    ul: PositionedUnorderedList,
  }
}

export const MarkdownRenderer = memo(function MarkdownRenderer({
  annotations,
  focusAnnotationId,
  headings,
  markdown,
  onCreateAnnotation,
  onAnnotationFocused,
  scope,
}: {
  annotations: Annotation[]
  focusAnnotationId?: number | null
  headings: MarkdownHeading[]
  markdown: string
  onCreateAnnotation: (draft: AnnotationDraft) => Promise<void>
  onAnnotationFocused?: (annotationId: number) => void
  scope: string
}) {
  const components = createMarkdownComponents(headings, scope)
  return (
    <AnnotationSurface
      annotations={annotations}
      contentKey={markdown}
      focusAnnotationId={focusAnnotationId}
      onCreate={onCreateAnnotation}
      onFocused={onAnnotationFocused}
      owner={scope}
    >
      <Markdown
        components={components}
        rehypePlugins={[
          rehypeRaw,
          [rehypeKatex, { throwOnError: false, strict: 'warn' }],
          [rehypeHighlight, { detect: false, plainText: ['mermaid'] }],
        ]}
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: true }]]}
        urlTransform={(url) => url}
      >
        {markdown}
      </Markdown>
    </AnnotationSurface>
  )
})

export function MarkdownOutline({
  headings,
  label,
  onNavigate,
  title,
}: {
  headings: MarkdownHeading[]
  label: string
  onNavigate: (heading: MarkdownHeading) => void
  title: string
}) {
  return (
    <nav aria-label={label} className="message-outline">
      <strong>{title}</strong>
      <ol>
        {headings.map((heading) => (
          <li
            key={`${heading.line}-${heading.id}`}
            style={{ paddingInlineStart: `${Math.max(heading.depth - 1, 0) * 0.8}rem` }}
          >
            <a
              href={`#${heading.id}`}
              onClick={(event) => {
                event.preventDefault()
                onNavigate(heading)
              }}
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  )
}
