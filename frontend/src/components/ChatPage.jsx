import { useEffect, useRef, useState } from 'react'
import { getSession, listDocuments, streamQuestion } from '../api.js'
import ChatWindow from './ChatWindow.jsx'
import ChatInput from './ChatInput.jsx'
import DocumentPanel from './DocumentPanel.jsx'
import ModeToggle from './ModeToggle.jsx'

// localStorage can throw (private mode, blocked storage) - never let that break the app.
const makeStorage = (key) => ({
  get: () => {
    try { return localStorage.getItem(key) } catch { return null }
  },
  set: (value) => {
    try {
      if (value) localStorage.setItem(key, value)
      else localStorage.removeItem(key)
    } catch { /* ignore */ }
  },
})

// Convert a message from the API into the shape the UI uses.
const fromApi = (m) => ({
  id: crypto.randomUUID(),
  role: m.role,
  text: m.content ?? m.answer,
  answerType: m.answer_type,
  sources: m.sources ?? [],
  routeReason: m.route_reason,
})

function ChatPage({ user, onLogout }) {
  // One remembered conversation per user on this browser.
  const [storage] = useState(() => makeStorage(`qa-session-id:${user.user_id}`))
  const [messages, setMessages] = useState([])
  const [sessionId, setSessionId] = useState(storage.get)
  const [mode, setMode] = useState('auto')
  const [documents, setDocuments] = useState([])
  const [selectedDocId, setSelectedDocId] = useState('') // '' = all documents
  const [isLoading, setIsLoading] = useState(false)
  // AbortController of the answer currently streaming (null when idle).
  const abortRef = useRef(null)

  const updateSession = (id) => {
    setSessionId(id)
    storage.set(id)
  }

  // Load the document list once.
  useEffect(() => {
    listDocuments()
      .then(setDocuments)
      .catch(() => setDocuments([]))
  }, [])

  // Restore the previous conversation after a page refresh.
  useEffect(() => {
    const saved = storage.get()
    if (!saved) return
    let ignore = false
    getSession(saved)
      .then((data) => { if (!ignore) setMessages(data.messages.map(fromApi)) })
      .catch(() => { if (!ignore) updateSession(null) })
    return () => { ignore = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storage])

  // Cancel any in-flight answer if the page unmounts (e.g. on logout).
  useEffect(() => () => abortRef.current?.abort(), [])

  const addMessage = (message) =>
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), sources: [], ...message }])

  // Patch one message; `changes` can be an object or a function of the old message.
  const updateMessage = (id, changes) =>
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, ...(typeof changes === 'function' ? changes(m) : changes) } : m,
      ),
    )

  const handleSend = async (question) => {
    if (abortRef.current) return // an answer is already streaming
    const controller = new AbortController()
    abortRef.current = controller
    setIsLoading(true)

    addMessage({ role: 'user', text: question })
    const replyId = crypto.randomUUID()
    addMessage({ id: replyId, role: 'assistant', text: '', status: 'pending' })

    const body = { question, mode }
    if (sessionId) body.session_id = sessionId
    // In Auto mode a selected document also counts: the agent then answers from it.
    if (mode !== 'general' && selectedDocId) body.document_id = selectedDocId

    let finished = false
    const onEvent = (event, data) => {
      if (event === 'meta') {
        if (data.session_id !== sessionId) updateSession(data.session_id)
      } else if (event === 'status') {
        updateMessage(replyId, { statusText: data.text })
      } else if (event === 'route') {
        updateMessage(replyId, { routeReason: data.reason })
      } else if (event === 'delta') {
        updateMessage(replyId, (m) => ({ text: m.text + data.text, status: 'streaming' }))
      } else if (event === 'replace') {
        // The agent rejected the streamed answer (e.g. failed validation) and replaced it.
        updateMessage(replyId, { text: data.text, status: 'streaming' })
      } else if (event === 'done') {
        finished = true
        updateMessage(replyId, {
          text: data.answer,
          answerType: data.answer_type,
          sources: data.sources,
          routeReason: data.route_reason,
          status: 'done',
        })
      } else if (event === 'error') {
        finished = true
        updateMessage(replyId, { status: 'error', error: data.detail })
      }
    }

    try {
      await streamQuestion(body, { signal: controller.signal, onEvent })
      if (!finished) throw new Error('Connection closed before the answer finished.')
    } catch (error) {
      if (error.name === 'AbortError') {
        updateMessage(replyId, { status: 'stopped' })
      } else {
        if (error.status === 404 && error.message.startsWith('Session')) {
          updateSession(null) // server no longer has this conversation
        }
        updateMessage(replyId, { status: 'error', error: error.message })
      }
    } finally {
      abortRef.current = null
      setIsLoading(false)
    }
  }

  const handleStop = () => abortRef.current?.abort()

  const handleNewChat = () => {
    abortRef.current?.abort()
    setMessages([])
    updateSession(null)
  }

  const handleDeleted = (documentId) => {
    setDocuments((prev) => prev.filter((d) => d.document_id !== documentId))
    if (selectedDocId === documentId) setSelectedDocId('')
  }

  const selectedDoc = documents.find((d) => d.document_id === selectedDocId)
  const scopeLabels = {
    auto: selectedDoc
      ? `Auto: ${selectedDoc.filename} is selected, so answers come from it.`
      : 'Auto: uses your documents when they are relevant, otherwise general knowledge.',
    documents: `Answering only from ${selectedDoc ? selectedDoc.filename : 'all uploaded documents'}, with sources.`,
    general: "Answering from Gemini's general knowledge - your documents are not used.",
  }

  return (
    <div className="app">
      <DocumentPanel
        documents={documents}
        selectedDocId={selectedDocId}
        onSelect={setSelectedDocId}
        onUploaded={(doc) => setDocuments((prev) => [...prev, doc])}
        onDeleted={handleDeleted}
      />

      <main className="chat">
        <header className="app-header">
          <div className="header-row">
            <div>
              <h1>AI Q&amp;A Assistant</h1>
              <p>Powered by Gemini</p>
            </div>
            <div className="header-actions">
              <span className="user-email" title={user.email}>{user.email}</span>
              <button type="button" className="new-chat" onClick={handleNewChat}>
                New chat
              </button>
              <button type="button" className="new-chat" onClick={onLogout}>
                Log out
              </button>
            </div>
          </div>
          <div className="header-row">
            <ModeToggle mode={mode} onChange={setMode} disabled={isLoading} />
            <p className={`scope scope-${mode}`}>{scopeLabels[mode]}</p>
          </div>
        </header>

        <ChatWindow
          messages={messages}
          emptyText={
            mode === 'documents'
              ? 'Upload a PDF, then ask a question about it.'
              : 'Ask me anything. In Auto mode I use your documents when they are relevant.'
          }
        />
        <ChatInput
          onSend={handleSend}
          onStop={handleStop}
          isStreaming={isLoading}
          placeholder={mode === 'documents' ? 'Ask about your documents…' : 'Ask anything…'}
        />
      </main>
    </div>
  )
}

export default ChatPage
