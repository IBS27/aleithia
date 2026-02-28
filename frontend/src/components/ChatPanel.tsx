import { useState, useRef, useEffect } from 'react'
import type { ChatMessage } from '../types/index.ts'

interface Props {
  messages: ChatMessage[]
  onSend: (message: string) => void
  loading: boolean
}

export default function ChatPanel({ messages, onSend, loading }: Props) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !loading) {
      onSend(input.trim())
      setInput('')
    }
  }

  return (
    <div className="flex flex-col h-full border border-white/[0.06] bg-white/[0.01]">
      <div className="px-4 py-3 border-b border-white/[0.06]">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-white/60">Query Engine</h3>
        <p className="text-[10px] font-mono text-white/20 mt-0.5">Powered by live Chicago data</p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
        {messages.length === 0 && (
          <div className="py-8">
            <p className="text-xs text-white/25 mb-4">Suggested queries</p>
            <div className="space-y-1.5">
              {[
                'What permits do I need?',
                'How is foot traffic in this area?',
                'What are the zoning restrictions?',
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => onSend(q)}
                  className="block w-full text-left text-xs text-white/35 hover:text-white/70 bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.04] px-4 py-2.5 transition-colors cursor-pointer"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] px-4 py-2.5 text-xs leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-white text-[#06080d]'
                  : 'bg-white/[0.04] border border-white/[0.06] text-white/70'
              }`}
            >
              <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/[0.04] border border-white/[0.06] px-4 py-2.5 text-xs text-white/30 font-mono">
              processing...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="p-3 border-t border-white/[0.06]">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Query permits, zoning, competition..."
            className="flex-1 bg-white/[0.03] border border-white/[0.06] px-4 py-2.5 text-xs text-white placeholder-white/20 focus:outline-none focus:border-white/20 transition-colors"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="bg-white text-[#06080d] disabled:bg-white/[0.06] disabled:text-white/20 px-4 py-2.5 text-xs font-medium transition-colors cursor-pointer"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  )
}
