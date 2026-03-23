import React, { useEffect, useRef, useState } from 'react'
import { X, CheckCircle, AlertCircle, Loader } from 'lucide-react'

export default function ProductionPanel({ jobId, episodeTitle, onClose }) {
  const [progress, setProgress] = useState(0)
  const [log, setLog] = useState('')
  const [jobStatus, setJobStatus] = useState('running')
  const [finalPath, setFinalPath] = useState(null)
  const logRef = useRef(null)
  const wsRef = useRef(null)

  useEffect(() => {
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/${jobId}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

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

  // Auto-scroll log to bottom
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [log])

  const isDone = jobStatus === 'complete' || jobStatus === 'error'

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-zinc-900 border-t border-zinc-700 shadow-2xl">
      <div className="max-w-7xl mx-auto px-6 py-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            {jobStatus === 'complete' ? (
              <CheckCircle className="w-5 h-5 text-green-400 shrink-0" />
            ) : jobStatus === 'error' ? (
              <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
            ) : (
              <Loader className="w-5 h-5 text-accent-400 animate-spin shrink-0" />
            )}
            <div>
              <p className="text-sm font-semibold text-zinc-100">
                {jobStatus === 'complete'
                  ? 'Production complete'
                  : jobStatus === 'error'
                  ? 'Production failed'
                  : 'Producing episode…'}
              </p>
              <p className="text-xs text-zinc-400">{episodeTitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {finalPath && (
              <a
                href={finalPath}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent-400 hover:text-accent-300 font-medium"
              >
                Watch video
              </a>
            )}
            {isDone && (
              <button
                onClick={onClose}
                className="text-zinc-400 hover:text-zinc-200 p-1 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-1.5 bg-zinc-800 rounded-full mb-3 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              jobStatus === 'complete'
                ? 'bg-green-500'
                : jobStatus === 'error'
                ? 'bg-red-500'
                : 'bg-accent-500'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Log output */}
        {log && (
          <pre
            ref={logRef}
            className="text-xs text-zinc-400 font-mono bg-zinc-950 rounded-lg p-3 max-h-28 overflow-y-auto whitespace-pre-wrap"
          >
            {log}
          </pre>
        )}
      </div>
    </div>
  )
}
