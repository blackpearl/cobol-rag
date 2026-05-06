import { useState } from 'react'
import IngestPanel from './components/IngestPanel'
import QueryPanel from './components/QueryPanel'
import WorkspacePanel from './components/WorkspacePanel'
import './App.css'

type Tab = 'query' | 'ingest' | 'browse'

const TABS: { id: Tab; label: string }[] = [
  { id: 'query', label: 'Query' },
  { id: 'ingest', label: 'Ingest' },
  { id: 'browse', label: 'Browse' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('query')

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__inner">
          <span className="app-title">COBOL RAG</span>
          <nav className="tab-nav">
            {TABS.map((t) => (
              <button
                key={t.id}
                className={`tab-btn ${tab === t.id ? 'tab-btn--active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="app-main">
        {tab === 'query' && <QueryPanel />}
        {tab === 'ingest' && <IngestPanel />}
        {tab === 'browse' && <WorkspacePanel />}
      </main>
    </div>
  )
}
