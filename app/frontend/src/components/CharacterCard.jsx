import React, { useState, useRef, useCallback } from 'react'
import { Camera, Pencil, Star, Trash2 } from 'lucide-react'
import { put } from '../api/client'

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

function getLoraFilename(path) {
  if (!path) return ''
  return path.split('/').pop().split('\\').pop().replace(/\.[^.]+$/, '')
}

export default function CharacterCard({ character, onEdit, onDelete, onOpenPortraitStudio, deleting }) {
  const [strength, setStrength] = useState(character.lora_strength ?? 0.7)
  const debounceRef = useRef(null)

  const handleStrengthChange = useCallback((e) => {
    const val = parseFloat(e.target.value)
    setStrength(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      put(`/characters/${character.id}`, { lora_strength: val }).catch(() => {})
    }, 400)
  }, [character.id])

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
          <div className="w-full h-full flex flex-col items-center justify-center gap-2 cursor-pointer"
            style={{ background: 'linear-gradient(135deg, #1c1c38 0%, #2a2a50 100%)' }}
            onClick={onOpenPortraitStudio}
            title="Open Portrait Studio">
            <span className="font-pixel text-accent-400 select-none"
              style={{ fontSize: '20px', textShadow: '2px 2px 0 #000' }}>
              {getInitials(character.name)}
            </span>
            <span className="font-pixel text-zinc-500 flex items-center gap-1" style={{ fontSize: '6px' }}>
              <Camera className="w-2.5 h-2.5" /> ADD PORTRAIT
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
        <div className="absolute inset-0 bg-black/70 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
          <button
            onClick={onOpenPortraitStudio}
            className="p-2 bg-zinc-900 border-2 border-px-green text-px-green hover:bg-green-900 transition-colors"
            style={{ boxShadow: '2px 2px 0 0 #000' }}
            title="Portrait Studio"
          >
            <Camera className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onEdit}
            className="p-2 bg-zinc-900 border-2 border-accent-600 text-accent-400 hover:bg-accent-800 transition-colors"
            style={{ boxShadow: '2px 2px 0 0 #000' }}
            title="Edit character"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onDelete}
            disabled={deleting}
            className="p-2 bg-zinc-900 border-2 border-px-red text-px-red hover:bg-red-900 transition-colors disabled:opacity-50"
            style={{ boxShadow: '2px 2px 0 0 #000' }}
            title="Delete character"
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

      {/* LoRA strength slider */}
      {character.lora_path && (
        <div className="px-3 pb-3 flex flex-col gap-1">
          <span className="label-pixel text-zinc-500 truncate" style={{ fontSize: '6px' }}
            title={character.lora_path}>
            LoRA: {getLoraFilename(character.lora_path)}
          </span>
          {character.trigger_word && (
            <span className="font-pixel text-accent-400 truncate" style={{ fontSize: '6px' }}
              title={`Trigger: ${character.trigger_word}`}>
              TRIGGER: {character.trigger_word}
            </span>
          )}
          <div className="flex items-center gap-1.5">
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={strength}
              onChange={handleStrengthChange}
              className="input-pixel flex-1 h-1.5 accent-accent-600 cursor-pointer"
              style={{ accentColor: 'var(--accent-600, #7c3aed)' }}
              title={`LoRA strength: ${strength.toFixed(2)}`}
            />
            <span className="font-pixel text-zinc-100 min-w-[2rem] text-right" style={{ fontSize: '7px' }}>
              {strength.toFixed(2)}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
