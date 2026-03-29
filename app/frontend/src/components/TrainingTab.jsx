import React, { useEffect, useState, useCallback } from 'react'
import { Plus, ChevronDown, ChevronRight, XCircle, HardDrive, Clock, Cpu, Images, RotateCw } from 'lucide-react'
import { get, post, put } from '../api/client'
import TrainingModal from './TrainingModal'

const ACTIVE_STATUSES = ['pending', 'provisioning', 'bootstrapping', 'uploading', 'training', 'downloading']

const STATUS_STYLES = {
  pending:        'bg-yellow-900/60 text-yellow-400 border-yellow-700',
  provisioning:   'bg-blue-900/60 text-blue-400 border-blue-700',
  bootstrapping:  'bg-blue-900/60 text-blue-400 border-blue-700',
  uploading:      'bg-blue-900/60 text-blue-400 border-blue-700',
  training:       'bg-purple-900/60 text-purple-400 border-purple-700',
  downloading:    'bg-blue-900/60 text-blue-400 border-blue-700',
  complete:       'bg-green-900/60 text-green-400 border-green-700',
  error:          'bg-red-900/60 text-red-400 border-red-700',
  cancelled:      'bg-zinc-800/60 text-zinc-400 border-zinc-600',
}

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending
  const isTraining = status === 'training'
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 border rounded font-pixel text-xs uppercase ${style}`}
      style={{ fontSize: '8px' }}>
      {isTraining && (
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
      )}
      {status}
    </span>
  )
}

function ProgressBar({ progress = 0 }) {
  const pct = Math.min(100, Math.max(0, progress))
  return (
    <div className="w-full bg-zinc-800 border border-zinc-700 h-3 rounded-sm overflow-hidden">
      <div
        className="h-full bg-accent-500 transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function formatBytes(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`
  return `${(bytes / 1073741824).toFixed(2)} GB`
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export default function TrainingTab({ projectId, project = {}, onTrainingChange }) {
  const [jobs, setJobs] = useState([])
  const [loras, setLoras] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [expandedLogs, setExpandedLogs] = useState({})
  const [cancellingId, setCancellingId] = useState(null)
  const [assigningLora, setAssigningLora] = useState({})
  const [datasetPreview, setDatasetPreview] = useState(null) // { jobId, images, selectedImage }

  const openDatasetPreview = async (jobId) => {
    try {
      const data = await get(`/training/${jobId}/dataset-preview`)
      setDatasetPreview({ jobId, images: data.images || [], selectedImage: null })
    } catch {
      // ignore
    }
  }

  const characters = project.characters || []
  const locations = project.locations || []

  const fetchData = useCallback(async () => {
    try {
      const [jobsData, lorasData] = await Promise.all([
        get(`/projects/${projectId}/training`),
        get(`/projects/${projectId}/loras`).catch(() => []),
      ])
      setJobs(jobsData)
      setLoras(lorasData)
    } catch {
      // silent — polling will retry
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Poll every 5s while any job is active
  useEffect(() => {
    const hasActive = jobs.some((j) => ACTIVE_STATUSES.includes(j.status))
    if (!hasActive) return

    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [jobs, fetchData])

  const toggleLog = (jobId) => {
    setExpandedLogs((prev) => ({ ...prev, [jobId]: !prev[jobId] }))
  }

  const handleCancel = async (jobId) => {
    if (!window.confirm('Cancel this training job?')) return
    setCancellingId(jobId)
    try {
      await post(`/training/${jobId}/cancel`)
      fetchData()
    } catch {
      alert('Failed to cancel job.')
    } finally {
      setCancellingId(null)
    }
  }

  const [retryingId, setRetryingId] = useState(null)
  const [retryGpuPicker, setRetryGpuPicker] = useState(null) // { jobId, gpus: [] }
  const [availableGpus, setAvailableGpus] = useState(null)

  const handleRetryClick = async (jobId) => {
    // Fetch available GPUs if not cached
    if (!availableGpus) {
      try {
        const gpus = await get('/training/gpu-availability')
        setAvailableGpus(gpus)
        setRetryGpuPicker({ jobId, gpus })
      } catch {
        // Fallback: retry with same GPU
        handleRetry(jobId, null)
      }
    } else {
      setRetryGpuPicker({ jobId, gpus: availableGpus })
    }
  }

  const handleRetry = async (jobId, gpuType) => {
    setRetryGpuPicker(null)
    setRetryingId(jobId)
    try {
      const body = gpuType ? { gpu_type: gpuType } : {}
      await post(`/training/${jobId}/retry`, body)
      fetchData()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to retry job.')
    } finally {
      setRetryingId(null)
    }
  }

  // Close GPU picker on outside click
  useEffect(() => {
    if (!retryGpuPicker) return
    const handler = () => setRetryGpuPicker(null)
    const timer = setTimeout(() => document.addEventListener('click', handler), 0)
    return () => { clearTimeout(timer); document.removeEventListener('click', handler) }
  }, [retryGpuPicker])

  const handleAssignLora = async (loraFilename, assignValue) => {
    setAssigningLora((prev) => ({ ...prev, [loraFilename]: true }))
    try {
      const payload = { filename: loraFilename, character_id: null, location_id: null }
      if (assignValue) {
        const [type, id] = assignValue.split(':')
        if (type === 'char') payload.character_id = Number(id)
        else if (type === 'loc') payload.location_id = Number(id)
      }
      await put(`/projects/${projectId}/loras/assign`, payload)
      fetchData()
      onTrainingChange?.()
    } catch {
      alert('Failed to assign LoRA.')
    } finally {
      setAssigningLora((prev) => ({ ...prev, [loraFilename]: false }))
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 gap-3">
        <span className="pixel-spinner" />
        <span className="text-retro text-zinc-400">LOADING FORGE...</span>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="heading-pixel text-zinc-100 mb-1">🔥 FORGE — LoRA TRAINING</h2>
          <p className="text-retro text-zinc-500">
            Train character & location LoRAs on cloud GPUs
          </p>
        </div>
        <button onClick={() => setShowModal(true)} className="btn-pixel">
          <Plus className="w-3 h-3" />
          NEW JOB
        </button>
      </div>

      {/* Available LoRAs section */}
      {loras.length > 0 && (
        <div className="mb-8">
          <h3 className="heading-pixel text-zinc-300 mb-3 text-sm">
            <HardDrive className="w-3 h-3 inline mr-2" />
            AVAILABLE LoRAs
          </h3>
          <div className="pixel-panel divide-y divide-zinc-700/50">
            {loras.map((lora) => (
              <div key={lora.filename} className="px-4 py-3 flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-retro text-zinc-200 truncate">{lora.filename}</p>
                  <p className="text-retro text-zinc-500 text-xs">
                    {formatBytes(lora.size)} — {formatDate(lora.modified)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    className="input-pixel text-xs py-1"
                    value={
                      lora.character_id ? `char:${lora.character_id}` :
                      lora.location_id ? `loc:${lora.location_id}` : ''
                    }
                    onChange={(e) => handleAssignLora(lora.filename, e.target.value)}
                    disabled={assigningLora[lora.filename]}
                  >
                    <option value="">— Assign to... —</option>
                    {characters.length > 0 && <optgroup label="Characters">
                      {characters.map((c) => (
                        <option key={`c${c.id}`} value={`char:${c.id}`}>{c.name}</option>
                      ))}
                    </optgroup>}
                    {locations.length > 0 && <optgroup label="Locations">
                      {locations.map((l) => (
                        <option key={`l${l.id}`} value={`loc:${l.id}`}>{l.name}</option>
                      ))}
                    </optgroup>}
                  </select>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Training Jobs section */}
      <h3 className="heading-pixel text-zinc-300 mb-3 text-sm">
        <Cpu className="w-3 h-3 inline mr-2" />
        TRAINING JOBS
      </h3>

      {jobs.length === 0 ? (
        <div className="pixel-panel p-12 text-center">
          <div className="text-5xl mb-5">🔨</div>
          <h3 className="heading-pixel text-zinc-300 mb-3">NO TRAINING JOBS</h3>
          <p className="text-retro text-zinc-500 mb-6 max-w-sm mx-auto">
            Train a LoRA to teach the model a character's face or a location's look. Upload a dataset or auto-generate one and let the GPU forge your model.
          </p>
          <button onClick={() => setShowModal(true)} className="btn-pixel">
            <Plus className="w-3 h-3" />
            CREATE FIRST JOB
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => {
            const isActive = ACTIVE_STATUSES.includes(job.status)
            const isExpanded = expandedLogs[job.id]
            return (
              <div key={job.id} className="pixel-panel">
                {/* Job header row */}
                <div className="px-4 py-3 flex items-center gap-4">
                  {/* Expand toggle */}
                  <button
                    onClick={() => toggleLog(job.id)}
                    className="text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    {isExpanded
                      ? <ChevronDown className="w-4 h-4" />
                      : <ChevronRight className="w-4 h-4" />}
                  </button>

                  {/* Subject + status */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-retro text-zinc-100 font-bold">
                        {job.location_id ? '📍 ' : ''}{job.character_name}
                      </span>
                      <StatusBadge status={job.status} />
                      {(job.total_attempts || 1) > 1 && (
                        <span className="text-retro text-zinc-500 text-xs">
                          attempt {job.attempt || 1}/{job.total_attempts}
                        </span>
                      )}
                    </div>

                    {/* Progress bar for active jobs */}
                    {isActive && (
                      <div>
                        <div className="flex items-center gap-3">
                          <div className="flex-1">
                            <ProgressBar progress={job.progress_pct || job.progress || 0} />
                          </div>
                          <span className="text-retro text-zinc-500 text-xs whitespace-nowrap">
                            {Math.round(job.progress_pct || job.progress || 0)}%
                          </span>
                        </div>
                        {/* Training stats row */}
                        {job.status === 'training' && (
                          <div className="flex items-center gap-4 mt-1 text-retro text-xs">
                            {job.training_loss != null && (
                              <span className="text-accent-400">
                                loss: {job.training_loss.toFixed(4)}
                              </span>
                            )}
                            {job.epochs && job.progress_pct > 50 && (
                              <span className="text-zinc-500">
                                ~epoch {Math.round(((job.progress_pct - 50) / 40) * job.epochs)}/{job.epochs}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Completed job stats */}
                    {job.status === 'complete' && job.training_loss != null && (
                      <div className="mt-1 text-retro text-xs">
                        <span className="text-px-green">final loss: {job.training_loss.toFixed(4)}</span>
                        {job.lora_path && (
                          <span className="text-zinc-500 ml-3">{job.lora_path}</span>
                        )}
                      </div>
                    )}

                    {/* Meta row */}
                    <div className="flex items-center gap-4 mt-1 text-retro text-zinc-500 text-xs">
                      {job.gpu_type && (
                        <span className="flex items-center gap-1">
                          <Cpu className="w-2.5 h-2.5" />
                          {job.gpu_type === 'local' ? 'This Pod' : job.gpu_type}
                        </span>
                      )}
                      {job.rank && (
                        <span>r{job.rank}</span>
                      )}
                      {job.epochs && (
                        <span>{job.epochs}ep</span>
                      )}
                      {job.created_at && (
                        <span className="flex items-center gap-1">
                          <Clock className="w-2.5 h-2.5" />
                          {formatDate(job.created_at)}
                        </span>
                      )}
                      {job.completed_at && (
                        <span>Done {formatDate(job.completed_at)}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* View Dataset button */}
                    {job.dataset_path && (
                      <button
                        onClick={() => openDatasetPreview(job.id)}
                        className="btn-pixel-ghost flex items-center gap-1 text-xs"
                      >
                        <Images className="w-3 h-3" />
                        DATASET
                      </button>
                    )}

                    {/* Retry button for failed/cancelled jobs */}
                    {(job.status === 'error' || job.status === 'cancelled') && (
                      <div className="relative">
                        <button
                          onClick={() => handleRetryClick(job.id)}
                          disabled={retryingId === job.id}
                          className="btn-pixel-ghost flex items-center gap-1 text-xs"
                        >
                          <RotateCw className={`w-3 h-3 ${retryingId === job.id ? 'animate-spin' : ''}`} />
                          {retryingId === job.id ? 'RETRYING...' : 'RETRY'}
                        </button>

                        {/* GPU picker dropdown */}
                        {retryGpuPicker?.jobId === job.id && (
                          <div className="absolute right-0 top-full mt-1 z-40 pixel-panel border border-zinc-600 w-72 shadow-lg">
                            <div className="px-3 py-2 border-b border-zinc-700">
                              <p className="label-pixel text-xs">SELECT GPU</p>
                            </div>
                            <div className="max-h-48 overflow-y-auto">
                              {/* Local training option */}
                              <button
                                onClick={() => handleRetry(job.id, 'local')}
                                className="w-full text-left px-3 py-2 hover:bg-zinc-700/50 transition-colors flex justify-between items-center gap-2 border-b border-zinc-700"
                              >
                                <span className="text-retro text-zinc-200 text-xs flex-1">
                                  This Pod (RTX 3090, 24GB)
                                </span>
                                <span className="text-retro text-xs flex items-center gap-1 text-px-green">
                                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-400" />
                                  Ready
                                </span>
                                <span className="text-retro text-zinc-500 text-xs w-16 text-right">
                                  free
                                </span>
                              </button>
                              {retryGpuPicker.gpus.map((gpu) => {
                                const stockColor = gpu.stock === 'High' ? 'text-px-green' : gpu.stock === 'Medium' ? 'text-yellow-400' : 'text-red-400'
                                const dotColor = gpu.stock === 'High' ? 'bg-green-400' : gpu.stock === 'Medium' ? 'bg-yellow-400' : 'bg-red-400'
                                return (
                                  <button
                                    key={gpu.id}
                                    onClick={() => handleRetry(job.id, gpu.id)}
                                    className="w-full text-left px-3 py-2 hover:bg-zinc-700/50 transition-colors flex justify-between items-center gap-2"
                                  >
                                    <span className="text-retro text-zinc-200 text-xs flex-1">
                                      {gpu.name} ({gpu.vram_gb}GB)
                                    </span>
                                    <span className={`text-retro text-xs flex items-center gap-1 ${stockColor}`}>
                                      <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotColor}`} />
                                      {gpu.stock}
                                    </span>
                                    <span className="text-retro text-zinc-500 text-xs w-16 text-right">
                                      ${gpu.price}/hr
                                    </span>
                                  </button>
                                )
                              })}
                            </div>
                            <div className="px-3 py-2 border-t border-zinc-700">
                              <button
                                onClick={() => handleRetry(job.id, null)}
                                className="text-retro text-zinc-500 text-xs hover:text-zinc-300"
                              >
                                Use same GPU ({job.gpu_type})
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Cancel button */}
                    {isActive && (
                      <button
                        onClick={() => handleCancel(job.id)}
                        disabled={cancellingId === job.id}
                        className="btn-pixel-ghost text-px-red hover:text-red-300 flex items-center gap-1"
                      >
                        <XCircle className="w-3 h-3" />
                        {cancellingId === job.id ? 'CANCELLING...' : 'CANCEL'}
                      </button>
                    )}
                  </div>
                </div>

                {/* Expandable log + attempt history */}
                {isExpanded && (
                  <div className="border-t border-zinc-700/50 px-4 py-3 space-y-3">
                    {/* Log viewer */}
                    <pre className="bg-zinc-950 border border-zinc-700 rounded p-3 text-retro text-zinc-400 text-xs overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
                      {job.log_text || 'No logs available yet.'}
                    </pre>

                    {/* Attempt history */}
                    {job.attempts && job.attempts.length > 1 && (
                      <div>
                        <p className="label-pixel text-xs mb-1">ATTEMPT HISTORY</p>
                        <div className="space-y-1">
                          {job.attempts.map((a) => (
                            <div key={a.id} className="flex items-center gap-3 text-retro text-xs">
                              <span className="text-zinc-500 w-6">#{a.attempt}</span>
                              <StatusBadge status={a.status} />
                              <span className="text-zinc-500">
                                {a.gpu_type === 'local' ? 'This Pod' : a.gpu_type}
                              </span>
                              {a.training_loss != null && (
                                <span className="text-zinc-400">loss: {a.training_loss.toFixed(4)}</span>
                              )}
                              <span className="text-zinc-600 ml-auto">
                                {a.created_at ? new Date(a.created_at).toLocaleString() : ''}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Dataset preview modal */}
      {datasetPreview && (
        <div className="modal-overlay" onClick={() => setDatasetPreview(null)}>
          <div className="modal-pixel max-w-4xl" style={{ maxHeight: '90vh' }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="heading-pixel-sm text-accent-400">
                DATASET PREVIEW ({datasetPreview.images.length} images)
              </span>
              <button onClick={() => setDatasetPreview(null)} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">X</button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {datasetPreview.images.length === 0 ? (
                <p className="text-retro text-zinc-500 text-center py-8">No images in dataset.</p>
              ) : (
                <div className="grid grid-cols-5 gap-2">
                  {datasetPreview.images.map((img, i) => (
                    <div
                      key={i}
                      className="relative group cursor-pointer border border-zinc-700 hover:border-accent-500 transition-colors bg-zinc-800"
                      onClick={() => setDatasetPreview((p) => ({ ...p, selectedImage: img }))}
                    >
                      <img
                        src={`http://localhost:8000${img.url}`}
                        alt={img.filename}
                        className="w-full aspect-[3/4] object-cover"
                        loading="lazy"
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-1 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <p className="text-retro text-zinc-300 truncate" style={{ fontSize: '7px' }}>{img.caption.slice(0, 80)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={() => setDatasetPreview(null)} className="btn-pixel-ghost">CLOSE</button>
            </div>
          </div>

          {/* Full-size image viewer */}
          {datasetPreview.selectedImage && (
            <div
              className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center cursor-pointer"
              onClick={() => setDatasetPreview((p) => ({ ...p, selectedImage: null }))}
            >
              <div className="max-w-2xl max-h-[80vh] relative" onClick={(e) => e.stopPropagation()}>
                <img
                  src={`http://localhost:8000${datasetPreview.selectedImage.url}`}
                  alt={datasetPreview.selectedImage.filename}
                  className="max-w-full max-h-[70vh] object-contain"
                />
                <div className="mt-3 px-2">
                  <p className="text-retro text-zinc-300 text-sm">{datasetPreview.selectedImage.caption}</p>
                  <p className="text-retro text-zinc-600 text-xs mt-1">{datasetPreview.selectedImage.filename}</p>
                </div>
                <button
                  onClick={() => setDatasetPreview((p) => ({ ...p, selectedImage: null }))}
                  className="absolute top-2 right-2 text-zinc-400 hover:text-white text-lg"
                >X</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Training modal */}
      {showModal && (
        <TrainingModal
          projectId={projectId}
          characters={characters}
          locations={locations}
          onCreated={() => {
            setShowModal(false)
            fetchData()
            onTrainingChange?.()
          }}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  )
}
