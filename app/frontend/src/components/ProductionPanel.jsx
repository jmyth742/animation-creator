import React, { useEffect, useRef, useState } from 'react'
import { X, CheckCircle, AlertCircle, ChevronDown, ChevronUp, Copy } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { get } from '../api/client'

export default function ProductionPanel({ jobId, episodeTitle, onClose }) {
  const [progress, setProgress] = useState(0)
  const [log, setLog] = useState('')
  const [jobStatus, setJobStatus] = useState('running')
  const [finalPath, setFinalPath] = useState(null)
  const [wsError, setWsError] = useState(null)   // distinct from job error
  const [logExpanded, setLogExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  const logRef = useRef(null)
  const token = useAuthStore((s) => s.token)

  // Scroll log to bottom when new content arrives
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  // Expand log automatically when job errors so the failure is immediately visible
  useEffect(() => {
    if (jobStatus === 'error') setLogExpanded(true)
  }, [jobStatus])

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
      // Surface any detail message from the server (e.g. "Job not found.")
      if (data.detail) setWsError(data.detail)
    }

    ws.onerror = () => {
      // WS connection failed — fall back to REST polling so we don't cry wolf
      setWsError('Live connection lost — polling for status...')
      const poll = setInterval(async () => {
        try {
          const job = await get(`/jobs/${jobId}`)
          if (job.progress_pct !== undefined) setProgress(job.progress_pct)
          if (job.log_text) setLog(job.log_text)
          if (job.status) setJobStatus(job.status)
          if (job.status === 'complete' || job.status === 'error') {
            clearInterval(poll)
            setWsError(null)
          }
        } catch {
          // backend unreachable — keep trying
        }
      }, 3000)
    }

    return () => ws.close()
  }, [jobId, token])

  const isDone = jobStatus === 'complete' || jobStatus === 'error'
  const isError = jobStatus === 'error'

  // Extract the most relevant error line from the log for a summary
  const errorSummary = (() => {
    if (!isError || !log) return null
    const lines = log.split('\n').filter(Boolean)
    const errorLine = [...lines].reverse().find(
      (l) => l.includes('[ERROR]') || l.includes('[FATAL]') || l.includes('ERROR:') || l.includes('Exception') || l.includes('Error:')
    )
    return errorLine || lines[lines.length - 1] || null
  })()

  const handleCopyLog = () => {
    navigator.clipboard.writeText(log).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const barClass = jobStatus === 'complete' ? 'hp-bar-fill-green'
    : jobStatus === 'error' ? 'hp-bar-fill-red' : 'hp-bar-fill'

  return (
    <div className={`fixed bottom-0 left-0 right-0 z-50 bg-zinc-900 border-t-2 ${isError ? 'border-px-red' : 'border-accent-700'}`}
      style={{ boxShadow: '0 -4px 0 0 #000' }}>
      <div className="max-w-7xl mx-auto px-6 py-4">

        {/* Header row */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            {jobStatus === 'complete' ? <CheckCircle className="w-4 h-4 text-px-green shrink-0" />
              : jobStatus === 'error' ? <AlertCircle className="w-4 h-4 text-px-red shrink-0" />
              : <span className="pixel-spinner shrink-0" />}
            <div>
              <p className={`font-pixel ${isError ? 'text-px-red' : 'text-zinc-100'}`} style={{ fontSize: '8px' }}>
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
            {log && (
              <button
                onClick={() => setLogExpanded((v) => !v)}
                className="flex items-center gap-1 font-pixel text-zinc-500 hover:text-zinc-300 border border-zinc-700 px-2 py-1"
                style={{ fontSize: '6px' }}
              >
                {logExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
                {logExpanded ? 'HIDE LOG' : 'VIEW LOG'}
              </button>
            )}
            {isDone && (
              <button onClick={onClose} className="text-zinc-400 hover:text-zinc-200 p-1 font-pixel text-sm">✕</button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="hp-bar-track mb-3">
          <div className={`hp-bar-fill ${barClass}`} style={{ width: `${progress}%` }} />
        </div>
        <div className="flex justify-between items-center mb-2">
          <span className="font-pixel text-zinc-500" style={{ fontSize: '7px' }}>PROGRESS</span>
          <span className="font-pixel text-accent-400" style={{ fontSize: '8px' }}>{progress}%</span>
        </div>

        {/* WS connection warning (not a job error) */}
        {wsError && !isError && (
          <p className="text-retro text-amber-400 mb-2" style={{ fontSize: '13px' }}>⚠ {wsError}</p>
        )}

        {/* Error summary — shown prominently when job failed */}
        {isError && errorSummary && (
          <div className="bg-px-red/10 border border-px-red/40 px-3 py-2 mb-2">
            <p className="font-pixel text-px-red mb-0.5" style={{ fontSize: '6px' }}>ERROR DETAILS</p>
            <p className="text-retro text-px-red" style={{ fontSize: '14px' }}>{errorSummary}</p>
            {!logExpanded && (
              <button
                onClick={() => setLogExpanded(true)}
                className="text-retro text-zinc-500 hover:text-zinc-300 mt-1 underline"
                style={{ fontSize: '13px' }}
              >
                View full log →
              </button>
            )}
          </div>
        )}

        {/* Log panel */}
        {log && logExpanded && (
          <div className="relative">
            <div className="flex items-center justify-between mb-1">
              <span className="font-pixel text-zinc-600" style={{ fontSize: '6px' }}>PRODUCTION LOG (last 40 lines)</span>
              <button
                onClick={handleCopyLog}
                className="flex items-center gap-1 font-pixel text-zinc-500 hover:text-zinc-300"
                style={{ fontSize: '6px' }}
              >
                <Copy className="w-2.5 h-2.5" />
                {copied ? 'COPIED!' : 'COPY'}
              </button>
            </div>
            <pre
              ref={logRef}
              className="text-retro text-zinc-400 bg-zinc-950 border-2 border-zinc-700 p-3 overflow-y-auto whitespace-pre-wrap"
              style={{ fontSize: '13px', maxHeight: '240px' }}
            >
              {log}
            </pre>
          </div>
        )}

        {/* Compact log when not expanded and not error */}
        {log && !logExpanded && !isError && (
          <pre className="text-retro text-zinc-500 truncate" style={{ fontSize: '13px' }}>
            {log.split('\n').filter(Boolean).pop()}
          </pre>
        )}

      </div>
    </div>
  )
}
