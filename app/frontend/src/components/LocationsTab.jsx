import React, { useState } from 'react'
import { Plus, MapPin, Pencil, Trash2, Check, X } from 'lucide-react'
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
    } catch (err) {
      console.error(err)
      alert('Failed to save location.')
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setName(location.name)
    setDescription(location.description)
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="bg-zinc-800 rounded-xl p-4 border border-accent-600">
        <div className="flex gap-3 mb-3">
          <input
            className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-accent-500"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Location name"
          />
          <button onClick={handleCancel} className="text-zinc-400 hover:text-zinc-200 p-1.5 rounded-lg hover:bg-zinc-700">
            <X className="w-4 h-4" />
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="text-white bg-accent-600 hover:bg-accent-500 p-1.5 rounded-lg disabled:opacity-50"
          >
            <Check className="w-4 h-4" />
          </button>
        </div>
        <textarea
          className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 resize-none"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Visual description for video generation…"
        />
      </div>
    )
  }

  return (
    <div className="bg-zinc-800/50 rounded-xl p-4 flex items-start gap-4 group hover:bg-zinc-800 transition-colors">
      <div className="w-10 h-10 bg-zinc-700 rounded-xl flex items-center justify-center shrink-0">
        <MapPin className="w-5 h-5 text-zinc-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-zinc-100 text-sm">{location.name}</p>
        {location.description && (
          <p className="text-xs text-zinc-400 mt-0.5 line-clamp-2">{location.description}</p>
        )}
        <p className="text-xs text-zinc-600 mt-1 font-mono">{location.slug}</p>
      </div>
      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
        <button
          onClick={() => setEditing(true)}
          className="text-zinc-400 hover:text-zinc-200 p-1.5 rounded-lg hover:bg-zinc-700"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => onDelete(location)}
          disabled={deleting}
          className="text-zinc-400 hover:text-red-400 p-1.5 rounded-lg hover:bg-zinc-700 disabled:opacity-50"
        >
          <Trash2 className="w-3.5 h-3.5" />
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
      setNewName('')
      setNewDesc('')
      setShowAdd(false)
      onLocationsChange()
    } catch (err) {
      console.error(err)
      alert('Failed to add location.')
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (location) => {
    if (!window.confirm(`Delete location "${location.name}"?`)) return
    setDeletingId(location.id)
    try {
      await del(`/locations/${location.id}`)
      onLocationsChange()
    } catch (err) {
      console.error(err)
      alert('Failed to delete location.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-zinc-100">Locations</h2>
          <p className="text-sm text-zinc-400 mt-0.5">
            {locations.length} location{locations.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-4 py-2.5 text-sm transition-colors shadow-lg shadow-accent-900/30"
        >
          <Plus className="w-4 h-4" />
          New Location
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="bg-zinc-800 rounded-xl p-4 border border-accent-600 mb-4">
          <p className="text-sm font-semibold text-zinc-200 mb-3">New Location</p>
          <input
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 mb-2"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Location name (e.g. Alleyway, Rooftop, Living room)"
            autoFocus
          />
          <textarea
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-accent-500 resize-none mb-3"
            rows={2}
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="Visual description for video generation…"
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => { setShowAdd(false); setNewName(''); setNewDesc('') }}
              className="px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200 rounded-lg hover:bg-zinc-700"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              disabled={!newName.trim() || adding}
              className="px-4 py-1.5 text-sm bg-accent-600 hover:bg-accent-500 text-white rounded-lg disabled:opacity-50"
            >
              {adding ? 'Adding…' : 'Add Location'}
            </button>
          </div>
        </div>
      )}

      {locations.length === 0 && !showAdd ? (
        <div className="flex flex-col items-center justify-center h-52 text-center">
          <div className="w-16 h-16 bg-zinc-800 rounded-2xl flex items-center justify-center mb-4">
            <MapPin className="w-8 h-8 text-zinc-600" />
          </div>
          <h3 className="text-lg font-semibold text-zinc-300 mb-2">No locations yet</h3>
          <p className="text-zinc-500 text-sm max-w-xs mb-5">
            Add locations where your scenes take place.
          </p>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-4 py-2 text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add first location
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {locations.map((loc) => (
            <LocationRow
              key={loc.id}
              location={loc}
              deleting={deletingId === loc.id}
              onEdit={onLocationsChange}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}
