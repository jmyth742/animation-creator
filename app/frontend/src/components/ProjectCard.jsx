import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Tv, Users, Trash2 } from 'lucide-react'
import { del } from '../api/client'

const CARD_COLORS = [
  'border-accent-700',
  'border-px-cyan',
  'border-px-green',
  'border-px-yellow',
  'border-px-orange',
]

export default function ProjectCard({ project, onDelete }) {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const menuRef = useRef(null)

  // Deterministic color based on project id
  const borderColor = CARD_COLORS[project.id % CARD_COLORS.length]

  const truncated =
    project.premise && project.premise.length > 100
      ? project.premise.slice(0, 100) + '…'
      : project.premise

  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleDelete = async (e) => {
    e.stopPropagation()
    if (!window.confirm(`DELETE "${project.title}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await del(`/projects/${project.id}`)
      onDelete(project.id)
    } catch (err) {
      alert('Failed to delete project.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div
      onClick={() => navigate(`/projects/${project.id}`)}
      className={`group relative bg-zinc-900 border-2 ${borderColor} cursor-pointer flex flex-col gap-3 p-5 transition-all duration-100`}
      style={{ boxShadow: '4px 4px 0 0 #000' }}
      onMouseEnter={(e) => { e.currentTarget.style.transform = 'translate(-2px,-2px)'; e.currentTarget.style.boxShadow = '6px 6px 0 0 #000' }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '4px 4px 0 0 #000' }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-pixel text-zinc-100 flex-1 leading-relaxed" style={{ fontSize: '9px', textShadow: '1px 1px 0 #000' }}>
          {project.title}
        </h3>

        {/* Menu */}
        <div ref={menuRef} onClick={(e) => e.stopPropagation()} className="shrink-0">
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="text-zinc-600 hover:text-zinc-300 font-pixel opacity-0 group-hover:opacity-100 transition-opacity px-1"
            style={{ fontSize: '10px' }}
          >
            ···
          </button>
          {menuOpen && (
            <div className="absolute right-2 top-10 z-20 bg-zinc-800 border-2 border-zinc-600 min-w-32"
              style={{ boxShadow: '4px 4px 0 0 #000' }}>
              <button
                onClick={() => { setMenuOpen(false); navigate(`/projects/${project.id}`) }}
                className="w-full text-left px-4 py-2 text-retro text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 border-b border-zinc-700"
              >
                ▶ OPEN
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="w-full text-left px-4 py-2 text-retro text-px-red hover:bg-zinc-700 flex items-center gap-2 disabled:opacity-50"
              >
                <Trash2 className="w-3 h-3" />
                {deleting ? 'DELETING...' : 'DELETE'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Premise */}
      {truncated && (
        <p className="text-retro text-zinc-400 flex-1" style={{ fontSize: '16px', lineHeight: '1.4' }}>
          {truncated}
        </p>
      )}

      {/* Stats badges */}
      <div className="flex items-center gap-2 pt-1 flex-wrap">
        <span className="badge-pixel">
          <Tv className="w-2.5 h-2.5 text-accent-400" />
          {project.episode_count ?? project.episodes?.length ?? 0} EP
        </span>
        <span className="badge-pixel">
          <Users className="w-2.5 h-2.5 text-accent-400" />
          {project.character_count ?? project.characters?.length ?? 0} CHAR
        </span>
        {project.tone && (
          <span className="badge-pixel-accent">{project.tone.slice(0, 12)}</span>
        )}
      </div>
    </div>
  )
}
