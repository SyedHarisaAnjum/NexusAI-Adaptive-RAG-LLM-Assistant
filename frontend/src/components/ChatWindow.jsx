import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble.jsx'

function ChatWindow({ messages, emptyText }) {
  const bottomRef = useRef(null)

  // Keep the newest text in view. Smooth scrolling on every streamed chunk
  // looks jittery, so jump instantly while an answer is streaming.
  useEffect(() => {
    const streaming = messages.at(-1)?.status === 'streaming'
    bottomRef.current?.scrollIntoView({ behavior: streaming ? 'auto' : 'smooth' })
  }, [messages])

  return (
    <div className="chat-window">
      {messages.length === 0 && <p className="empty-state">{emptyText}</p>}

      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      <div ref={bottomRef} />
    </div>
  )
}

export default ChatWindow
