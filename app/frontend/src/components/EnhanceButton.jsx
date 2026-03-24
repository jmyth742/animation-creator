import React, { useState } from 'react'
import { Sparkles, X, Check } from 'lucide-react'
import { post } from '../api/client'

/**
 * EnhanceButton — shows a ✨ button next to a field label.
 * When clicked, calls POST /enhance and shows 3 AI suggestions inline.
 *
 * Props:
 *   fieldType   — string key (visual_style, tone, character_visual, etc.)
 *   currentText — current value of the field
 *   context     — object with series context (series_title, visual_style, tone, etc.)
 *   onSelect    — callback(text) when user picks a suggestion
 */
export default function EnhanceButton({ fieldType, currentText, context = {}, onSelect }) {
  const [state, setState] = useState('idle') // idle | loading | done | error
  const [suggestions, setSuggestions] = useState([])
  const [picked, setPicked] = useState(null)
  const [error, setError] = useState('')

  const handleEnhance = async () => {
    setState('loading')
    setError('')
    setSuggestions([])
    setPicked(null)
    try {
      const data = await post('/enhance', {
        field_type: fieldType,
        current_text: currentText || '',
        context,
      })
      setSuggestions(data.suggestions)
      setState('done')
    } catch (err) {
      setError(err.response?.data?.detail || 'Enhancement failed.')
      setState('error')
    }
  }

  const handlePick = (text) => {
    setPicked(text)
    onSelect(text)
  }

  const handleDismiss = () => {
    setState('idle')
    setSuggestions([])
    setPicked(null)
    setError('')
  }

  return (
    <div>
      {/* Trigger button */}
      <button
        type="button"
        onClick={state === 'idle' || state === 'error' ? handleEnhance : handleDismiss}
        disabled={state === 'loading'}
        className={`flex items-center gap-1 font-pixel border transition-colors ${
          state === 'done'
            ? 'border-accent-600 text-accent-400 bg-accent-950 hover:border-zinc-600 hover:text-zinc-400'
            : 'border-zinc-700 text-zinc-500 hover:border-accent-600 hover:text-accent-400'
        }`}
        style={{ fontSize: '6px', padding: '2px 6px', lineHeight: '1.8' }}
        title={state === 'done' ? 'Dismiss suggestions' : 'Get AI suggestions'}
      >
        {state === 'loading' ? (
          <span className="pixel-spinner" style={{ width: '8px', height: '8px' }} />
        ) : (
          <Sparkles className="w-2 h-2" />
        )}
        {state === 'loading' ? 'THINKING...' : state === 'done' ? '✨ SUGGESTIONS' : '✨ ENHANCE'}
      </button>

      {/* Suggestions panel */}
      {state === 'done' && suggestions.length > 0 && (
        <div className="mt-2 space-y-1.5 border border-accent-800 bg-zinc-950 p-2">
          <div className="flex items-center justify-between mb-2">
            <span className="font-pixel text-accent-500" style={{ fontSize: '5px' }}>
              AI SUGGESTIONS — CLICK TO APPLY
            </span>
            <button
              type="button"
              onClick={handleDismiss}
              className="text-zinc-600 hover:text-zinc-400"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
          {suggestions.map((s, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handlePick(s)}
              className={`w-full text-left p-2 border transition-colors ${
                picked === s
                  ? 'border-px-green bg-px-green/10 text-zinc-200'
                  : 'border-zinc-800 hover:border-accent-600 hover:bg-accent-950/40 text-zinc-400'
              }`}
            >
              <div className="flex items-start gap-2">
                <span className="font-pixel text-zinc-600 flex-shrink-0" style={{ fontSize: '5px', marginTop: '2px' }}>
                  {picked === s ? <Check className="w-2 h-2 text-px-green inline" /> : `0${i + 1}`}
                </span>
                <span className="text-retro flex-1" style={{ fontSize: '14px', lineHeight: '1.5' }}>
                  {s}
                </span>
              </div>
            </button>
          ))}
          <p className="text-retro text-zinc-700 mt-1" style={{ fontSize: '12px' }}>
            Clicking a suggestion replaces the field value. You can edit it further.
          </p>
        </div>
      )}

      {state === 'error' && (
        <p className="text-retro text-px-red mt-1" style={{ fontSize: '13px' }}>✖ {error}</p>
      )}
    </div>
  )
}
