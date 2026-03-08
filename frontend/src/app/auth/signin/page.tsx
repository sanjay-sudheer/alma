'use client'
import { signIn } from 'next-auth/react'
import { useState } from 'react'

export default function SignInPage() {
  const [loading, setLoading] = useState(false)

  const handleGoogleSignIn = async () => {
    setLoading(true)
    await signIn('google', { callbackUrl: '/chat' })
  }

  return (
    <div className="mesh-bg noise-bg min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      {/* Decorative orbs */}
      <div className="absolute top-[-15%] right-[-10%] w-[600px] h-[600px] rounded-full opacity-10"
        style={{ background: 'radial-gradient(circle, #e8c45a 0%, transparent 70%)' }} />
      <div className="absolute bottom-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full opacity-8"
        style={{ background: 'radial-gradient(circle, #162057 0%, transparent 70%)' }} />

      {/* Decorative corner lines */}
      <div className="absolute top-8 left-8 w-16 h-16 border-t border-l opacity-20" style={{ borderColor: '#e8c45a' }} />
      <div className="absolute top-8 right-8 w-16 h-16 border-t border-r opacity-20" style={{ borderColor: '#e8c45a' }} />
      <div className="absolute bottom-8 left-8 w-16 h-16 border-b border-l opacity-20" style={{ borderColor: '#e8c45a' }} />
      <div className="absolute bottom-8 right-8 w-16 h-16 border-b border-r opacity-20" style={{ borderColor: '#e8c45a' }} />

      <div className="relative z-10 w-full max-w-md">
        {/* Logo / wordmark */}
        <div className="text-center mb-10 opacity-0 animate-fade-up" style={{ animationFillMode: 'forwards' }}>
          <div className="inline-flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #d4a827, #e8c45a)', boxShadow: '0 0 30px rgba(212, 168, 39, 0.3)' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#06091a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <span className="font-display text-3xl font-semibold tracking-wide" style={{ color: '#faf6ef' }}>
              Alma
            </span>
          </div>
          <p className="font-body text-sm tracking-[0.2em] uppercase opacity-50" style={{ color: '#faf6ef' }}>
            College Intelligence
          </p>
        </div>

        {/* Card */}
        <div
          className="glass rounded-2xl p-8 opacity-0 animate-fade-up stagger-2"
          style={{
            animationFillMode: 'forwards',
            boxShadow: '0 40px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(232,196,90,0.08), inset 0 1px 0 rgba(255,255,255,0.05)'
          }}
        >
          <div className="mb-8">
            <h1 className="font-display text-2xl font-semibold mb-2" style={{ color: '#faf6ef' }}>
              Welcome back
            </h1>
            <p className="font-body text-sm leading-relaxed opacity-60" style={{ color: '#faf6ef' }}>
              Sign in to start researching colleges with AI-powered intelligence.
            </p>
          </div>

          {/* Google Sign In Button */}
          <button
            onClick={handleGoogleSignIn}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 py-3.5 px-6 rounded-xl font-body font-medium text-sm transition-all duration-200 group relative overflow-hidden"
            style={{
              background: loading ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.08)',
              border: '1px solid rgba(255,255,255,0.12)',
              color: '#faf6ef',
            }}
            onMouseEnter={e => {
              if (!loading) {
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.12)'
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(232,196,90,0.3)'
              }
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.08)'
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.12)'
            }}
          >
            {loading ? (
              <div className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: 'rgba(232,196,90,0.4)', borderTopColor: 'transparent' }} />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
            )}
            {loading ? 'Signing in…' : 'Continue with Google'}
          </button>

          {/* Divider */}
          <div className="flex items-center gap-4 my-6">
            <div className="flex-1 h-px opacity-10" style={{ background: '#faf6ef' }} />
            <span className="font-body text-xs opacity-40" style={{ color: '#faf6ef' }}>or</span>
            <div className="flex-1 h-px opacity-10" style={{ background: '#faf6ef' }} />
          </div>

          <p className="text-center font-body text-xs opacity-40 leading-relaxed" style={{ color: '#faf6ef' }}>
            By signing in, you agree to our Terms of Service<br />and Privacy Policy.
          </p>
        </div>

        {/* Features */}
        <div className="mt-8 grid grid-cols-3 gap-3 opacity-0 animate-fade-up stagger-4" style={{ animationFillMode: 'forwards' }}>
          {[
            { icon: '🔍', label: 'Live Web Scraping' },
            { icon: '🤖', label: 'AI-Powered Answers' },
            { icon: '📚', label: '1000s of Colleges' },
          ].map((f) => (
            <div key={f.label} className="text-center p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div className="text-xl mb-1">{f.icon}</div>
              <p className="font-body text-xs opacity-40 leading-tight" style={{ color: '#faf6ef' }}>{f.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
