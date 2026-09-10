import { useEffect, useId, useState } from 'react'
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

export function MermaidDiagram({ source }: { source: string }) {
  const reactId = useId()
  const diagramId = `mermaid-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`
  const [result, setResult] = useState<RenderResult>({ source, svg: null, error: null })
  const [showRaw, setShowRaw] = useState(false)

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
        <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: current.svg }} />
      ) : (
        <div className="mermaid-loading">Rendering diagram…</div>
      )}
    </div>
  )
}
