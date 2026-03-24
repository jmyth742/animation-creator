import React from 'react'
import { Pencil, Star, Trash2 } from 'lucide-react'

function getInitials(name = '') {
  return name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()
}

const VOICE_LABELS = {
  'en-GB-RyanNeural':    'RYAN-GB',
  'en-GB-ThomasNeural':  'THOMAS-GB',
  'en-GB-SoniaNeural':   'SONIA-GB',
  'en-GB-LibbyNeural':   'LIBBY-GB',
  'en-US-GuyNeural':     'GUY-US',
  'en-US-JennyNeural':   'JENNY-US',
  'en-AU-NatashaNeural': 'NATASHA-AU',
}

export default function CharacterCard({ character, onEdit, onDelete, deleting }) {
  return (
    <div
      className="group relative bg-zinc-800 border-2 border-zinc-700 flex flex-col overflow-hidden"
      style={{ boxShadow: '3px 3px 0 0 #000' }}
    >
      {/* Portrait */}
      <div className="relative w-full aspect-square bg-zinc-700 flex-shrink-0 border-b-2 border-zinc-700">
        {character.portrait_url ? (
          <img
            src={character.portrait_url}
            alt={character.name}
            className="w-full h-full object-cover"
            style={{ imageRendering: 'pixelated' }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #1c1c38 0%, #2a2a50 100%)' }}>
            <span className="font-pixel text-accent-400 select-none"
              style={{ fontSize: '20px', textShadow: '2px 2px 0 #000' }}>
              {getInitials(character.name)}
            </span>
          </div>
        )}

        {/* Canonical portrait badge */}
        {character.reference_image_path && (
          <div className="absolute top-1 right-1 bg-black/70 border border-px-green p-0.5"
            title="Canonical portrait set — used for visual consistency in video generation">
            <Star className="w-2.5 h-2.5 text-px-green fill-current" />
          </div>
        )}

        {/* Action overlay */}
        <div className="absolute inset-0 bg-black/70 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
          <button
            onClick={onEdit}
            className="p-2 bg-zinc-900 border-2 border-accent-600 text-accent-400 hover:bg-accent-800 transition-colors"
            style={{ boxShadow: '2px 2px 0 0 #000' }}
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onDelete}
            disabled={deleting}
            className="p-2 bg-zinc-900 border-2 border-px-red text-px-red hover:bg-red-900 transition-colors disabled:opacity-50"
            style={{ boxShadow: '2px 2px 0 0 #000' }}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Info */}
      <div className="p-3 flex flex-col gap-1.5 flex-1">
        <h4 className="font-pixel text-zinc-100 truncate" style={{ fontSize: '8px', textShadow: '1px 1px 0 #000' }}>
          {character.name}
        </h4>
        {character.role && (
          <span className="badge-pixel-accent truncate max-w-full">{character.role}</span>
        )}
        {character.voice && (
          <span className="badge-pixel truncate max-w-full">
            🔊 {VOICE_LABELS[character.voice] || character.voice}
          </span>
        )}
      </div>
    </div>
  )
}
