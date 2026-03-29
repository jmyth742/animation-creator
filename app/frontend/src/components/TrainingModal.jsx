import React, { useState, useRef, useEffect } from 'react'
import { Upload, X, Wand2, Loader } from 'lucide-react'
import { get, post } from '../api/client'

const GPU_OPTIONS = [
  { value: 'local', label: 'This Pod (RTX 3090 — free, 24GB VRAM)', cost: 0 },
  { value: 'NVIDIA RTX A6000', label: 'RunPod: RTX A6000 — $0.33/hr, 48GB', cost: 0.33 },
  { value: 'NVIDIA RTX A5000', label: 'RunPod: RTX A5000 — $0.16/hr, 24GB', cost: 0.16 },
  { value: 'NVIDIA GeForce RTX 3090', label: 'RunPod: RTX 3090 — $0.22/hr, 24GB', cost: 0.22 },
  { value: 'NVIDIA GeForce RTX 4090', label: 'RunPod: RTX 4090 — $0.34/hr, 24GB', cost: 0.34 },
]

const DATASET_MODES = [
  { value: 'generate', label: 'AUTO-GENERATE', desc: 'Generate varied images using FLUX T2I from the character description' },
  { value: 'upload', label: 'UPLOAD', desc: 'Upload your own dataset (.zip or .tar.gz with images + captions)' },
]

export default function TrainingModal({ projectId, characters = [], locations = [], onCreated, onClose }) {
  const fileInputRef = useRef(null)

  const [form, setForm] = useState({
    character_id: '',
    location_id: '',
    subject_name: '',
    trigger_word: 'ohwx person',
    gpu_type: 'local',
    rank: 32,
    epochs: 150,
    learning_rate: '1e-4',
  })
  const [datasetMode, setDatasetMode] = useState('generate')
  const [datasetFile, setDatasetFile] = useState(null)
  const [numImages, setNumImages] = useState(25)
  const [subjectType, setSubjectType] = useState('character') // 'character' or 'location'
  const [locationId, setLocationId] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [datasetStatus, setDatasetStatus] = useState(null) // { generating, progress, total, done }

  const handleChange = (e) => {
    const { name, value } = e.target
    setForm((f) => {
      const updated = { ...f, [name]: value }
      if (name === 'character_id' && value) {
        const char = characters.find((c) => String(c.id) === String(value))
        if (char) updated.subject_name = char.name
      }
      if (name === 'location_id' && value) {
        const loc = locations.find((l) => String(l.id) === String(value))
        if (loc) {
          updated.subject_name = loc.name
          updated.trigger_word = 'sksstyle'
        }
      }
      return updated
    })
  }

  const handleFileDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer?.files?.[0] || e.target?.files?.[0]
    if (file && (file.name.endsWith('.zip') || file.name.endsWith('.tar.gz') || file.name.endsWith('.tgz'))) {
      setDatasetFile(file)
    } else if (file) {
      setError('Dataset must be a .zip or .tar.gz file.')
    }
  }

  // Poll dataset generation status
  useEffect(() => {
    if (!datasetStatus?.jobId || datasetStatus?.done) return
    const interval = setInterval(async () => {
      try {
        const status = await get(`/training/dataset-job/${datasetStatus.jobId}`)
        setDatasetStatus((prev) => ({
          ...prev,
          progress: status.generated,
          total: status.total,
          done: status.status === 'complete' || status.status === 'error',
          error: status.error,
          datasetPath: status.dataset_path,
          status: status.status,
        }))
      } catch {
        // ignore poll errors
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [datasetStatus?.jobId, datasetStatus?.done])

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (!form.subject_name.trim()) {
      setError('Subject name is required.')
      return
    }
    if (datasetMode === 'generate' && subjectType === 'character' && !form.character_id) {
      setError('Select a character to auto-generate a dataset from.')
      return
    }
    if (datasetMode === 'generate' && subjectType === 'location' && !locationId) {
      setError('Select a location to auto-generate a dataset from.')
      return
    }
    setError('')
    setCreating(true)
    try {
      const payload = {
        subject_name: form.subject_name.trim(),
        trigger_word: form.trigger_word.trim(),
        gpu_type: form.gpu_type,
        rank: Number(form.rank),
        epochs: Number(form.epochs),
        learning_rate: form.learning_rate.trim(),
      }
      if (subjectType === 'character' && form.character_id) {
        payload.character_id = Number(form.character_id)
      }
      if (subjectType === 'location' && (form.location_id || locationId)) {
        payload.location_id = Number(form.location_id || locationId)
      }

      // When auto-generating a dataset, defer training so it doesn't race
      // ahead and fail before the dataset exists.
      if (datasetMode === 'generate') {
        payload.defer_training = true
      }

      const job = await post(`/projects/${projectId}/training`, payload)

      if (datasetMode === 'upload' && datasetFile) {
        // Upload dataset file
        const formData = new FormData()
        formData.append('file', datasetFile)
        await post(`/training/${job.job_id}/upload-dataset`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        onCreated(job)
      } else if (datasetMode === 'generate') {
        // Start auto-generation
        const genPayload = {
          trigger_word: form.trigger_word.trim(),
          num_images: numImages,
        }
        if (subjectType === 'character') {
          genPayload.character_id = Number(form.character_id)
        } else {
          genPayload.location_id = Number(locationId)
        }

        const genResult = await post(`/training/${job.job_id}/generate-dataset`, genPayload)

        setDatasetStatus({
          jobId: genResult.dataset_job_id,
          generating: true,
          progress: 0,
          total: numImages,
          done: false,
          trainingJob: job,
        })
        setCreating(false)
        // Don't close — show progress
        return
      } else {
        onCreated(job)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create training job.')
    } finally {
      setCreating(false)
    }
  }

  // When dataset generation completes, kick off training then notify parent
  const handleDatasetDone = async () => {
    if (!datasetStatus?.trainingJob) return
    try {
      // Start the deferred training now that the dataset is ready
      if (!datasetStatus.error) {
        await post(`/training/${datasetStatus.trainingJob.job_id}/start-training`)
      }
    } catch {
      // Training start failed — job list will show the error
    }
    onCreated(datasetStatus.trainingJob)
  }

  // Fetch dataset preview images when generation is in progress or done
  const [previewImages, setPreviewImages] = useState([])
  const [selectedImage, setSelectedImage] = useState(null)

  useEffect(() => {
    if (!datasetStatus?.trainingJob?.job_id) return
    const fetchPreview = async () => {
      try {
        const data = await get(`/training/${datasetStatus.trainingJob.job_id}/dataset-preview`)
        if (data.images) setPreviewImages(data.images)
      } catch {
        // ignore
      }
    }
    fetchPreview()
    if (!datasetStatus.done) {
      const interval = setInterval(fetchPreview, 5000)
      return () => clearInterval(interval)
    }
  }, [datasetStatus?.trainingJob?.job_id, datasetStatus?.done, datasetStatus?.progress])

  // Show dataset generation progress screen with live gallery
  if (datasetStatus?.generating) {
    const pct = datasetStatus.total > 0
      ? Math.round((datasetStatus.progress / datasetStatus.total) * 100)
      : 0
    return (
      <div className="modal-overlay">
        <div className="modal-pixel max-w-3xl" style={{ maxHeight: '90vh' }}>
          <div className="modal-header">
            <span className="heading-pixel-sm text-accent-400">
              {datasetStatus.done ? 'DATASET READY' : 'GENERATING DATASET'}
            </span>
            <span className="text-retro text-zinc-500 text-xs">
              {datasetStatus.progress} / {datasetStatus.total}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
            {/* Progress bar */}
            <div className="w-full bg-zinc-700 h-3 border border-zinc-600">
              <div
                className={`h-full transition-all duration-500 ${
                  datasetStatus.error ? 'bg-red-500' : datasetStatus.done ? 'bg-px-green' : 'bg-accent-500'
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>

            {!datasetStatus.done && (
              <div className="flex items-center gap-2">
                <Loader className="w-4 h-4 text-accent-400 animate-spin" />
                <p className="text-retro text-zinc-400 text-xs">
                  Generating varied poses, angles, and lighting via FLUX T2I...
                </p>
              </div>
            )}

            {datasetStatus.error && (
              <div className="alert-error">{datasetStatus.error}</div>
            )}

            {/* Image gallery */}
            {previewImages.length > 0 && (
              <div>
                <p className="label-pixel mb-2">GENERATED IMAGES ({previewImages.length})</p>
                <div className="grid grid-cols-4 gap-2">
                  {previewImages.map((img, i) => (
                    <div
                      key={i}
                      className="relative group cursor-pointer border border-zinc-700 hover:border-accent-500 transition-colors bg-zinc-800"
                      onClick={() => setSelectedImage(img)}
                    >
                      <img
                        src={`http://localhost:8000${img.url}`}
                        alt={img.filename}
                        className="w-full aspect-[3/4] object-cover"
                        loading="lazy"
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-1 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <p className="text-retro text-zinc-300 text-xs truncate">{img.caption.slice(0, 60)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Full-size image viewer */}
            {selectedImage && (
              <div
                className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center cursor-pointer"
                onClick={() => setSelectedImage(null)}
              >
                <div className="max-w-2xl max-h-[80vh] relative" onClick={(e) => e.stopPropagation()}>
                  <img
                    src={`http://localhost:8000${selectedImage.url}`}
                    alt={selectedImage.filename}
                    className="max-w-full max-h-[70vh] object-contain"
                  />
                  <div className="mt-3 px-2">
                    <p className="text-retro text-zinc-300 text-sm">{selectedImage.caption}</p>
                    <p className="text-retro text-zinc-600 text-xs mt-1">{selectedImage.filename}</p>
                  </div>
                  <button
                    onClick={() => setSelectedImage(null)}
                    className="absolute top-2 right-2 text-zinc-400 hover:text-white text-lg"
                  >X</button>
                </div>
              </div>
            )}
          </div>

          <div className="modal-footer">
            {datasetStatus.done ? (
              <button onClick={handleDatasetDone} className="btn-pixel">
                {datasetStatus.error ? 'CLOSE' : 'DONE'}
              </button>
            ) : (
              <p className="text-retro text-zinc-500 text-xs">Please wait...</p>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal-pixel max-w-lg">

        {/* Header */}
        <div className="modal-header">
          <span className="heading-pixel-sm text-accent-400">+ NEW TRAINING JOB</span>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 font-pixel text-sm p-1">X</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {error && <div className="alert-error">{error}</div>}

          {/* Subject type toggle */}
          <div>
            <label className="label-pixel">TRAINING TARGET</label>
            <div className="flex gap-3 mb-3">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  value="character"
                  checked={subjectType === 'character'}
                  onChange={() => {
                    setSubjectType('character')
                    setForm((f) => ({ ...f, trigger_word: 'ohwx person', location_id: '', subject_name: '' }))
                    setLocationId('')
                  }}
                  className="accent-accent-500"
                />
                <span className="text-retro text-zinc-300 text-xs">CHARACTER</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  value="location"
                  checked={subjectType === 'location'}
                  onChange={() => {
                    setSubjectType('location')
                    setForm((f) => ({ ...f, trigger_word: 'sksstyle', character_id: '', subject_name: '' }))
                  }}
                  className="accent-accent-500"
                />
                <span className="text-retro text-zinc-300 text-xs">LOCATION / SCENE</span>
              </label>
            </div>
          </div>

          {/* Link to character or location */}
          {subjectType === 'character' && characters.length > 0 && (
            <div>
              <label className="label-pixel">LINK TO CHARACTER (OPTIONAL)</label>
              <select
                name="character_id"
                value={form.character_id}
                onChange={handleChange}
                className="input-pixel w-full"
              >
                <option value="">-- None --</option>
                {characters.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}
          {subjectType === 'location' && locations.length > 0 && (
            <div>
              <label className="label-pixel">LINK TO LOCATION *</label>
              <select
                name="location_id"
                value={form.location_id || locationId}
                onChange={(e) => {
                  handleChange(e)
                  setLocationId(e.target.value)
                }}
                className="input-pixel w-full"
              >
                <option value="">-- Select --</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Subject name */}
          <div>
            <label className="label-pixel">{subjectType === 'location' ? 'LOCATION NAME *' : 'CHARACTER NAME *'}</label>
            <input
              name="subject_name"
              value={form.subject_name}
              onChange={handleChange}
              className="input-pixel w-full"
              placeholder={subjectType === 'location' ? 'e.g. Rain-Soaked Alley' : 'e.g. Detective Noir'}
            />
          </div>

          {/* Trigger word */}
          <div>
            <label className="label-pixel">TRIGGER WORD</label>
            <input
              name="trigger_word"
              value={form.trigger_word}
              onChange={handleChange}
              className="input-pixel w-full"
              placeholder="ohwx person"
            />
            <p className="text-retro text-zinc-600 text-xs mt-1">
              A rare token the model learns to associate with this {subjectType === 'location' ? 'scene/location' : 'character'}
            </p>
          </div>

          {/* GPU type */}
          <div>
            <label className="label-pixel">GPU TYPE</label>
            <select
              name="gpu_type"
              value={form.gpu_type}
              onChange={handleChange}
              className="input-pixel w-full"
            >
              {GPU_OPTIONS.map((g) => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
          </div>

          {/* Rank + Epochs row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-pixel">RANK</label>
              <input
                name="rank"
                type="number"
                value={form.rank}
                onChange={handleChange}
                className="input-pixel w-full"
                min={4}
                max={128}
              />
            </div>
            <div>
              <label className="label-pixel">EPOCHS</label>
              <input
                name="epochs"
                type="number"
                value={form.epochs}
                onChange={handleChange}
                className="input-pixel w-full"
                min={10}
                max={500}
              />
            </div>
          </div>

          {/* Learning rate */}
          <div>
            <label className="label-pixel">LEARNING RATE</label>
            <input
              name="learning_rate"
              value={form.learning_rate}
              onChange={handleChange}
              className="input-pixel w-full"
              placeholder="1e-4"
            />
          </div>

          {/* Dataset mode toggle */}
          <div>
            <label className="label-pixel">TRAINING DATASET</label>
            <div className="grid grid-cols-2 gap-2 mb-3">
              {DATASET_MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setDatasetMode(m.value)}
                  className={`p-3 border-2 text-left transition-colors ${
                    datasetMode === m.value
                      ? 'border-accent-500 bg-accent-600/10'
                      : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'
                  }`}
                >
                  <div className="text-retro text-xs font-bold mb-1 flex items-center gap-1.5">
                    {m.value === 'generate' ? <Wand2 className="w-3 h-3" /> : <Upload className="w-3 h-3" />}
                    {m.label}
                  </div>
                  <p className="text-retro text-zinc-500 text-xs leading-tight">{m.desc}</p>
                </button>
              ))}
            </div>

            {datasetMode === 'generate' ? (
              <div className="space-y-3 pixel-panel p-4">
                {/* Subject type toggle */}
                <div className="flex gap-3">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="subjectType"
                      value="character"
                      checked={subjectType === 'character'}
                      onChange={() => setSubjectType('character')}
                      className="accent-accent-500"
                    />
                    <span className="text-retro text-zinc-300 text-xs">CHARACTER</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="subjectType"
                      value="location"
                      checked={subjectType === 'location'}
                      onChange={() => setSubjectType('location')}
                      className="accent-accent-500"
                    />
                    <span className="text-retro text-zinc-300 text-xs">LOCATION</span>
                  </label>
                </div>

                {subjectType === 'location' && locations.length > 0 && (
                  <div>
                    <label className="label-pixel text-xs">LOCATION</label>
                    <select
                      value={locationId}
                      onChange={(e) => setLocationId(e.target.value)}
                      className="input-pixel w-full"
                    >
                      <option value="">-- Select --</option>
                      {locations.map((l) => (
                        <option key={l.id} value={l.id}>{l.name}</option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label className="label-pixel text-xs">NUMBER OF IMAGES</label>
                  <input
                    type="number"
                    value={numImages}
                    onChange={(e) => setNumImages(Math.max(5, Math.min(50, Number(e.target.value))))}
                    className="input-pixel w-full"
                    min={5}
                    max={50}
                  />
                  <p className="text-retro text-zinc-600 text-xs mt-1">
                    Generates varied poses, angles, expressions and lighting via FLUX T2I (~5-10s each)
                  </p>
                </div>
              </div>
            ) : (
              <div
                className={`border-2 border-dashed rounded p-6 text-center cursor-pointer transition-colors ${
                  dragOver
                    ? 'border-accent-400 bg-accent-600/10'
                    : 'border-zinc-600 hover:border-zinc-500 bg-zinc-800/50'
                }`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleFileDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,.tar.gz,.tgz"
                  className="hidden"
                  onChange={handleFileDrop}
                />
                {datasetFile ? (
                  <div className="flex items-center justify-center gap-2">
                    <Upload className="w-4 h-4 text-px-green" />
                    <span className="text-retro text-px-green">{datasetFile.name}</span>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); setDatasetFile(null) }}
                      className="text-zinc-500 hover:text-px-red ml-2"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <div>
                    <Upload className="w-6 h-6 text-zinc-500 mx-auto mb-2" />
                    <p className="text-retro text-zinc-400">Drop .zip or .tar.gz here</p>
                    <p className="text-retro text-zinc-600 text-xs mt-1">Images + .txt captions per image</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="modal-footer">
          <button onClick={onClose} className="btn-pixel-ghost" disabled={creating}>
            CANCEL
          </button>
          <button onClick={handleSubmit} className="btn-pixel" disabled={creating}>
            {creating ? 'CREATING...' : datasetMode === 'generate' ? 'CREATE & GENERATE DATASET' : 'START TRAINING'}
          </button>
        </div>
      </div>
    </div>
  )
}
