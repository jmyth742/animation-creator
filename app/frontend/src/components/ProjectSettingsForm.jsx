import React, { useState } from 'react'
import { Save, Wand2 } from 'lucide-react'
import { put, post } from '../api/client'
import EnhanceButton from './EnhanceButton'

function Field({ label, hint, enhance, children }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-0.5">
        <label className="label-pixel">{label}</label>
        {enhance}
      </div>
      {hint && <p className="text-retro text-zinc-500 mb-1" style={{ fontSize: '15px' }}>{hint}</p>}
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
  const [saveMsg, setSaveMsg] = useState(null)
  const [genMsg, setGenMsg] = useState(null)

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const handleSave = async () => {
    setSaving(true); setSaveMsg(null)
    try {
      const updated = await put(`/projects/${project.id}`, form)
      onUpdate(updated)
      setSaveMsg({ type: 'ok', text: 'CHANGES SAVED.' })
    } catch {
      setSaveMsg({ type: 'error', text: 'SAVE FAILED.' })
    } finally { setSaving(false) }
  }

  const handleGenerate = async () => {
    if (!window.confirm(
      `GENERATE ${numEpisodes} EPISODE SCRIPTS USING CLAUDE AI?\n\nThis will create episode outlines and scene breakdowns. Existing generated scripts will be replaced.`
    )) return
    setGenerating(true); setGenMsg(null)
    try {
      const result = await post(`/projects/${project.id}/generate-scripts`, { episodes: numEpisodes, force: true })
      setGenMsg({ type: 'ok', text: result.message })
    } catch (err) {
      setGenMsg({ type: 'error', text: err.response?.data?.detail || 'Script generation failed.' })
    } finally { setGenerating(false) }
  }

  return (
    <div className="max-w-2xl space-y-8">
      <section>
        <h2 className="heading-pixel text-zinc-100 mb-6">⚙ PROJECT SETTINGS</h2>
        <div className="space-y-4">
          <Field label="TITLE">
            <input className="input-pixel" value={form.title} onChange={setField('title')} placeholder="Series title" />
          </Field>
          <Field
            label="PREMISE"
            hint="2-3 sentences describing the core concept."
            enhance={
              <EnhanceButton
                fieldType="premise"
                currentText={form.premise}
                context={{ series_title: form.title, tone: form.tone, setting: form.setting }}
                onSelect={(v) => setForm((f) => ({ ...f, premise: v }))}
              />
            }
          >
            <textarea className="input-pixel resize-none" rows={3} value={form.premise} onChange={setField('premise')} placeholder="What is this series about?" />
          </Field>
          <Field
            label="TONE"
            hint="e.g. dark comedy, heartfelt drama, whimsical adventure"
            enhance={
              <EnhanceButton
                fieldType="tone"
                currentText={form.tone}
                context={{ series_title: form.title, premise: form.premise }}
                onSelect={(v) => setForm((f) => ({ ...f, tone: v }))}
              />
            }
          >
            <input className="input-pixel" value={form.tone} onChange={setField('tone')} placeholder="Series tone and mood" />
          </Field>
          <Field
            label="VISUAL STYLE"
            hint="e.g. anime, cyberpunk, watercolor, studio ghibli"
            enhance={
              <EnhanceButton
                fieldType="visual_style"
                currentText={form.visual_style}
                context={{ series_title: form.title, tone: form.tone, setting: form.setting }}
                onSelect={(v) => setForm((f) => ({ ...f, visual_style: v }))}
              />
            }
          >
            <input className="input-pixel" value={form.visual_style} onChange={setField('visual_style')} placeholder="Art style for video generation" />
          </Field>
          <Field
            label="SETTING"
            hint="Where and when the series takes place."
            enhance={
              <EnhanceButton
                fieldType="setting"
                currentText={form.setting}
                context={{ series_title: form.title, premise: form.premise, tone: form.tone }}
                onSelect={(v) => setForm((f) => ({ ...f, setting: v }))}
              />
            }
          >
            <textarea className="input-pixel resize-none" rows={2} value={form.setting} onChange={setField('setting')} placeholder="Setting description" />
          </Field>
        </div>
        <div className="flex items-center gap-4 mt-6">
          <button onClick={handleSave} disabled={saving} className="btn-pixel-ghost">
            <Save className="w-3 h-3" />
            {saving ? 'SAVING...' : 'SAVE CHANGES'}
          </button>
          {saveMsg && (
            <span className={`text-retro font-bold ${saveMsg.type === 'ok' ? 'text-px-green' : 'text-px-red'}`}
              style={{ fontSize: '16px' }}>
              {saveMsg.type === 'ok' ? '✔' : '✖'} {saveMsg.text}
            </span>
          )}
        </div>
      </section>

      <hr className="divider-pixel" />

      <section>
        <h3 className="heading-pixel-sm text-accent-400 mb-2">🤖 AI SCRIPT GENERATOR</h3>
        <p className="text-retro text-zinc-400 mb-5" style={{ fontSize: '17px' }}>
          Claude will write complete episode scripts — scene breakdowns, visual prompts, narration, and dialogue — based on your project settings, characters, and locations.
        </p>

        <div className="pixel-panel-sm p-4 mb-5">
          <p className="text-retro text-zinc-400 mb-1" style={{ fontSize: '16px' }}>
            <span className="text-zinc-200">GENERATES:</span> A series bible + episode JSON files with full scene breakdowns imported directly into the Quest Log.
          </p>
          <p className="text-retro text-zinc-500" style={{ fontSize: '15px' }}>
            Requires ANTHROPIC_API_KEY in environment. Takes ~30-90 seconds.
          </p>
        </div>

        <div className="flex items-center gap-4 mb-4">
          <label className="label-pixel whitespace-nowrap">EPISODES TO GENERATE</label>
          <input
            type="number" min={1} max={20} value={numEpisodes}
            onChange={(e) => setNumEpisodes(Number(e.target.value))}
            className="input-pixel w-20 text-center"
          />
        </div>

        <div className="flex items-center gap-4">
          <button onClick={handleGenerate} disabled={generating} className="btn-pixel">
            <Wand2 className="w-3 h-3" />
            {generating ? '▶▶ GENERATING SCRIPTS...' : '✨ GENERATE SCRIPTS'}
          </button>
          {genMsg && (
            <span className={`text-retro ${genMsg.type === 'ok' ? 'text-px-green' : 'text-px-red'}`}
              style={{ fontSize: '16px' }}>
              {genMsg.type === 'ok' ? '✔' : '✖'} {genMsg.text}
            </span>
          )}
        </div>
      </section>

      <hr className="divider-pixel" />

      <section>
        <h3 className="heading-pixel-sm text-zinc-600 mb-2">SERIES SLUG</h3>
        <code className="font-mono text-zinc-500 bg-zinc-900 border border-zinc-700 px-3 py-1.5 text-sm">
          {project.series_slug}
        </code>
        <p className="text-retro text-zinc-600 mt-2" style={{ fontSize: '15px' }}>
          Used as directory name for generated files. Set at creation.
        </p>
      </section>
    </div>
  )
}
