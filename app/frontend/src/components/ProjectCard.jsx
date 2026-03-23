import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { MoreVertical, Tv, Users, Trash2 } from 'lucide-react'
import { del } from '../api/client'

export default function ProjectCard({ project, onDelete }) {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const menuRef = useRef(null)

  const truncated =
    project.premise && project.premise.length > 120
      ? project.premise.slice(0, 120) + '…'
      : project.premise

  // Close menu on outside click
  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleDelete = async (e) => {
    e.stopPropagation()
    if (!window.confirm(`Delete "${project.title}"? This cannot be undone.`)) return
    setDeleting(true)
    try {
      await del(`/projects/${project.id}`)
      onDelete(project.id)
    } catch (err) {
      console.error('Delete failed:', err)
      alert('Failed to delete project.')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div
      onClick={() => navigate(`/projects/${project.id}`)}
      className="group relative bg-zinc-900 hover:bg-zinc-800 border border-zinc-700/50 hover:border-zinc-600 rounded-xl p-5 cursor-pointer transition-all duration-150 flex flex-col gap-3"
    >
      {/* Three-dot menu */}
      <div
        ref={menuRef}
        className="absolute top-3 right-3"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={() => setMenuOpen((o) => !o)}
          className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-700 transition-colors opacity-0 group-hover:opacity-100"
        >
          <MoreVertical className="w-4 h-4" />
        </button>

        {menuOpen && (
          <div className="absolute right-0 top-8 z-20 w-40 bg-zinc-800 border border-zinc-700 rounded-xl shadow-xl py-1">
            <button
              onClick={() => { setMenuOpen(false); navigate(`/projects/${project.id}`) }}
              className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 transition-colors"
            >
              Open
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-zinc-700 hover:text-red-300 transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        )}
      </div>

      {/* Title */}
      <h3 className="text-base font-semibold text-zinc-100 pr-6 leading-snug">
        {project.title}
      </h3>

      {/* Premise */}
      {truncated && (
        <p className="text-sm text-zinc-400 leading-relaxed flex-1">{truncated}</p>
      )}

      {/* Badges */}
      <div className="flex items-center gap-2 pt-1 flex-wrap">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-zinc-800 border border-zinc-700 rounded-full text-xs text-zinc-300">
          <Tv className="w-3 h-3 text-accent-400" />
          {project.episode_count ?? project.episodes?.length ?? 0} episodes
        </span>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-zinc-800 border border-zinc-700 rounded-full text-xs text-zinc-300">
          <Users className="w-3 h-3 text-accent-400" />
          {project.character_count ?? project.characters?.length ?? 0} characters
        </span>
        {project.tone && (
          <span className="inline-flex items-center px-2.5 py-1 bg-accent-950/60 border border-accent-800/50 rounded-full text-xs text-accent-300">
            {project.tone}
          </span>
        )}
      </div>
    </div>
  )
}
