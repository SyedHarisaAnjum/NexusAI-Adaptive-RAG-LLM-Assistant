import { useState } from 'react'

function ChatInput({ onSend, onStop, isStreaming, placeholder = 'Type your question…' }) {
  const [question, setQuestion] = useState('')

  const handleSubmit = (event) => {
    event.preventDefault()
    const trimmed = question.trim()
    // Only one answer at a time: block new submissions while streaming.
    if (!trimmed || isStreaming) return
    onSend(trimmed)
    setQuestion('')
  }

  // Enter sends, Shift+Enter adds a new line, Escape stops a streaming answer.
  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      handleSubmit(event)
    } else if (event.key === 'Escape' && isStreaming) {
      onStop()
    }
  }

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={1}
        maxLength={4000}
      />
      {isStreaming ? (
        <button type="button" className="stop-button" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" disabled={!question.trim()}>
          Send
        </button>
      )}
    </form>
  )
}

export default ChatInput
