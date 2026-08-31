import { useCallback, useEffect, useRef, useState } from 'react'
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso'
import {
  discoverSessions,
  fetchMessages,
  fetchSessions,
  syncSession,
  type Message,
  type SessionSummary,
} from './api'
import { CopyButton } from './components/CopyButton'
import { MessageCard } from './MessageCard'
import './App.css'

const BLOCK_SIZE = 30
const MAX_CACHED_BLOCKS = 7

type BlockStatus = 'loading' | 'error'

type FoldState = {
  defaultCollapsed: boolean
  exceptions: Set<number>
}

function displayClockTime(value: string | null) {
  if (!value) return 'Unknown'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf())
    ? value
    : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function activityDay(value: string | null) {
  if (!value) return { key: 'unknown', label: 'Unknown activity date' }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.valueOf())) return { key: value, label: value }
  const day = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate())
  const today = new Date()
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const difference = Math.round((todayStart.valueOf() - day.valueOf()) / 86_400_000)
  const key = `${day.getFullYear()}-${day.getMonth() + 1}-${day.getDate()}`
  if (difference === 0) return { key, label: 'Today' }
  if (difference === 1) return { key, label: 'Yesterday' }
  return {
    key,
    label: parsed.toLocaleDateString([], {
      weekday: 'long',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }),
  }
}

function groupSessions(sessions: SessionSummary[]) {
  const groups: Array<{ key: string; label: string; sessions: SessionSummary[] }> = []
  for (const session of sessions) {
    const day = activityDay(session.last_activity_at ?? session.created_at)
    const current = groups.at(-1)
    if (current?.key === day.key) current.sessions.push(session)
    else groups.push({ ...day, sessions: [session] })
  }
  return groups
}

function sessionIdentity(session: SessionSummary) {
  return `${session.profile}:${session.session_id}`
}

function blockStartFor(index: number) {
  return Math.floor(index / BLOCK_SIZE) * BLOCK_SIZE
}

function foldStorageKey(session: SessionSummary) {
  return `codex-sessions-viewer:folds:${sessionIdentity(session)}`
}

function loadFoldState(session: SessionSummary): FoldState {
  try {
    const stored = localStorage.getItem(foldStorageKey(session))
    if (!stored) return { defaultCollapsed: false, exceptions: new Set() }
    const parsed = JSON.parse(stored) as {
      defaultCollapsed?: unknown
      exceptions?: unknown
    }
    const exceptions = Array.isArray(parsed.exceptions)
      ? parsed.exceptions.filter(
          (value): value is number => Number.isInteger(value) && value > 0,
        )
      : []
    return {
      defaultCollapsed: parsed.defaultCollapsed === true,
      exceptions: new Set(exceptions),
    }
  } catch (error) {
    console.warn('Could not restore folded messages', error)
    return { defaultCollapsed: false, exceptions: new Set() }
  }
}

function Transcript({
  session,
  onSynced,
}: {
  session: SessionSummary
  onSynced: () => Promise<void>
}) {
  const virtuoso = useRef<VirtuosoHandle>(null)
  const blocksRef = useRef(new Map<number, Message[]>())
  const accessOrder = useRef<number[]>([])
  const requests = useRef(new Map<number, AbortController>())
  const mounted = useRef(false)
  const [blocks, setBlocks] = useState(new Map<number, Message[]>())
  const [statuses, setStatuses] = useState(new Map<number, BlockStatus>())
  const [total, setTotal] = useState(session.message_count)
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: -1 })
  const [syncing, setSyncing] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [newMessages, setNewMessages] = useState(0)
  const [foldState, setFoldState] = useState<FoldState>(() => loadFoldState(session))

  useEffect(() => {
    mounted.current = true
    const activeRequests = requests.current
    return () => {
      mounted.current = false
      activeRequests.forEach((controller) => controller.abort())
      activeRequests.clear()
    }
  }, [])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), 5000)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    try {
      localStorage.setItem(
        foldStorageKey(session),
        JSON.stringify({
          defaultCollapsed: foldState.defaultCollapsed,
          exceptions: [...foldState.exceptions],
        }),
      )
    } catch (error) {
      console.warn('Could not persist folded messages', error)
    }
  }, [foldState, session])

  const toggleMessage = useCallback((messageIndex: number) => {
    setFoldState((current) => {
      const exceptions = new Set(current.exceptions)
      if (exceptions.has(messageIndex)) exceptions.delete(messageIndex)
      else exceptions.add(messageIndex)
      return { ...current, exceptions }
    })
  }, [])

  const touchBlock = useCallback((start: number) => {
    accessOrder.current = [
      ...accessOrder.current.filter((candidate) => candidate !== start),
      start,
    ]
  }, [])

  const loadBlock = useCallback(
    (start: number, retry = false) => {
      if (start < 0 || start >= total) return
      if (!retry && blocksRef.current.has(start)) {
        touchBlock(start)
        return
      }
      if (requests.current.has(start)) return

      const controller = new AbortController()
      requests.current.set(start, controller)
      setStatuses((current) => {
        const next = new Map(current)
        next.set(start, 'loading')
        return next
      })

      fetchMessages(session, start, BLOCK_SIZE, controller.signal)
        .then((page) => {
          if (!mounted.current) return
          touchBlock(start)
          const next = new Map(blocksRef.current)
          next.set(start, page.items)
          while (accessOrder.current.length > MAX_CACHED_BLOCKS) {
            const evicted = accessOrder.current.shift()
            if (evicted !== undefined) next.delete(evicted)
          }
          blocksRef.current = next
          setBlocks(next)
          setStatuses((current) => {
            const updated = new Map(current)
            updated.delete(start)
            return updated
          })
        })
        .catch((caught: unknown) => {
          if (!mounted.current || controller.signal.aborted) return
          console.error(`Could not load message block ${start}`, caught)
          setStatuses((current) => {
            const next = new Map(current)
            next.set(start, 'error')
            return next
          })
        })
        .finally(() => {
          if (requests.current.get(start) === controller) {
            requests.current.delete(start)
          }
        })
    },
    [session, total, touchBlock],
  )

  const loadVisibleRange = useCallback(
    ({ startIndex, endIndex }: { startIndex: number; endIndex: number }) => {
      setVisibleRange({ start: startIndex, end: endIndex })
      const first = blockStartFor(startIndex)
      const last = blockStartFor(endIndex)
      for (let start = first - BLOCK_SIZE; start <= last + BLOCK_SIZE; start += BLOCK_SIZE) {
        if (start >= 0 && start < total) loadBlock(start)
      }
    },
    [loadBlock, total],
  )

  function messageAt(index: number) {
    const start = blockStartFor(index)
    return blocks.get(start)?.[index - start]
  }

  function invalidateFrom(start: number) {
    requests.current.forEach((controller, blockStart) => {
      if (blockStart >= start) {
        controller.abort()
        requests.current.delete(blockStart)
      }
    })
    accessOrder.current = accessOrder.current.filter((blockStart) => blockStart < start)
    const next = new Map(blocksRef.current)
    for (const blockStart of next.keys()) {
      if (blockStart >= start) next.delete(blockStart)
    }
    blocksRef.current = next
    setBlocks(next)
  }

  async function synchronize() {
    setSyncing(true)
    setNotice(null)
    setError(null)
    try {
      const previousTotal = total
      const result = await syncSession(session)
      if (result.added_messages) {
        invalidateFrom(blockStartFor(previousTotal))
        setNewMessages(result.added_messages)
      }
      setTotal(result.message_count)
      await onSynced()
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

  function jumpTo(index: number) {
    if (!total) return
    loadBlock(blockStartFor(index))
    virtuoso.current?.scrollToIndex({ index, align: index === 0 ? 'start' : 'end' })
  }

  function jumpToLatest() {
    setNewMessages(0)
    jumpTo(total - 1)
  }

  const visibleLabel =
    visibleRange.end >= 0 && total
      ? `${visibleRange.start + 1}–${Math.min(visibleRange.end + 1, total)} of ${total}`
      : 'No visible messages'

  return (
    <>
      <header className="session-header">
        <div className="session-heading">
          <span className="eyebrow">{session.profile}</span>
          <h2>{session.title}</h2>
          <p>
            <span className="session-id">
              <code>{session.session_id}</code>
              <CopyButton
                className="copy-button--session"
                label="Copy session ID"
                text={session.session_id}
              />
            </span>
            {session.workspace && <span> · {session.workspace}</span>}
          </p>
        </div>
        <div className="session-actions">
          <span className="range-indicator">{visibleLabel}</span>
          <button onClick={() => jumpTo(0)} type="button">Beginning</button>
          <button onClick={jumpToLatest} type="button">Latest</button>
          <button
            onClick={() => setFoldState({ defaultCollapsed: true, exceptions: new Set() })}
            type="button"
          >
            Collapse all
          </button>
          <button
            onClick={() => setFoldState({ defaultCollapsed: false, exceptions: new Set() })}
            type="button"
          >
            Expand all
          </button>
          <button
            disabled={syncing || !session.source_present}
            onClick={synchronize}
            type="button"
          >
            {syncing ? 'Syncing…' : session.indexed ? 'Sync now' : 'Index session'}
          </button>
        </div>
      </header>

      {error && <div className="status status--error">{error}</div>}
      {notice && <div className="status">{notice}</div>}
      {newMessages > 0 && (
        <button className="new-messages" onClick={jumpToLatest} type="button">
          {newMessages} new message{newMessages === 1 ? '' : 's'} · jump to latest
        </button>
      )}

      <div className="virtual-transcript">
        {total ? (
          <Virtuoso
            ref={virtuoso}
            totalCount={total}
            rangeChanged={loadVisibleRange}
            increaseViewportBy={{ top: 500, bottom: 800 }}
            defaultItemHeight={180}
            computeItemKey={(index) => `${sessionIdentity(session)}:message:${index + 1}`}
            itemContent={(index) => {
              const message = messageAt(index)
              const start = blockStartFor(index)
              const status = statuses.get(start)
              if (!message) {
                return (
                  <div className="message-slot">
                    <div className={`message-placeholder${status === 'error' ? ' message-placeholder--error' : ''}`}>
                      {status === 'error' ? (
                        <>
                          <span>Messages {start + 1}–{Math.min(start + BLOCK_SIZE, total)} failed to load.</span>
                          <button onClick={() => loadBlock(start, true)} type="button">Retry</button>
                        </>
                      ) : (
                        <span>Loading message {index + 1}…</span>
                      )}
                    </div>
                  </div>
                )
              }
              const collapsed =
                foldState.defaultCollapsed !== foldState.exceptions.has(message.message_index)
              return (
                <div className="message-slot">
                  <MessageCard
                    collapsed={collapsed}
                    message={message}
                    onToggle={toggleMessage}
                  />
                </div>
              )
            }}
          />
        ) : !session.source_present ? (
          <div className="empty-transcript">
            <h2>Source unavailable</h2>
            <p>The indexed catalog entry remains, but its rollout is not currently mounted.</p>
          </div>
        ) : !session.indexed ? (
          <div className="empty-transcript">
            <h2>Session not indexed</h2>
            <p>Use <strong>Index session</strong> to import its visible messages on demand.</p>
          </div>
        ) : (
          <div className="empty-transcript">
            <h2>No visible messages</h2>
            <p>This rollout has not produced a user or assistant message yet.</p>
          </div>
        )}
      </div>
    </>
  )
}

function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selected, setSelected] = useState<SessionSummary | null>(null)
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [discovering, setDiscovering] = useState(false)
  const [catalogNotice, setCatalogNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('codex-sessions-viewer:sidebar-collapsed') === 'true',
  )

  async function refreshSessions() {
    const loaded = await fetchSessions()
    setSessions(loaded)
    setSelected((current) => {
      if (!current) return loaded[0] ?? null
      return (
        loaded.find((item) => sessionIdentity(item) === sessionIdentity(current)) ??
        loaded[0] ??
        null
      )
    })
  }

  useEffect(() => {
    let active = true
    discoverSessions()
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : String(caught))
      })
      .then(() => fetchSessions())
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
    if (!catalogNotice) return
    const timer = window.setTimeout(() => setCatalogNotice(null), 5000)
    return () => window.clearTimeout(timer)
  }, [catalogNotice])

  useEffect(() => {
    localStorage.setItem(
      'codex-sessions-viewer:sidebar-collapsed',
      String(sidebarCollapsed),
    )
  }, [sidebarCollapsed])

  async function rescanSessions() {
    setDiscovering(true)
    setCatalogNotice(null)
    setError(null)
    try {
      const result = await discoverSessions()
      await refreshSessions()
      setCatalogNotice(
        `Found ${result.found} session${result.found === 1 ? '' : 's'} · ` +
        `${result.added} new · ${result.unavailable} unavailable.`,
      )
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : String(caught))
    } finally {
      setDiscovering(false)
    }
  }

  const sessionGroups = groupSessions(sessions)

  return (
    <main className={`app-shell${sidebarCollapsed ? ' app-shell--sidebar-collapsed' : ''}`}>
      <aside className={`session-sidebar${sidebarCollapsed ? ' session-sidebar--collapsed' : ''}`}>
        <div className="sidebar-heading">
          {!sidebarCollapsed && (
            <div>
              <span className="eyebrow">Recently active</span>
              <h1>Sessions</h1>
            </div>
          )}
          <div className="sidebar-heading-actions">
            {!sidebarCollapsed && (
              <button
                aria-label="Rescan sessions"
                disabled={discovering}
                onClick={rescanSessions}
                title="Rescan sessions"
                type="button"
              >
                {discovering ? '…' : '↻'}
              </button>
            )}
            <button
              aria-expanded={!sidebarCollapsed}
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              onClick={() => setSidebarCollapsed((current) => !current)}
              title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              type="button"
            >
              {sidebarCollapsed ? '›' : '‹'}
            </button>
          </div>
        </div>
        {!sidebarCollapsed && (
          <>
            {error && <div className="status status--error">{error}</div>}
            {catalogNotice && <div className="status">{catalogNotice}</div>}
            {sessions.length === 0 && loadingSessions ? (
              <div className="empty-sidebar">Scanning mounted sessions…</div>
            ) : sessions.length === 0 ? (
              <div className="empty-sidebar">
                <p>No session rollouts were discovered.</p>
                <code>viewer discover</code>
              </div>
            ) : (
              <nav aria-label="Recently active sessions">
                {sessionGroups.map((group) => (
                  <section className="session-day" key={group.key}>
                    <h2>{group.label}</h2>
                    {group.sessions.map((session) => {
                      const active = selected && sessionIdentity(selected) === sessionIdentity(session)
                      return (
                        <button
                          className={`session-link${active ? ' session-link--active' : ''}`}
                          key={sessionIdentity(session)}
                          onClick={() => setSelected(session)}
                          type="button"
                        >
                          <strong>{session.title}</strong>
                          <div className="session-meta">
                            <span className={!session.source_present ? 'session-state--unavailable' : ''}>
                              {session.profile} ·{' '}
                              {!session.source_present
                                ? 'Unavailable'
                                : session.indexed
                                  ? `${session.message_count} messages`
                                  : 'Not indexed'}
                            </span>
                            <time>{displayClockTime(session.last_activity_at)}</time>
                          </div>
                        </button>
                      )
                    })}
                  </section>
                ))}
              </nav>
            )}
          </>
        )}
      </aside>

      <section className="transcript">
        {selected ? (
          <Transcript
            key={sessionIdentity(selected)}
            session={selected}
            onSynced={refreshSessions}
          />
        ) : (
          <div className="empty-transcript">
            <h2>Import a session to begin</h2>
            <p>The viewer only reads sessions you explicitly synchronize.</p>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
