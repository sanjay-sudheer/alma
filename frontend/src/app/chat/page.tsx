'use client'
import { useSession, signOut } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useEffect, useState, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import TextareaAutosize from 'react-textarea-autosize'
import Image from 'next/image'
import { loadCollege, sendMessage, listColleges, resetSession } from '@/lib/api'
import type { CollegeInfo } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  rescrape?: boolean
  sources?: string[]
  timestamp: Date
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-4 py-3">
      <div className="typing-dot" />
      <div className="typing-dot" />
      <div className="typing-dot" />
    </div>
  )
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-3 mb-4 ${isUser ? 'justify-end animate-slide-in-right' : 'justify-start animate-slide-in-left'}`}>
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-0.5"
          style={{ background: 'linear-gradient(135deg, #d4a827, #e8c45a)', boxShadow: '0 0 15px rgba(212,168,39,0.2)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#06091a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      )}
      <div className={`max-w-[78%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={`rounded-2xl px-4 py-3 ${isUser
            ? 'text-sm font-body leading-relaxed'
            : 'message-prose'
          }`}
          style={{
            background: isUser
              ? 'linear-gradient(135deg, rgba(212,168,39,0.2), rgba(232,196,90,0.15))'
              : 'rgba(15,24,69,0.5)',
            border: isUser
              ? '1px solid rgba(232,196,90,0.25)'
              : '1px solid rgba(255,255,255,0.06)',
            color: '#faf6ef',
            backdropFilter: 'blur(10px)',
          }}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed" style={{ color: '#faf6ef' }}>{msg.content}</p>
          ) : (
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          )}
        </div>
        {msg.rescrape && (
          <div className="flex items-center gap-1.5 mt-1.5 px-1">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#d4a827' }} />
            <span className="font-body text-xs opacity-40" style={{ color: '#faf6ef' }}>
              Searched for more context
            </span>
          </div>
        )}
        {msg.sources && msg.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2 px-1">
            {msg.sources.map(s => (
              <span key={s} className="font-mono text-[10px] px-2 py-0.5 rounded-full opacity-50"
                style={{ background: 'rgba(232,196,90,0.08)', color: '#e8c45a', border: '1px solid rgba(232,196,90,0.15)' }}>
                {s.replace('web:', '')}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const [collegeName, setCollegeName] = useState('')
  const [collegeInput, setCollegeInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingCollege, setLoadingCollege] = useState(false)
  const [error, setError] = useState('')
  const [recentColleges, setRecentColleges] = useState<CollegeInfo[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [loadStatus, setLoadStatus] = useState<string>('')

  useEffect(() => {
    if (status === 'unauthenticated') router.push('/auth/signin')
  }, [status, router])

  useEffect(() => {
    listColleges().then(setRecentColleges).catch(() => {})
  }, [collegeName])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleLoadCollege = async () => {
    if (!collegeInput.trim() || collegeInput.trim().length < 3) return
    setLoadingCollege(true)
    setError('')
    setLoadStatus('Scraping the web…')
    try {
      const res = await loadCollege(collegeInput.trim(), sessionId || undefined)
      setSessionId(res.session_id)
      setCollegeName(collegeInput.trim())
      setMessages([{
        id: Date.now().toString(),
        role: 'assistant',
        content: `I'm ready to answer your questions about **${collegeInput.trim()}**.\n\nI've loaded **${res.chunks} knowledge chunks** from ${res.sources?.join(', ') || 'multiple sources'}. Ask me anything — admissions, fees, courses, placements, or campus life!`,
        timestamp: new Date(),
      }])
      setLoadStatus('')
    } catch (e: any) {
      setError(e.message || 'Failed to load college data.')
      setLoadStatus('')
    } finally {
      setLoadingCollege(false)
    }
  }

  const handleSend = useCallback(async () => {
    if (!input.trim() || loading || !sessionId) return
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setError('')
    try {
      const res = await sendMessage(sessionId, userMsg.content)
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.reply,
        rescrape: res.rescrape_triggered,
        sources: res.sources,
        timestamp: new Date(),
      }])
    } catch (e: any) {
      setError(e.message || 'Something went wrong. Please try again.')
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }, [input, loading, sessionId])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleReset = async () => {
    if (!sessionId) return
    await resetSession(sessionId)
    setMessages(messages.slice(0, 1))
  }

  const suggestedQueries = [
    'What are all B.Tech branches?',
    'Tell me about fee structure',
    'Admission eligibility criteria',
    'Campus facilities & hostel',
    'Placement statistics',
    'Cut-off ranks last year',
  ]

  if (status === 'loading') {
    return (
      <div className="mesh-bg min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'rgba(232,196,90,0.4)', borderTopColor: '#e8c45a' }} />
      </div>
    )
  }

  return (
    <div className="mesh-bg noise-bg min-h-screen flex" style={{ fontFamily: 'var(--font-dm-sans)' }}>

      {/* ── Sidebar ── */}
      <aside
        className={`flex-shrink-0 flex flex-col transition-all duration-300 ${sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'}`}
        style={{
          background: 'rgba(6,9,26,0.7)',
          backdropFilter: 'blur(20px)',
          borderRight: '1px solid rgba(255,255,255,0.05)',
        }}
      >
        {/* Logo */}
        <div className="p-5 flex items-center gap-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: 'linear-gradient(135deg, #d4a827, #e8c45a)' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#06091a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span className="font-display text-lg font-semibold" style={{ color: '#faf6ef' }}>Alma</span>
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full font-body opacity-50"
            style={{ background: 'rgba(232,196,90,0.1)', color: '#e8c45a', border: '1px solid rgba(232,196,90,0.15)' }}>
            Beta
          </span>
        </div>

        {/* College Loader */}
        <div className="p-4" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <p className="font-body text-xs uppercase tracking-widest opacity-40 mb-3" style={{ color: '#faf6ef' }}>
            Research College
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={collegeInput}
              onChange={e => setCollegeInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLoadCollege()}
              placeholder="e.g. IIT Bombay"
              className="flex-1 text-sm px-3 py-2 rounded-lg outline-none font-body transition-all"
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.08)',
                color: '#faf6ef',
              }}
              onFocus={e => { e.target.style.borderColor = 'rgba(232,196,90,0.4)' }}
              onBlur={e => { e.target.style.borderColor = 'rgba(255,255,255,0.08)' }}
            />
            <button
              onClick={handleLoadCollege}
              disabled={loadingCollege || collegeInput.trim().length < 3}
              className="px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150 flex-shrink-0"
              style={{
                background: loadingCollege ? 'rgba(212,168,39,0.3)' : 'rgba(212,168,39,0.9)',
                color: '#06091a',
                opacity: collegeInput.trim().length < 3 ? 0.4 : 1,
              }}
            >
              {loadingCollege ? (
                <div className="w-4 h-4 rounded-full border-2 animate-spin" style={{ borderColor: '#06091a33', borderTopColor: '#06091a' }} />
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
              )}
            </button>
          </div>
          {loadStatus && (
            <p className="text-xs mt-2 opacity-50 font-body animate-pulse" style={{ color: '#e8c45a' }}>
              ⏳ {loadStatus}
            </p>
          )}
          {error && (
            <p className="text-xs mt-2 font-body" style={{ color: '#f87171' }}>⚠️ {error}</p>
          )}
        </div>

        {/* Recent colleges */}
        {recentColleges.length > 0 && (
          <div className="p-4 flex-1 overflow-y-auto">
            <p className="font-body text-xs uppercase tracking-widest opacity-40 mb-3" style={{ color: '#faf6ef' }}>
              Recent
            </p>
            <div className="space-y-1">
              {recentColleges.slice(0, 8).map(c => (
                <button
                  key={c.college}
                  onClick={() => {
                    setCollegeInput(c.college)
                    setTimeout(handleLoadCollege, 100)
                  }}
                  className="w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group"
                  style={{
                    background: collegeName.toLowerCase() === c.college.toLowerCase()
                      ? 'rgba(232,196,90,0.1)'
                      : 'transparent',
                    border: collegeName.toLowerCase() === c.college.toLowerCase()
                      ? '1px solid rgba(232,196,90,0.2)'
                      : '1px solid transparent',
                    color: '#faf6ef',
                  }}
                  onMouseEnter={e => { if (collegeName.toLowerCase() !== c.college.toLowerCase()) (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.04)' }}
                  onMouseLeave={e => { if (collegeName.toLowerCase() !== c.college.toLowerCase()) (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
                >
                  <p className="font-body text-sm truncate opacity-80">{c.college}</p>
                  <p className="font-body text-xs opacity-30 mt-0.5">{c.chunks} chunks</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* User profile */}
        <div className="p-4 mt-auto" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <div className="flex items-center gap-3">
            {session?.user?.image ? (
              <Image src={session.user.image} alt="avatar" width={32} height={32} className="rounded-full" />
            ) : (
              <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold"
                style={{ background: 'rgba(232,196,90,0.2)', color: '#e8c45a' }}>
                {session?.user?.name?.[0]?.toUpperCase() || '?'}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="font-body text-sm truncate opacity-80" style={{ color: '#faf6ef' }}>
                {session?.user?.name || 'User'}
              </p>
              <p className="font-body text-xs truncate opacity-40" style={{ color: '#faf6ef' }}>
                {session?.user?.email}
              </p>
            </div>
            <button
              onClick={() => signOut({ callbackUrl: '/auth/signin' })}
              className="p-1.5 rounded-lg opacity-40 hover:opacity-80 transition-opacity"
              title="Sign out"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#faf6ef" strokeWidth="2">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 flex flex-col min-h-screen min-w-0">

        {/* Header */}
        <header className="flex items-center gap-4 px-6 py-4 flex-shrink-0"
          style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', background: 'rgba(6,9,26,0.4)', backdropFilter: 'blur(10px)' }}>
          <button
            onClick={() => setSidebarOpen(o => !o)}
            className="p-2 rounded-lg opacity-40 hover:opacity-70 transition-opacity"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#faf6ef" strokeWidth="2">
              <path d="M3 12h18M3 6h18M3 18h18"/>
            </svg>
          </button>

          {collegeName ? (
            <div className="flex items-center gap-3 flex-1">
              <div>
                <h1 className="font-display text-lg font-semibold capitalize" style={{ color: '#faf6ef' }}>
                  {collegeName}
                </h1>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={handleReset}
                  className="text-xs px-3 py-1.5 rounded-lg font-body opacity-50 hover:opacity-80 transition-opacity"
                  style={{ border: '1px solid rgba(255,255,255,0.1)', color: '#faf6ef' }}
                >
                  Clear chat
                </button>
              </div>
            </div>
          ) : (
            <h1 className="font-display text-lg opacity-50" style={{ color: '#faf6ef' }}>
              Select a college to begin
            </h1>
          )}
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6" style={{ maxHeight: 'calc(100vh - 140px)' }}>
          {!collegeName ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-6"
                style={{ background: 'linear-gradient(135deg, rgba(212,168,39,0.2), rgba(232,196,90,0.1))', border: '1px solid rgba(232,196,90,0.2)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#e8c45a" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <h2 className="font-display text-2xl font-semibold mb-3 opacity-0 animate-fade-up" style={{ color: '#faf6ef', animationFillMode: 'forwards' }}>
                Your College Research Assistant
              </h2>
              <p className="font-body text-sm opacity-50 max-w-sm leading-relaxed mb-8 opacity-0 animate-fade-up stagger-2" style={{ color: '#faf6ef', animationFillMode: 'forwards' }}>
                Enter any college name in the sidebar. Alma will scrape the web in real-time and answer your questions with verified data.
              </p>
              <div className="grid grid-cols-2 gap-3 w-full max-w-sm opacity-0 animate-fade-up stagger-3" style={{ animationFillMode: 'forwards' }}>
                {['IIT Bombay', 'BITS Pilani', 'NIT Trichy', 'Model Engineering College'].map(c => (
                  <button
                    key={c}
                    onClick={() => { setCollegeInput(c); setSidebarOpen(true) }}
                    className="text-left p-3 rounded-xl text-sm font-body transition-all"
                    style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)', color: '#faf6ef', opacity: 0.7 }}
                    onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(232,196,90,0.2)'; (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
                    onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.06)'; (e.currentTarget as HTMLButtonElement).style.opacity = '0.7' }}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto">
              {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
              {loading && (
                <div className="flex gap-3 mb-4 animate-slide-in-left">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0"
                    style={{ background: 'linear-gradient(135deg, #d4a827, #e8c45a)' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#06091a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </div>
                  <div className="rounded-2xl" style={{ background: 'rgba(15,24,69,0.5)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <TypingIndicator />
                  </div>
                </div>
              )}
              {/* Suggested queries — show when no messages besides welcome */}
              {messages.length === 1 && !loading && (
                <div className="mt-4 animate-fade-up">
                  <p className="font-body text-xs uppercase tracking-widest opacity-30 mb-3 text-center" style={{ color: '#faf6ef' }}>
                    Suggested questions
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {suggestedQueries.map(q => (
                      <button
                        key={q}
                        onClick={() => { setInput(q); setTimeout(handleSend, 50) }}
                        className="text-sm px-4 py-2 rounded-full font-body transition-all duration-150"
                        style={{
                          background: 'rgba(232,196,90,0.06)',
                          border: '1px solid rgba(232,196,90,0.15)',
                          color: '#e8c45a',
                        }}
                        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(232,196,90,0.12)' }}
                        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(232,196,90,0.06)' }}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        {collegeName && (
          <div className="px-4 pb-4 pt-2 flex-shrink-0"
            style={{ borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(6,9,26,0.4)', backdropFilter: 'blur(10px)' }}>
            <div className="max-w-3xl mx-auto">
              <div
                className="flex items-end gap-3 rounded-2xl px-4 py-3 transition-all"
                style={{
                  background: 'rgba(15,24,69,0.5)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  backdropFilter: 'blur(10px)',
                }}
              >
                <TextareaAutosize
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={`Ask about ${collegeName}…`}
                  minRows={1}
                  maxRows={5}
                  className="flex-1 bg-transparent outline-none resize-none text-sm font-body leading-relaxed py-0.5"
                  style={{ color: '#faf6ef' }}
                  disabled={loading}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || loading}
                  className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-150"
                  style={{
                    background: input.trim() && !loading
                      ? 'linear-gradient(135deg, #d4a827, #e8c45a)'
                      : 'rgba(255,255,255,0.06)',
                    cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
                  }}
                >
                  {loading ? (
                    <div className="w-3.5 h-3.5 rounded-full border-2 animate-spin" style={{ borderColor: '#ffffff33', borderTopColor: '#fff' }} />
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={input.trim() ? '#06091a' : '#ffffff40'} strokeWidth="2.5">
                      <path d="M5 12h14M12 5l7 7-7 7"/>
                    </svg>
                  )}
                </button>
              </div>
              <p className="text-center font-body text-xs opacity-20 mt-2" style={{ color: '#faf6ef' }}>
                Press Enter to send · Shift+Enter for new line
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
