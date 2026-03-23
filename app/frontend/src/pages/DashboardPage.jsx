import React, { useEffect, useState } from 'react'
import { Plus, LogOut } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { get } from '../api/client'
import ProjectCard from '../components/ProjectCard'
import NewProjectModal from '../components/NewProjectModal'

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNewModal, setShowNewModal] = useState(false)

  const fetchProjects = async () => {
    try {
      const data = await get('/projects')
      setProjects(data)
    } catch (err) {
      console.error('Failed to fetch projects:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProjects() }, [])

  const handleCreated = (project) => {
    setProjects((prev) => [project, ...prev])
    setShowNewModal(false)
  }

  const handleDelete = (projectId) => {
    setProjects((prev) => prev.filter((p) => p.id !== projectId))
  }

  return (
    <div className="scanlines min-h-screen bg-zinc-950 flex flex-col">

      {/* Header */}
      <header className="bg-zinc-900 border-b-2 border-zinc-700 sticky top-0 z-10"
        style={{ boxShadow: '0 4px 0 0 #000' }}>
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">👾</span>
            <span className="font-pixel text-accent-400" style={{ fontSize: '11px', textShadow: '2px 2px 0 #000' }}>
              STORY BUILDER
            </span>
          </div>

          <div className="flex items-center gap-4">
            {user && (
              <span className="text-retro text-zinc-500 hidden sm:block">
                {user.email}
              </span>
            )}
            <button
              onClick={logout}
              className="btn-pixel-ghost"
              style={{ fontSize: '8px' }}
            >
              <LogOut className="w-3 h-3" />
              SIGN OUT
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8">

        {/* Page title */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="heading-pixel text-zinc-100 mb-1">
              ▸ YOUR STORIES
            </h2>
            <p className="text-retro text-zinc-500">
              {projects.length} project{projects.length !== 1 ? 's' : ''} in your library
            </p>
          </div>
          <button onClick={() => setShowNewModal(true)} className="btn-pixel">
            <Plus className="w-3 h-3" />
            NEW STORY
          </button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-4">
            <span className="pixel-spinner" />
            <span className="text-retro text-zinc-400">LOADING...</span>
          </div>
        ) : projects.length === 0 ? (
          <div className="pixel-panel p-12 text-center">
            <div className="text-6xl mb-6">📼</div>
            <h3 className="heading-pixel text-zinc-300 mb-3">NO STORIES FOUND</h3>
            <p className="text-retro text-zinc-500 mb-8 max-w-xs mx-auto">
              Your quest log is empty. Begin your first story to get started.
            </p>
            <button onClick={() => setShowNewModal(true)} className="btn-pixel">
              <Plus className="w-3 h-3" />
              START FIRST STORY
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </main>

      {showNewModal && (
        <NewProjectModal
          onCreated={handleCreated}
          onClose={() => setShowNewModal(false)}
        />
      )}
    </div>
  )
}
