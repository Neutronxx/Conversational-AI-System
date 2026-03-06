import { useState, useEffect, useRef } from 'react'
import './App.css'

// WebSocket URL: use VITE_WS_URL if set, else same host as the page on port 8000
function getWsUrl() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${host}:8000/ws/chat`
}
const SESSION_STORAGE_KEY = 'uniguide_session_id'

function App() {
  const [connected, setConnected] = useState(false)
  const [metaLabel, setMetaLabel] = useState('Ready when you are.')
  const [messages, setMessages] = useState([])
  const [streamingText, setStreamingText] = useState('')
  const [error, setError] = useState('')
  const [sessionId, setSessionId] = useState(() =>
    typeof window !== 'undefined' ? window.localStorage.getItem(SESSION_STORAGE_KEY) || null : null
  )
  const [inputValue, setInputValue] = useState('')

  const wsRef = useRef(null)
  const messagesEndRef = useRef(null)
  const sessionIdRef = useRef(sessionId)
  const streamingTextRef = useRef('')
  const lastBackendErrorRef = useRef('')

  sessionIdRef.current = sessionId
  streamingTextRef.current = streamingText

  const setSession = (id) => {
    setSessionId(id)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(SESSION_STORAGE_KEY, id)
    }
  }

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingText])

  const connect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setError('')

    try {
      const ws = new WebSocket(getWsUrl())
      wsRef.current = ws
    } catch (e) {
      setError('Failed to create WebSocket: ' + e.message)
      return
    }

    const ws = wsRef.current

    ws.onopen = () => {
      lastBackendErrorRef.current = ''
      setConnected(true)
      setMetaLabel('Streaming from local Ollama Qwen2.5.')
      if (sessionIdRef.current) {
        ws.send(JSON.stringify({ type: 'ping', session_id: sessionIdRef.current }))
      }
    }

    ws.onmessage = (event) => {
      let msg
      try {
        msg = JSON.parse(event.data)
      } catch {
        streamingTextRef.current += String(event.data)
        setStreamingText(streamingTextRef.current)
        return
      }

      const { type } = msg

      if (type === 'session_reset') {
        if (msg.session_id) setSession(msg.session_id)
        return
      }

      if (type === 'start') {
        if (msg.session_id) setSession(msg.session_id)
        streamingTextRef.current = ''
        setStreamingText('')
        return
      }

      if (type === 'chunk') {
        const chunk = msg.content || ''
        streamingTextRef.current += chunk
        setStreamingText(streamingTextRef.current)
        return
      }

      if (type === 'end') {
        const fullText = streamingTextRef.current
        streamingTextRef.current = ''
        setStreamingText('')
        setMessages((prev) => [...prev, { role: 'assistant', text: fullText }])
        return
      }

      if (type === 'error') {
        const err = msg.error || 'Unknown error.'
        lastBackendErrorRef.current = err
        setError(err)
        setStreamingText('')
      }
    }

    ws.onerror = () => {
      const backendErr = lastBackendErrorRef.current
      setError(backendErr || 'WebSocket error. Check backend / Ollama.')
    }

    ws.onclose = () => {
      setConnected(false)
      setMetaLabel('Click into the window to reconnect if needed.')
      setStreamingText('')
      setTimeout(() => {
        if (wsRef.current?.readyState === WebSocket.CLOSED) {
          connect()
        }
      }, 1000)
    }
  }

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    const onFocus = () => {
      if (wsRef.current?.readyState === WebSocket.CLOSED) connect()
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])

  const sendMessage = () => {
    const text = inputValue.trim()
    if (!text) return
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      setError('Not connected to server.')
      connect()
      return
    }

    setError('')
    setMessages((prev) => [...prev, { role: 'user', text }])
    wsRef.current.send(
      JSON.stringify({
        type: 'message',
        payload: {
          session_id: sessionIdRef.current,
          message: text,
        },
      })
    )
    setInputValue('')
  }

  const resetSession = () => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      connect()
    }
    const id = sessionIdRef.current || crypto.randomUUID()
    setSession(id)
    wsRef.current?.send(
      JSON.stringify({
        type: 'reset',
        session_id: id,
      })
    )
    setMessages([])
    setStreamingText('')
    setError('')
  }

  useEffect(() => {
    window.__resetSession = resetSession
    return () => {
      delete window.__resetSession
    }
  }, [])

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const displayMessages = [...messages]
  if (streamingText) {
    displayMessages.push({ role: 'assistant', text: streamingText })
  }

  return (
    <div className="shell">
      <header className="shellHeader">
        <div className="trafficLights">
          <span className="dot dotRed" />
          <span className="dot dotAmber" />
          <span className="dot dotGreen" />
        </div>
        <div className="title">Ollama · Phi WebSocket Chat</div>
        <div
          className={`statusPill ${connected ? '' : 'statusPillDisconnected'}`}
          data-status={connected ? 'connected' : 'disconnected'}
        >
          <span className="statusIndicator" />
          <span>{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </header>
      <main className="main">
        <div className="messages">
          {displayMessages.map((m, i) => (
            <div
              key={i}
              className={`bubble ${m.role === 'user' ? 'bubbleUser' : 'bubbleAssistant'}`}
            >
              {m.text}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        <div>
          <div className="metaRow">
            <span>{metaLabel}</span>
            <span>Model: qwen2.5 (via Ollama)</span>
          </div>
          <div className="inputRow">
            <div className="inputInner">
              <textarea
                className="inputTextarea"
                rows={1}
                placeholder="Ask me anything…"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={onKeyDown}
              />
              <button type="button" className="sendBtn" onClick={sendMessage}>
                Send
              </button>
            </div>
            <div className="hintRow">
              <span>
                <span className="chip">
                  <span className="kbd">Enter</span> to send ·
                  <span className="kbd">Shift</span> + <span className="kbd">Enter</span>
                  for new line
                </span>
              </span>
              <span className="errorText">{error}</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
