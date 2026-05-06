import { useRef, useState } from 'react'
import { streamQuery } from '../api'

interface Message {
  role: 'user' | 'assistant' | 'error'
  text: string
}

export default function QueryPanel() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState(false)
  const cancelRef = useRef<(() => void) | null>(null)

  function submit() {
    const q = input.trim()
    if (!q || streaming) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: q }])

    // placeholder for the assistant turn
    setMessages((prev) => [...prev, { role: 'assistant', text: '' }])
    setStreaming(true)

    cancelRef.current = streamQuery(
      q,
      (token) => {
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = {
            ...next[next.length - 1],
            text: next[next.length - 1].text + token,
          }
          return next
        })
      },
      () => setStreaming(false),
      (detail) => {
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = { role: 'error', text: detail }
          return next
        })
        setStreaming(false)
      },
    )
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
  }

  return (
    <div className="panel query-panel">
      <div className="messages">
        {messages.length === 0 && (
          <p className="placeholder">Ask anything about your COBOL codebase.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message message--${m.role}`}>
            <span className="message__role">
              {m.role === 'user' ? 'You' : m.role === 'error' ? 'Error' : 'Assistant'}
            </span>
            <pre className="message__text">{m.text}{m.role === 'assistant' && streaming && i === messages.length - 1 ? '▋' : ''}</pre>
          </div>
        ))}
      </div>
      <div className="input-row">
        <textarea
          className="query-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about your COBOL programs… (Enter to send)"
          rows={2}
          disabled={streaming}
        />
        <button className="btn btn--primary" onClick={submit} disabled={streaming || !input.trim()}>
          {streaming ? 'Streaming…' : 'Send'}
        </button>
      </div>
    </div>
  )
}
