import { useEffect, useRef, useState } from 'react'

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.append(textarea)
  textarea.select()
  const copied = document.execCommand('copy')
  textarea.remove()
  if (!copied) throw new Error('The browser refused to copy this text.')
}

export function CopyButton({
  className = '',
  disabled = false,
  label,
  text,
}: {
  className?: string
  disabled?: boolean
  label: string
  text: string
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'error'>('idle')
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (resetTimer.current) clearTimeout(resetTimer.current)
    }
  }, [])

  async function copy() {
    if (resetTimer.current) clearTimeout(resetTimer.current)
    try {
      await copyText(text)
      setState('copied')
    } catch (error) {
      console.error('Could not copy text', error)
      setState('error')
    }
    resetTimer.current = setTimeout(() => setState('idle'), 1600)
  }

  const visibleLabel = state === 'copied' ? 'Copied' : state === 'error' ? 'Copy failed' : 'Copy'

  return (
    <button
      aria-label={label}
      className={`copy-button ${className}`.trim()}
      disabled={disabled}
      onClick={copy}
      title={label}
      type="button"
    >
      {visibleLabel}
    </button>
  )
}
