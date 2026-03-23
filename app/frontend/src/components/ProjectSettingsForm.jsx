import React, { useState } from 'react'
import { Save, Wand2, AlertCircle, CheckCircle } from 'lucide-react'
import { put, post } from '../api/client'

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-zinc-300 mb-1">{label}</label>
      {hint && <p className="text-xs text-zinc-500 mb-1.5">{hint}</p>}
      {children}
    </div>
  )
}

export default function ProjectSettingsForm({ project, onUpdate }) {
  const [form, setForm] = useState({
    title: project.title,
    premise: project.premise,
    tone: project.tone,
    visual_style: project.visual_style,
    setting: project.setting,
  })
  const [numEpisodes, setNumEpisodes] = useState(5)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null) // { type: 'ok'|'error', text }
  const [genMsg, setGenMsg] = useState(null)

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const handleSave = async () => {
    setSaving(true)
    setSaveMsg(null)
    try {
      const updated = await put(`/projects/${project.id}`, form)
      onUpdate(updated)
      setSaveMsg({ type: 'ok', text: 'Changes saved.' })
    } catch (err) {
      console.error(err)
      setSaveMsg({ type: 'error', text: 'Save failed.' })
    } finally {
      setSaving(false)
    }
  }

  const handleGenerate = async () => {
    if (!window.confirm(
      `Generate ${numEpisodes} episode scripts using Claude AI?\n\nThis will create episode outlines and scene breakdowns based on your project details. Existing generated scripts will be replaced.`
    )) return

    setGenerating(true)
    setGenMsg(null)
    try {
      const result = await post(`/projects/${project.id}/generate-scripts`, {
        episodes: numEpisodes,
        force: true,
      })
      setGenMsg({ type: 'ok', text: result.message })
    } catch (err) {
      const detail = err.response?.data?.detail || 'Script generation failed.'
      setGenMsg({ type: 'error', text: detail })
    } finally {
      setGenerating(false)
    }
  }

  const inputClass =
    'w-full bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2.5 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 placeholder:text-zinc-600'
  const textareaClass = inputClass + ' resize-none'

  return (
    <div className="max-w-2xl space-y-8">
      {/* Project details */}
      <section>
        <h2 className="text-xl font-bold text-zinc-100 mb-6">Project Settings</h2>
        <div className="space-y-4">
          <Field label="Title">
            <input
              className={inputClass}
              value={form.title}
              onChange={setField('title')}
              placeholder="Series title"
            />
          </Field>

          <Field
            label="Premise"
            hint="2–3 sentences describing the core concept of your series."
          >
            <textarea
              className={textareaClass}
              rows={3}
              value={form.premise}
              onChange={setField('premise')}
              placeholder="What is this series about?"
            />
          </Field>

          <Field
            label="Tone"
            hint="e.g. dark comedy, heartfelt drama, whimsical adventure"
          >
            <input
              className={inputClass}
              value={form.tone}
              onChange={setField('tone')}
              placeholder="Series tone and mood"
            />
          </Field>

          <Field
            label="Visual Style"
            hint="e.g. anime, cyberpunk, watercolor, studio ghibli, photorealistic"
          >
            <input
              className={inputClass}
              value={form.visual_style}
              onChange={setField('visual_style')}
              placeholder="Art style for video generation"
            />
          </Field>

          <Field
            label="Setting"
            hint="Where and when the series takes place. Be descriptive — this helps generate better visuals."
          >
            <textarea
              className={textareaClass}
              rows={2}
              value={form.setting}
              onChange={setField('setting')}
              placeholder="Setting description"
            />
          </Field>
        </div>

        <div className="flex items-center gap-3 mt-6">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-100 font-medium rounded-xl px-4 py-2.5 text-sm transition-colors disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
          {saveMsg && (
            <span className={`flex items-center gap-1.5 text-sm ${saveMsg.type === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
              {saveMsg.type === 'ok' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
              {saveMsg.text}
            </span>
          )}
        </div>
      </section>

      {/* AI Script Generation */}
      <section className="border-t border-zinc-800 pt-8">
        <h3 className="text-lg font-bold text-zinc-100 mb-1">Generate Scripts with AI</h3>
        <p className="text-sm text-zinc-400 mb-5">
          Claude will write complete episode scripts — outlines, scene breakdowns, visuals, and dialogue — based on your project settings, characters, and locations.
        </p>

        <div className="flex items-center gap-4 mb-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-zinc-300 whitespace-nowrap">Number of episodes</label>
            <input
              type="number"
              min={1}
              max={20}
              value={numEpisodes}
              onChange={(e) => setNumEpisodes(Number(e.target.value))}
              className="w-20 bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 text-center"
            />
          </div>
        </div>

        <div className="bg-zinc-800/50 rounded-xl p-4 mb-5 border border-zinc-700">
          <p className="text-xs text-zinc-400 leading-relaxed">
            <span className="text-zinc-300 font-medium">What gets generated:</span> A series bible (characters, world, tone) and {numEpisodes} episode JSON files with full scene breakdowns, visual prompts, narration, and dialogue. These are imported directly into the Episodes tab.
          </p>
          <p className="text-xs text-zinc-500 mt-2">
            Requires a valid <code className="text-zinc-400">ANTHROPIC_API_KEY</code> in your environment. Generation takes ~30–90 seconds.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-5 py-2.5 text-sm transition-colors shadow-lg shadow-accent-900/30 disabled:opacity-50"
          >
            <Wand2 className="w-4 h-4" />
            {generating ? 'Generating scripts…' : 'Generate Scripts'}
          </button>
          {genMsg && (
            <span className={`flex items-center gap-1.5 text-sm ${genMsg.type === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
              {genMsg.type === 'ok' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
              {genMsg.text}
            </span>
          )}
        </div>
      </section>

      {/* Danger zone */}
      <section className="border-t border-zinc-800 pt-8">
        <h3 className="text-base font-semibold text-zinc-400 mb-1">Series Slug</h3>
        <p className="text-xs text-zinc-600 font-mono bg-zinc-900 rounded-lg px-3 py-2 inline-block">
          {project.series_slug}
        </p>
        <p className="text-xs text-zinc-600 mt-2">
          Used as the directory name for generated files. Set at creation time.
        </p>
      </section>
    </div>
  )
}
