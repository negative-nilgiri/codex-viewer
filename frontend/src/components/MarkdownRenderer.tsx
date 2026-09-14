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
import rehypeRaw from 'rehype-raw'
import remarkGfm from 'remark-gfm'
import { CopyButton } from './CopyButton'
import { MermaidDiagram } from './MermaidDiagram'
import {
  headingSlug,
  scrollHeadingIntoView,
  type MarkdownHeading,
} from '../markdown'
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
    pre: MarkdownPre,
    table: MarkdownTable,
  }
}

export const MarkdownRenderer = memo(function MarkdownRenderer({
  headings,
  markdown,
  scope,
}: {
  headings: MarkdownHeading[]
  markdown: string
  scope: string
}) {
  const components = createMarkdownComponents(headings, scope)
  return (
    <Markdown
      components={components}
      rehypePlugins={[
        rehypeRaw,
        [rehypeHighlight, { detect: false, plainText: ['mermaid'] }],
      ]}
      remarkPlugins={[remarkGfm]}
      urlTransform={(url) => url}
    >
      {markdown}
    </Markdown>
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
