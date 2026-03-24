import React, { useEffect, useRef, useState } from 'react'
import { X, CheckCircle, AlertCircle } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

export default function ProductionPanel({ jobId, episodeTitle, onClose }) {
  const [progress, setProgress] = useState(0)
  const [log, setLog] = useState('')
  const [jobStatus, setJobStatus] = useState('running')
  const [finalPath, setFinalPath] = useState(null)
  const logRef = useRef(null)
  const token = useAuthStore((s) => s.token)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${proto}://${window.location.host}/ws/${jobId}?token=${encodeURIComponent(token ?? '')}`
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.progress !== undefined) setProgress(data.progress)
      if (data.log) setLog(data.log)
      if (data.status) setJobStatus(data.status)
      if (data.final_path) setFinalPath(data.final_path)
    }
    ws.onerror = () => setJobStatus('error')
    return () => ws.close()
  }, [jobId])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  const isDone = jobStatus === 'complete' || jobStatus === 'error'

  const barClass = jobStatus === 'complete' ? 'hp-bar-fill-green'
    : jobStatus === 'error' ? 'hp-bar-fill-red' : 'hp-bar-fill'

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-900 border-t-2 border-accent-700"
      style={{ boxShadow: '0 -4px 0 0 #000' }}>
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            {jobStatus === 'complete' ? <CheckCircle className="w-4 h-4 text-px-green shrink-0" />
              : jobStatus === 'error' ? <AlertCircle className="w-4 h-4 text-px-red shrink-0" />
              : <span className="pixel-spinner shrink-0" />}
            <div>
              <p className="font-pixel text-zinc-100" style={{ fontSize: '8px' }}>
                {jobStatus === 'complete' ? '✔ PRODUCTION COMPLETE'
                  : jobStatus === 'error' ? '✖ PRODUCTION FAILED'
                  : '▶▶ PRODUCING...'}
              </p>
              <p className="text-retro text-zinc-500" style={{ fontSize: '15px' }}>{episodeTitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {finalPath && (
              <a href={finalPath} target="_blank" rel="noopener noreferrer" className="btn-pixel-sm">
                ▶ WATCH
              </a>
            )}
            {isDone && (
              <button onClick={onClose} className="text-zinc-400 hover:text-zinc-200 p-1 font-pixel text-sm">✕</button>
            )}
          </div>
        </div>

        {/* HP bar */}
        <div className="hp-bar-track mb-3">
          <div className={`hp-bar-fill ${barClass}`} style={{ width: `${progress}%` }} />
        </div>
        <div className="flex justify-between items-center mb-2">
          <span className="font-pixel text-zinc-500" style={{ fontSize: '7px' }}>PROGRESS</span>
          <span className="font-pixel text-accent-400" style={{ fontSize: '8px' }}>{progress}%</span>
        </div>

        {log && (
          <pre ref={logRef}
            className="text-retro text-zinc-400 bg-zinc-950 border-2 border-zinc-700 p-3 max-h-24 overflow-y-auto whitespace-pre-wrap"
            style={{ fontSize: '14px' }}>
            {log}
          </pre>
        )}
      </div>
    </div>
  )
}
