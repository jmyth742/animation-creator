import React, { useState } from 'react'
import { Plus, Users } from 'lucide-react'
import CharacterCard from './CharacterCard'
import CharacterModal from './CharacterModal'
import { del } from '../api/client'

export default function CharactersTab({ projectId, characters, onCharactersChange }) {
  // showModal: false | null (new) | character object (edit)
  const [showModal, setShowModal] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const handleEdit = (character) => {
    setShowModal(character)
  }

  const handleNew = () => {
    setShowModal(null)
  }

  const handleSave = () => {
    setShowModal(false)
    onCharactersChange()
  }

  const handleClose = () => {
    setShowModal(false)
  }

  const handleDelete = async (character) => {
    if (!window.confirm(`Delete character "${character.name}"? This cannot be undone.`)) return
    setDeletingId(character.id)
    try {
      await del(`/characters/${character.id}`)
      onCharactersChange()
    } catch (err) {
      console.error('Delete failed:', err)
      alert('Failed to delete character.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div>
      {/* Tab header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-zinc-100">Characters</h2>
          <p className="text-sm text-zinc-400 mt-0.5">
            {characters.length} character{characters.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={handleNew}
          className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-4 py-2.5 text-sm transition-colors shadow-lg shadow-accent-900/30"
        >
          <Plus className="w-4 h-4" />
          New Character
        </button>
      </div>

      {/* Grid */}
      {characters.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-52 text-center">
          <div className="w-16 h-16 bg-zinc-800 rounded-2xl flex items-center justify-center mb-4">
            <Users className="w-8 h-8 text-zinc-600" />
          </div>
          <h3 className="text-lg font-semibold text-zinc-300 mb-2">No characters yet</h3>
          <p className="text-zinc-500 text-sm max-w-xs mb-5">
            Add the characters that will appear in your series.
          </p>
          <button
            onClick={handleNew}
            className="flex items-center gap-2 bg-accent-600 hover:bg-accent-500 text-white font-medium rounded-xl px-4 py-2 text-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add first character
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">
          {characters.map((char) => (
            <CharacterCard
              key={char.id}
              character={char}
              deleting={deletingId === char.id}
              onEdit={() => handleEdit(char)}
              onDelete={() => handleDelete(char)}
            />
          ))}
        </div>
      )}

      {/* Modal */}
      {showModal !== false && (
        <CharacterModal
          projectId={projectId}
          character={showModal}
          onSave={handleSave}
          onClose={handleClose}
        />
      )}
    </div>
  )
}
