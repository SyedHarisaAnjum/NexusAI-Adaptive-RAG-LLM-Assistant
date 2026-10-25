import SourceList from './SourceList.jsx'

// Labels make it obvious whether an answer came from the user's documents
// or from Gemini's general knowledge.
const BADGES = {
  document: { label: 'From your documents', className: 'badge-document' },
  general: { label: 'General knowledge · not from your documents', className: 'badge-general' },
  not_found: { label: 'Not found in documents', className: 'badge-not-found' },
}

function TypingIndicator({ statusText }) {
  return (
    <span className="typing-row" role="status">
      <span className="typing" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="typing-status">{statusText || 'Thinking…'}</span>
    </span>
  )
}

// status: 'pending' (waiting for first text) | 'streaming' | 'done' | 'stopped' | 'error'.
// Messages loaded from history have no status and are treated as done.
function MessageBubble({ message }) {
  const { role, text, answerType, sources = [], status, error, statusText, routeReason } = message
  const failedWithoutText = status === 'error' && !text
  const badge = role === 'assistant' && !failedWithoutText ? BADGES[answerType] : null
  const className = `bubble bubble-${role}${failedWithoutText ? ' bubble-error' : ''}`

  return (
    <div className={`bubble-row bubble-row-${role}`}>
      <div className={className} aria-busy={status === 'pending' || status === 'streaming'}>
        {badge && <span className={`badge ${badge.className}`}>{badge.label}</span>}
        {/* Why the agent picked this path (documents vs general knowledge). */}
        {role === 'assistant' && routeReason && !failedWithoutText && (
          <p className="route-reason">{routeReason}</p>
        )}

        {status === 'pending' ? (
          <TypingIndicator statusText={statusText} />
        ) : (
          (text || failedWithoutText) && (
            <div className="bubble-text">
              {failedWithoutText ? `Error: ${error}` : text}
              {status === 'streaming' && <span className="cursor" aria-hidden="true" />}
            </div>
          )
        )}

        {status === 'stopped' && <p className="bubble-note">Response stopped.</p>}
        {status === 'error' && text && (
          <p className="bubble-note bubble-note-error">Error: {error}</p>
        )}

        {sources.length > 0 && <SourceList sources={sources} />}
      </div>
    </div>
  )
}

export default MessageBubble
