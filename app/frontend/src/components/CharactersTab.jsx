import React, { useState } from 'react'
import { Plus } from 'lucide-react'
import CharacterCard from './CharacterCard'
import CharacterModal from './CharacterModal'
import PortraitStudioModal from './PortraitStudioModal'
import { del } from '../api/client'

export default function CharactersTab({ projectId, project = {}, characters, onCharactersChange }) {
  const [showModal, setShowModal] = useState(false)
  const [portraitStudio, setPortraitStudio] = useState(null) // character object or null
  const [deletingId, setDeletingId] = useState(null)

  const handleDelete = async (character) => {
    if (!window.confirm(`DELETE "${character.name}"? This cannot be undone.`)) return
    setDeletingId(character.id)
    try {
      await del(`/characters/${character.id}`)
      onCharactersChange()
    } catch {
      alert('Failed to delete character.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="heading-pixel text-zinc-100 mb-1">⚔ PARTY MEMBERS</h2>
          <p className="text-retro text-zinc-500">
            {characters.length} character{characters.length !== 1 ? 's' : ''} recruited
          </p>
        </div>
        <button onClick={() => setShowModal(null)} className="btn-pixel">
          <Plus className="w-3 h-3" />
          RECRUIT
        </button>
      </div>

      {characters.length === 0 ? (
        <div className="pixel-panel p-12 text-center">
          <div className="text-5xl mb-5">🧙</div>
          <h3 className="heading-pixel text-zinc-300 mb-3">PARTY IS EMPTY</h3>
          <p className="text-retro text-zinc-500 mb-6 max-w-xs mx-auto">
            Recruit characters to appear in your story. Each character has a unique voice and visual description.
          </p>
          <button onClick={() => setShowModal(null)} className="btn-pixel">
            <Plus className="w-3 h-3" />
            RECRUIT FIRST CHARACTER
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {characters.map((char) => (
            <CharacterCard
              key={char.id}
              character={char}
              deleting={deletingId === char.id}
              onEdit={() => setShowModal(char)}
              onDelete={() => handleDelete(char)}
              onOpenPortraitStudio={() => setPortraitStudio(char)}
            />
          ))}
        </div>
      )}

      {showModal !== false && (
        <CharacterModal
          projectId={projectId}
          character={showModal}
          projectContext={{
            series_title: project.title,
            visual_style: project.visual_style,
            tone: project.tone,
            setting: project.setting,
            premise: project.premise,
          }}
          onSave={() => { setShowModal(false); onCharactersChange() }}
          onClose={() => setShowModal(false)}
          onOpenPortraitStudio={(char) => { setShowModal(false); setPortraitStudio(char) }}
        />
      )}

      {portraitStudio && (
        <PortraitStudioModal
          character={portraitStudio}
          onClose={() => setPortraitStudio(null)}
          onPortraitSelected={(updated) => {
            setPortraitStudio(updated)
            onCharactersChange()
          }}
        />
      )}
    </div>
  )
}
