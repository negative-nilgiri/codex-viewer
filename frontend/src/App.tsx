import { useEffect, useState } from 'react'
import {
  fetchMessages,
  fetchSessions,
  syncSession,
  type MessagePage,
  type SessionSummary,
} from './api'
import './App.css'

const PAGE_SIZE = 30

function displayTime(value: string | null) {
  if (!value) return 'Unknown time'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selected, setSelected] = useState<SessionSummary | null>(null)
  const [page, setPage] = useState<MessagePage | null>(null)
  const [start, setStart] = useState(0)
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function refreshSessions() {
    const loaded = await fetchSessions()
    setSessions(loaded)
    setSelected((current) => {
      if (!current) return loaded[0] ?? null
      return (
        loaded.find(
          (item) =>
            item.profile === current.profile && item.session_id === current.session_id,
        ) ?? loaded[0] ?? null
      )
    })
  }

  useEffect(() => {
    let active = true
    fetchSessions()
      .then((loaded) => {
        if (!active) return
        setSessions(loaded)
        setSelected(loaded[0] ?? null)
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : String(caught))
      })
      .finally(() => {
        if (active) setLoadingSessions(false)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selected) {
      return
    }
    let active = true
    fetchMessages(selected, start, PAGE_SIZE)
      .then((loaded) => {
        if (active) setPage(loaded)
      })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : String(caught))
      })
      .finally(() => {
        if (active) setLoadingMessages(false)
      })
    return () => {
      active = false
    }
  }, [selected, start])

  function chooseSession(session: SessionSummary) {
    setSelected(session)
    setStart(0)
    setPage(null)
    setLoadingMessages(true)
    setError(null)
    setNotice(null)
  }

  function changePage(nextStart: number) {
    setLoadingMessages(true)
    setStart(nextStart)
  }

  async function synchronize() {
    if (!selected) return
    setSyncing(true)
    setError(null)
    setNotice(null)
    try {
      const result = await syncSession(selected)
      await refreshSessions()
      const nextStart = Math.min(start, Math.max(0, result.message_count - 1))
      setStart(nextStart)
      const refreshed = await fetchMessages(selected, nextStart, PAGE_SIZE)
      setPage(refreshed)
      setNotice(
        result.added_messages
          ? `Imported ${result.added_messages} new message${result.added_messages === 1 ? '' : 's'}.`
          : 'Session is already up to date.',
      )
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setSyncing(false)
    }
  }

  const shownFrom = page && page.items.length ? page.items[0].message_index : 0
  const shownTo = page && page.items.length ? page.items.at(-1)!.message_index : 0

  return (
    <main className="app-shell">
      <aside className="session-sidebar">
        <div className="sidebar-heading">
          <span className="eyebrow">Local archive</span>
          <h1>Codex sessions</h1>
        </div>
        {sessions.length === 0 && !loadingSessions ? (
          <div className="empty-sidebar">
            <p>No sessions have been imported yet.</p>
            <code>viewer sync codex_2 SESSION_ID</code>
          </div>
        ) : (
          <nav aria-label="Imported sessions">
            {sessions.map((session) => {
              const active =
                selected?.profile === session.profile &&
                selected.session_id === session.session_id
              return (
                <button
                  className={`session-link${active ? ' session-link--active' : ''}`}
                  key={`${session.profile}:${session.session_id}`}
                  onClick={() => chooseSession(session)}
                  type="button"
                >
                  <strong>{session.title}</strong>
                  <span>{session.profile} · {session.message_count} messages</span>
                  <time>{displayTime(session.last_activity_at)}</time>
                </button>
              )
            })}
          </nav>
        )}
      </aside>

      <section className="transcript">
        {selected ? (
          <>
            <header className="session-header">
              <div>
                <span className="eyebrow">{selected.profile}</span>
                <h2>{selected.title}</h2>
                <p>
                  <code>{selected.session_id}</code>
                  {selected.workspace ? ` · ${selected.workspace}` : ''}
                </p>
              </div>
              <button disabled={syncing} onClick={synchronize} type="button">
                {syncing ? 'Syncing…' : 'Sync now'}
              </button>
            </header>

            {error && <div className="status status--error">{error}</div>}
            {notice && <div className="status">{notice}</div>}

            <div className="message-list" aria-busy={loadingMessages}>
              {page?.items.map((message) => (
                <article className={`message message--${message.role}`} key={message.message_index}>
                  <header>
                    <strong>[{message.message_index}] {message.role === 'assistant' ? 'AGENT' : 'USER'}</strong>
                    <time>{displayTime(message.timestamp)}</time>
                  </header>
                  <pre>{message.markdown}</pre>
                </article>
              ))}
              {loadingMessages && <div className="loading">Loading messages…</div>}
            </div>

            {page && (
              <footer className="pagination">
                <button
                  disabled={start === 0 || loadingMessages}
                  onClick={() => changePage(Math.max(0, start - PAGE_SIZE))}
                  type="button"
                >
                  Previous
                </button>
                <span>
                  {page.total ? `${shownFrom}–${shownTo} of ${page.total}` : 'No visible messages'}
                </span>
                <button
                  disabled={start + page.items.length >= page.total || loadingMessages}
                  onClick={() => changePage(start + page.items.length)}
                  type="button"
                >
                  Next
                </button>
              </footer>
            )}
          </>
        ) : (
          <div className="empty-transcript">
            <h2>Import a session to begin</h2>
            <p>The viewer only reads sessions you explicitly synchronize in this first milestone.</p>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
