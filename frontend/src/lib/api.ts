const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000'

export interface LoadCollegeResponse {
  session_id: string
  status: 'success' | 'cached' | 'error'
  chunks: number
  sources?: string[]
  message: string
  college?: string
}

export interface ChatResponse {
  reply: string
  rescrape_triggered: boolean
  rescrape_reason?: string
  sources: string[]
  session_id: string
}

export interface CollegeInfo {
  college: string
  scraped_at: string
  chunks: number
  meta: Record<string, any>
}

export async function loadCollege(
  collegeName: string,
  sessionId?: string,
  forceRefresh = false
): Promise<LoadCollegeResponse> {
  const res = await fetch(`${API_BASE}/api/college/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      college_name: collegeName,
      session_id: sessionId,
      force_refresh: forceRefresh,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || `Failed to load college (${res.status})`)
  }
  return res.json()
}

export async function sendMessage(
  sessionId: string,
  message: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || `Chat request failed (${res.status})`)
  }
  return res.json()
}

export async function listColleges(): Promise<CollegeInfo[]> {
  const res = await fetch(`${API_BASE}/api/colleges`)
  if (!res.ok) throw new Error('Failed to fetch colleges')
  const data = await res.json()
  return data.colleges || []
}

export async function resetSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/college/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  })
}
