export interface ProgramSummary {
  id: number
  name: string
  path: string
  loc: number
  move_count: number
  linkage_count: number
  indexed_at: string
}

export interface TableRef {
  table_name: string
  op_type: string
}

export interface FileRef {
  file_name: string
  op_type: string
}

export interface ProgramDetail extends ProgramSummary {
  modules: string[]
  tables_ref: TableRef[]
  files_ref: FileRef[]
}

export interface IngestResponse {
  status: string
  files_found: number
}

export type ProgressEvent =
  | { event: 'start'; total: number }
  | { event: 'progress'; file: string; current: number; total: number }
  | { event: 'file_error'; file: string; detail: string }
  | { event: 'done'; indexed: number; total: number }

export type SSEEvent =
  | { type: 'token'; text: string }
  | { type: 'done' }
  | { type: 'error'; detail: string }

// ── REST ──────────────────────────────────────────────────────────────────────

export async function postIngest(path: string): Promise<IngestResponse> {
  const resp = await fetch('/api/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail ?? resp.statusText)
  }
  return resp.json()
}

export async function getWorkspaces(): Promise<ProgramSummary[]> {
  const resp = await fetch('/api/workspaces')
  if (!resp.ok) throw new Error(resp.statusText)
  const data = await resp.json()
  return data.programs
}

export async function getProgram(id: number): Promise<ProgramDetail> {
  const resp = await fetch(`/api/programs/${id}`)
  if (!resp.ok) throw new Error(resp.statusText)
  return resp.json()
}

// ── SSE streaming query ───────────────────────────────────────────────────────

export function streamQuery(
  query: string,
  onToken: (text: string) => void,
  onDone: () => void,
  onError: (detail: string) => void,
): () => void {
  const url = `/api/query/stream?q=${encodeURIComponent(query)}`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    try {
      const payload: SSEEvent = JSON.parse(e.data)
      if (payload.type === 'token') onToken(payload.text)
      else if (payload.type === 'done') { onDone(); es.close() }
      else if (payload.type === 'error') { onError(payload.detail); es.close() }
    } catch {
      // ignore malformed lines
    }
  }

  es.onerror = () => {
    onError('Connection to server lost.')
    es.close()
  }

  return () => es.close()
}

// ── WebSocket ingest progress ─────────────────────────────────────────────────

export function connectIngestProgress(
  onEvent: (evt: ProgressEvent) => void,
): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/ingest-progress`)
  ws.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data) as ProgressEvent) } catch { /* ignore */ }
  }
  return ws
}
