import { useEffect, useRef, useState } from 'react'
import { connectIngestProgress, postIngest } from '../api'
import type { ProgressEvent } from '../api'

interface LogEntry {
  kind: 'info' | 'ok' | 'error'
  text: string
}

export default function IngestPanel() {
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<LogEntry[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log])

  function addLog(kind: LogEntry['kind'], text: string) {
    setLog((prev) => [...prev, { kind, text }])
  }

  async function handleIngest() {
    const dir = path.trim()
    if (!dir || busy) return
    setBusy(true)
    setLog([])

    // open WS before POST so no events are missed
    wsRef.current?.close()
    const ws = connectIngestProgress((evt: ProgressEvent) => {
      if (evt.event === 'start') {
        addLog('info', `Found ${evt.total} file(s) — indexing…`)
      } else if (evt.event === 'progress') {
        addLog('ok', `[${evt.current}/${evt.total}] ${evt.file}`)
      } else if (evt.event === 'file_error') {
        addLog('error', `${evt.file}: ${evt.detail}`)
      } else if (evt.event === 'done') {
        addLog('info', `Done — indexed ${evt.indexed}/${evt.total} file(s).`)
        ws.close()
        setBusy(false)
      }
    })
    wsRef.current = ws

    try {
      const resp = await postIngest(dir)
      addLog('info', `Request accepted — ${resp.files_found} file(s) queued.`)
    } catch (err: unknown) {
      addLog('error', err instanceof Error ? err.message : String(err))
      ws.close()
      setBusy(false)
    }
  }

  return (
    <div className="panel ingest-panel">
      <p className="panel__desc">
        Enter the absolute path to a directory containing <code>.cbl</code> / <code>.cob</code> / <code>.cpy</code> files.
      </p>
      <div className="input-row">
        <input
          className="path-input"
          type="text"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleIngest()}
          placeholder="/path/to/cobol/source"
          disabled={busy}
        />
        <button className="btn btn--primary" onClick={handleIngest} disabled={busy || !path.trim()}>
          {busy ? 'Indexing…' : 'Index'}
        </button>
      </div>

      {log.length > 0 && (
        <div className="ingest-log">
          {log.map((entry, i) => (
            <div key={i} className={`log-line log-line--${entry.kind}`}>
              {entry.text}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  )
}
