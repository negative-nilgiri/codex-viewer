export type SessionSummary = {
  profile: string
  session_id: string
  title: string
  workspace: string | null
  created_at: string | null
  last_activity_at: string | null
  message_count: number
  last_synced_at: string | null
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
  const response = await request<{ items: SessionSummary[] }>('/api/sessions')
  return response.items
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
