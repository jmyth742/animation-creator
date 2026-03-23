import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Tv, MapPin, Settings } from 'lucide-react'
import { get } from '../api/client'
import CharactersTab from '../components/CharactersTab'
import EpisodesTab from '../components/EpisodesTab'
import LocationsTab from '../components/LocationsTab'
import ProjectSettingsForm from '../components/ProjectSettingsForm'
import ProductionPanel from '../components/ProductionPanel'

const TABS = [
  { key: 'characters', label: 'Characters', Icon: Users },
  { key: 'locations', label: 'Locations', Icon: MapPin },
  { key: 'episodes', label: 'Episodes', Icon: Tv },
  { key: 'settings', label: 'Settings', Icon: Settings },
]

export default function ProjectPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('characters')
  const [activeJobId, setActiveJobId] = useState(null)
  const [activeJobMeta, setActiveJobMeta] = useState(null) // { episodeTitle, seriesSlug, episodeNumber }

  const fetchProject = async () => {
    try {
      const data = await get(`/projects/${id}`)
      setProject(data)
    } catch (err) {
      setError('Failed to load project.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProject()
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCharactersChange = () => fetchProject()
  const handleEpisodesChange = () => fetchProject()
  const handleLocationsChange = () => fetchProject()
  const handleProjectUpdate = (updated) => setProject(updated)

  const handleProduce = (jobId, meta) => {
    setActiveJobId(jobId)
    setActiveJobMeta(meta)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <span className="w-8 h-8 border-2 border-zinc-700 border-t-accent-500 rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !project) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || 'Project not found.'}</p>
          <button
            onClick={() => navigate('/')}
            className="text-accent-400 hover:text-accent-300 text-sm"
          >
            Back to dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col">
      {/* Header */}
      <header className="bg-zinc-900 border-b border-zinc-800 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-zinc-400 hover:text-zinc-200 p-1.5 rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-zinc-100 truncate">{project.title}</h1>
            {project.tone && (
              <p className="text-xs text-zinc-500 truncate">{project.tone}</p>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-7xl mx-auto px-6">
          <nav className="flex gap-1 -mb-px">
            {TABS.map(({ key, label, Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === key
                    ? 'border-accent-500 text-accent-400'
                    : 'border-transparent text-zinc-400 hover:text-zinc-200 hover:border-zinc-600'
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Tab content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8">
        {activeTab === 'characters' && (
          <CharactersTab
            projectId={id}
            characters={project.characters || []}
            onCharactersChange={handleCharactersChange}
          />
        )}
        {activeTab === 'locations' && (
          <LocationsTab
            projectId={id}
            locations={project.locations || []}
            onLocationsChange={handleLocationsChange}
          />
        )}
        {activeTab === 'episodes' && (
          <EpisodesTab
            projectId={id}
            project={project}
            episodes={project.episodes || []}
            onEpisodesChange={handleEpisodesChange}
            onProduce={handleProduce}
          />
        )}
        {activeTab === 'settings' && (
          <ProjectSettingsForm project={project} onUpdate={handleProjectUpdate} />
        )}
      </main>

      {/* Production panel */}
      {activeJobId && activeJobMeta && (
        <ProductionPanel
          jobId={activeJobId}
          episodeTitle={activeJobMeta.episodeTitle}
          seriesSlug={activeJobMeta.seriesSlug}
          episodeNumber={activeJobMeta.episodeNumber}
          onClose={() => { setActiveJobId(null); setActiveJobMeta(null) }}
        />
      )}
    </div>
  )
}
