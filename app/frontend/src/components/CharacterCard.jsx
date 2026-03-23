import React from 'react'
import { Pencil, Trash2 } from 'lucide-react'

function getInitials(name = '') {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

const VOICE_LABELS = {
  'en-GB-RyanNeural': 'Ryan (GB)',
  'en-GB-ThomasNeural': 'Thomas (GB)',
  'en-GB-SoniaNeural': 'Sonia (GB)',
  'en-GB-LibbyNeural': 'Libby (GB)',
  'en-US-GuyNeural': 'Guy (US)',
  'en-US-JennyNeural': 'Jenny (US)',
  'en-AU-NatashaNeural': 'Natasha (AU)',
}

export default function CharacterCard({ character, onEdit, onDelete, deleting }) {
  const initials = getInitials(character.name)

  return (
    <div className="group relative bg-zinc-800 hover:bg-zinc-750 border border-zinc-700/50 hover:border-zinc-600 rounded-xl overflow-hidden transition-all duration-150 flex flex-col">
      {/* Portrait */}
      <div className="relative w-full aspect-square bg-zinc-700 flex-shrink-0">
        {character.portrait_url ? (
          <img
            src={character.portrait_url}
            alt={character.name}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-zinc-700">
            <span className="text-3xl font-bold text-zinc-400 select-none">
              {initials}
            </span>
          </div>
        )}

        {/* Action buttons overlay */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
          <button
            onClick={onEdit}
            title="Edit"
            className="p-2 bg-zinc-800/90 hover:bg-zinc-700 rounded-lg text-zinc-200 transition-colors"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            onClick={onDelete}
            disabled={deleting}
            title="Delete"
            className="p-2 bg-zinc-800/90 hover:bg-red-900 rounded-lg text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Info */}
      <div className="p-3 flex flex-col gap-1.5 flex-1">
        <h4 className="text-sm font-semibold text-zinc-100 leading-tight truncate">
          {character.name}
        </h4>

        {character.role && (
          <span className="inline-block px-2 py-0.5 bg-accent-950/70 border border-accent-800/50 text-accent-300 text-xs rounded-full truncate max-w-full">
            {character.role}
          </span>
        )}

        {character.voice && (
          <span className="inline-block px-2 py-0.5 bg-zinc-700 text-zinc-400 text-xs rounded-full truncate max-w-full">
            {VOICE_LABELS[character.voice] || character.voice}
          </span>
        )}
      </div>
    </div>
  )
}
