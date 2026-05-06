import { useEffect, useState } from 'react'
import { getProgram, getWorkspaces } from '../api'
import type { ProgramDetail, ProgramSummary } from '../api'

export default function WorkspacePanel() {
  const [programs, setPrograms] = useState<ProgramSummary[]>([])
  const [selected, setSelected] = useState<ProgramDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    getWorkspaces()
      .then(setPrograms)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function selectProgram(id: number) {
    if (selected?.id === id) { setSelected(null); return }
    setDetailLoading(true)
    try {
      setSelected(await getProgram(id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetailLoading(false)
    }
  }

  if (loading) return <div className="panel"><p className="placeholder">Loading…</p></div>
  if (error) return <div className="panel"><p className="error-text">{error}</p></div>

  return (
    <div className="panel workspace-panel">
      {programs.length === 0 ? (
        <p className="placeholder">No programs indexed yet. Use the Ingest tab to add a workspace.</p>
      ) : (
        <div className="program-list">
          {programs.map((p) => (
            <div key={p.id} className="program-card">
              <button
                className={`program-card__header ${selected?.id === p.id ? 'program-card__header--open' : ''}`}
                onClick={() => selectProgram(p.id)}
              >
                <span className="program-card__name">{p.name}</span>
                <span className="program-card__stats">
                  {p.loc} LOC · {p.move_count} MOVEs · {p.linkage_count} linkage vars
                </span>
                <span className="program-card__chevron">{selected?.id === p.id ? '▲' : '▼'}</span>
              </button>

              {selected?.id === p.id && (
                detailLoading ? (
                  <p className="program-card__body">Loading…</p>
                ) : (
                  <div className="program-card__body">
                    <p className="detail-path">{selected.path}</p>
                    <p className="detail-date">Indexed {new Date(selected.indexed_at).toLocaleString()}</p>

                    <DetailSection title="Called modules" items={selected.modules} empty="None" />

                    <DetailSection
                      title="SQL tables"
                      items={selected.tables_ref.map((t) => `${t.table_name} [${t.op_type}]`)}
                      empty="None"
                    />

                    <DetailSection
                      title="File operations"
                      items={selected.files_ref.map((f) => `${f.file_name} [${f.op_type}]`)}
                      empty="None"
                    />
                  </div>
                )
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DetailSection({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="detail-section">
      <h4 className="detail-section__title">{title}</h4>
      {items.length === 0 ? (
        <span className="detail-section__empty">{empty}</span>
      ) : (
        <ul className="detail-section__list">
          {items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
      )}
    </div>
  )
}
