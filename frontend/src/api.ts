export type SessionSummary = {
  profile: string
  session_id: string
  title: string
  title_overridden: boolean
  workspace: string | null
  created_at: string | null
  last_activity_at: string | null
  message_count: number
  last_synced_at: string | null
  source_present: boolean
  last_discovered_at: string | null
  indexed: boolean
}

export type Message = {
  message_index: number
  role: 'user' | 'assistant'
  timestamp: string | null
  markdown: string
}

export type MessagePage = {
  start: number
  limit: number
  total: number
  items: Message[]
}

export type SyncResult = {
  profile: string
  session_id: string
  added_messages: number
  message_count: number
  last_complete_offset: number
  up_to_date: boolean
  rebuilt: boolean
}

export type DiscoveryResult = {
  sources: string[]
  found: number
  added: number
  refreshed: number
  unavailable: number
}

export type SearchResult = {
  query: string
  total: number
  message_indexes: number[]
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as { detail?: string }
      detail = body.detail ?? detail
    } catch {
      // Keep the HTTP status when the response has no JSON error body.
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

function sessionPath(session: SessionSummary) {
  return `/api/sessions/${encodeURIComponent(session.profile)}/${encodeURIComponent(session.session_id)}`
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  const response = await request<{ items: SessionSummary[] }>('/api/sessions?limit=500')
  return response.items
}

export function discoverSessions(): Promise<DiscoveryResult> {
  return request<DiscoveryResult>('/api/sessions/discover', { method: 'POST' })
}

export function fetchMessages(
  session: SessionSummary,
  start: number,
  limit: number,
  signal?: AbortSignal,
): Promise<MessagePage> {
  const query = new URLSearchParams({ start: String(start), limit: String(limit) })
  return request<MessagePage>(`${sessionPath(session)}/messages?${query}`, { signal })
}

export function syncSession(session: SessionSummary): Promise<SyncResult> {
  return request<SyncResult>(`${sessionPath(session)}/sync`, { method: 'POST' })
}

export function searchMessages(
  session: SessionSummary,
  query: string,
  signal?: AbortSignal,
): Promise<SearchResult> {
  const parameters = new URLSearchParams({ q: query })
  return request<SearchResult>(`${sessionPath(session)}/search?${parameters}`, { signal })
}
