import { useEffect, useId, useMemo, useState } from 'react'
import { CopyButton } from './CopyButton'

let mermaidModule: Promise<typeof import('mermaid')['default']> | null = null

function loadMermaid() {
  if (!mermaidModule) {
    mermaidModule = import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        securityLevel: 'loose',
        startOnLoad: false,
        suppressErrorRendering: true,
        theme: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'default',
      })
      return mermaid
    })
  }
  return mermaidModule
}

type RenderResult = {
  source: string
  svg: string | null
  error: string | null
}

type LegendEntry = {
  className: string
  fill?: string
  stroke?: string
  color?: string
}

function splitStyleDeclarations(source: string) {
  const declarations: string[] = []
  let current = ''
  let depth = 0
  let quote: '"' | "'" | null = null
  let escaped = false

  for (const character of source) {
    if (escaped) {
      current += character
      escaped = false
      continue
    }
    if (character === '\\') {
      current += character
      escaped = true
      continue
    }
    if (quote) {
      current += character
      if (character === quote) quote = null
      continue
    }
    if (character === '"' || character === "'") {
      current += character
      quote = character
      continue
    }
    if (character === '(') depth += 1
    if (character === ')' && depth > 0) depth -= 1
    if (character === ',' && depth === 0) {
      declarations.push(current)
      current = ''
      continue
    }
    current += character
  }
  if (current) declarations.push(current)
  return declarations
}

function parseLegend(source: string): LegendEntry[] {
  const entries = new Map<string, LegendEntry>()
  const definitions = /(?:^|[;\r\n])\s*classDef\s+([A-Za-z0-9_-]+(?:\s*,\s*[A-Za-z0-9_-]+)*)\s+([^;\r\n]+)/g

  for (const match of source.matchAll(definitions)) {
    const style: Pick<LegendEntry, 'fill' | 'stroke' | 'color'> = {}
    for (const declaration of splitStyleDeclarations(match[2])) {
      const separator = declaration.indexOf(':')
      if (separator < 0) continue
      const property = declaration.slice(0, separator).trim().toLocaleLowerCase()
      if (property !== 'fill' && property !== 'stroke' && property !== 'color') continue
      const value = declaration
        .slice(separator + 1)
        .trim()
        .replace(/\s*!important\s*$/i, '')
      if (value) style[property] = value
    }

    if (!style.fill && !style.stroke && !style.color) continue
    for (const rawClassName of match[1].split(',')) {
      const className = rawClassName.trim()
      if (!className || className === 'default') continue
      entries.set(className, {
        ...entries.get(className),
        ...style,
        className,
      })
    }
  }

  return [...entries.values()]
}

function legendLabel(className: string) {
  return className
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim()
}

export function MermaidDiagram({ source }: { source: string }) {
  const reactId = useId()
  const diagramId = `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`
  const [result, setResult] = useState<RenderResult>({ source, svg: null, error: null })
  const [showRaw, setShowRaw] = useState(false)
  const legend = useMemo(() => parseLegend(source), [source])

  useEffect(() => {
    let active = true
    loadMermaid()
      .then((mermaid) => mermaid.render(diagramId, source))
      .then(({ svg }) => {
        if (active) setResult({ source, svg, error: null })
      })
      .catch((error: unknown) => {
        if (active) {
          setResult({
            source,
            svg: null,
            error: error instanceof Error ? error.message : String(error),
          })
        }
      })
    return () => {
      active = false
    }
  }, [diagramId, source])

  const current = result.source === source ? result : { source, svg: null, error: null }

  return (
    <div className="mermaid-diagram">
      <div className="mermaid-toolbar">
        <span>Mermaid</span>
        <div className="mermaid-toolbar-actions">
          <button
            aria-pressed={showRaw}
            onClick={() => setShowRaw((current) => !current)}
            type="button"
          >
            {showRaw ? 'Diagram' : 'Raw'}
          </button>
          <CopyButton label="Copy Mermaid source" text={source} />
        </div>
      </div>
      {showRaw ? (
        <pre className="mermaid-raw"><code>{source}</code></pre>
      ) : current.error ? (
        <div className="mermaid-error">
          <strong>Diagram could not be rendered.</strong>
          <span>{current.error}</span>
          <pre><code>{source}</code></pre>
        </div>
      ) : current.svg ? (
        <>
          <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: current.svg }} />
          {legend.length > 0 && (
            <div aria-label="Diagram legend" className="mermaid-legend">
              <strong>Legend</strong>
              <ul>
                {legend.map((entry) => (
                  <li key={entry.className}>
                    <span
                      className="mermaid-legend-item"
                      style={{
                        backgroundColor: entry.fill,
                        borderColor: entry.stroke,
                        color: entry.color,
                      }}
                      title={`Mermaid class: ${entry.className}`}
                    >
                      {legendLabel(entry.className)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <div className="mermaid-loading">Rendering diagram…</div>
      )}
    </div>
  )
}
