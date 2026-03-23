import React, { useState } from 'react'
import { Plus, Pencil, Trash2, Check, X } from 'lucide-react'
import { post, put, del } from '../api/client'

function LocationRow({ location, onEdit, onDelete, deleting }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(location.name)
  const [description, setDescription] = useState(location.description)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await put(`/locations/${location.id}`, { name, description })
      setEditing(false)
      onEdit()
    } catch { alert('Failed to save location.') }
    finally { setSaving(false) }
  }

  if (editing) {
    return (
      <div className="bg-zinc-800 border-2 border-accent-600 p-4" style={{ boxShadow: '3px 3px 0 0 #6d28d9' }}>
        <div className="flex gap-2 mb-2">
          <input className="input-pixel flex-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="Location name" />
          <button onClick={() => { setName(location.name); setDescription(location.description); setEditing(false) }} className="btn-pixel-ghost px-2"><X className="w-3 h-3" /></button>
          <button onClick={handleSave} disabled={saving} className="btn-pixel px-2"><Check className="w-3 h-3" /></button>
        </div>
        <textarea className="input-pixel resize-none w-full" rows={2} value={description}
          onChange={(e) => setDescription(e.target.value)} placeholder="Visual description for video generation..." />
      </div>
    )
  }

  return (
    <div className="bg-zinc-800 border-2 border-zinc-700 p-4 flex items-start gap-4 group hover:border-zinc-600 transition-colors"
      style={{ boxShadow: '3px 3px 0 0 #000' }}>
      <div className="text-xl shrink-0 mt-1">📍</div>
      <div className="flex-1 min-w-0">
        <p className="font-pixel text-zinc-100 mb-1" style={{ fontSize: '9px' }}>{location.name}</p>
        {location.description && (
          <p className="text-retro text-zinc-400 line-clamp-2" style={{ fontSize: '16px' }}>{location.description}</p>
        )}
        <p className="font-mono text-zinc-600 text-xs mt-1">{location.slug}</p>
      </div>
      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
        <button onClick={() => setEditing(true)} className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-accent-400 hover:border-accent-600">
          <Pencil className="w-3 h-3" />
        </button>
        <button onClick={() => onDelete(location)} disabled={deleting} className="p-1.5 border border-zinc-600 text-zinc-400 hover:text-px-red hover:border-px-red disabled:opacity-50">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  )
}

export default function LocationsTab({ projectId, locations, onLocationsChange }) {
  const [showAdd, setShowAdd] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [adding, setAdding] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const handleAdd = async () => {
    if (!newName.trim()) return
    setAdding(true)
    try {
      await post(`/projects/${projectId}/locations`, { name: newName.trim(), description: newDesc.trim() })
      setNewName(''); setNewDesc(''); setShowAdd(false)
      onLocationsChange()
    } catch { alert('Failed to add location.') }
    finally { setAdding(false) }
  }

  const handleDelete = async (location) => {
    if (!window.confirm(`DELETE location "${location.name}"?`)) return
    setDeletingId(location.id)
    try { await del(`/locations/${location.id}`); onLocationsChange() }
    catch { alert('Failed to delete location.') }
    finally { setDeletingId(null) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="heading-pixel text-zinc-100 mb-1">🗺 WORLD MAP</h2>
          <p className="text-retro text-zinc-500">{locations.length} location{locations.length !== 1 ? 's' : ''} discovered</p>
        </div>
        <button onClick={() => setShowAdd(true)} className="btn-pixel"><Plus className="w-3 h-3" />ADD LOCATION</button>
      </div>

      {showAdd && (
        <div className="pixel-panel-accent p-4 mb-4">
          <div className="label-pixel mb-3">NEW LOCATION</div>
          <input className="input-pixel w-full mb-2" value={newName} onChange={(e) => setNewName(e.target.value)}
            placeholder="Location name (e.g. Alleyway, Rooftop)" autoFocus />
          <textarea className="input-pixel w-full resize-none mb-3" rows={2} value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)} placeholder="Visual description for video generation..." />
          <div className="flex gap-2 justify-end">
            <button onClick={() => { setShowAdd(false); setNewName(''); setNewDesc('') }} className="btn-pixel-ghost">CANCEL</button>
            <button onClick={handleAdd} disabled={!newName.trim() || adding} className="btn-pixel">{adding ? 'ADDING...' : '+ ADD'}</button>
          </div>
        </div>
      )}

      {locations.length === 0 && !showAdd ? (
        <div className="pixel-panel p-12 text-center">
          <div className="text-5xl mb-5">🗺</div>
          <h3 className="heading-pixel text-zinc-300 mb-3">MAP IS EMPTY</h3>
          <p className="text-retro text-zinc-500 mb-6 max-w-xs mx-auto">Add filming locations where your scenes take place.</p>
          <button onClick={() => setShowAdd(true)} className="btn-pixel"><Plus className="w-3 h-3" />ADD FIRST LOCATION</button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {locations.map((loc) => (
            <LocationRow key={loc.id} location={loc} deleting={deletingId === loc.id} onEdit={onLocationsChange} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}
