import React, { useEffect, useState } from 'react'
import { Film, Plus, LogOut, FolderOpen } from 'lucide-react'
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

  useEffect(() => {
    fetchProjects()
  }, [])

  const handleCreated = (project) => {
    setProjects((prev) => [project, ...prev])
    setShowNewModal(false)
  }

  const handleDelete = (projectId) => {
    setProjects((prev) => prev.filter((p) => p.id !== projectId))
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      {/* Header */}
      <header className="bg-zinc-900 border-b border-zinc-800 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-accent-600 rounded-xl flex items-center justify-center shadow-md shadow-accent-900/40">
              <Film className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-zinc-100 tracking-tight">Story Builder</span>
          </div>

          <div className="flex items-center gap-4">
            {user && (
              <span className="text-sm text-zinc-400 hidden sm:block">{user.email}</span>
            )}
            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors px-3 py-1.5 rounded-lg hover:bg-zinc-800"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8">
        {/* Page title + action */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-2xl font-bold text-zinc-100">Projects</h2>
            <p className="text-zinc-400 text-sm mt-1">Your animated video series</p>
          </div>
          <button
            onClick={() => setShowNewModal(true)}
            className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-4 py-2.5 text-sm transition-colors shadow-lg shadow-accent-900/30"
          >
            <Plus className="w-4 h-4" />
            New Project
          </button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <span className="w-8 h-8 border-2 border-zinc-700 border-t-accent-500 rounded-full animate-spin" />
          </div>
        ) : projects.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <div className="w-20 h-20 bg-zinc-800 rounded-3xl flex items-center justify-center mb-5">
              <FolderOpen className="w-10 h-10 text-zinc-600" />
            </div>
            <h3 className="text-xl font-semibold text-zinc-300 mb-2">No projects yet</h3>
            <p className="text-zinc-500 text-sm max-w-xs mb-6">
              Create your first animated series project to get started.
            </p>
            <button
              onClick={() => setShowNewModal(true)}
              className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-5 py-2.5 text-sm transition-colors"
            >
              <Plus className="w-4 h-4" />
              Create your first project
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
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

      {/* New project modal */}
      {showNewModal && (
        <NewProjectModal
          onCreated={handleCreated}
          onClose={() => setShowNewModal(false)}
        />
      )}
    </div>
  )
}
