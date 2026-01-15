'use client'

import { useState } from 'react'
import { useLogin } from '@/lib/queries/use-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Link from 'next/link'
import Image from 'next/image'
import { Eye, EyeOff, ArrowRight } from 'lucide-react'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const login = useLogin()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    login.mutate({ email, password })
  }

  return (
    <div className="relative flex min-h-screen">
      {/* Left Side - Clean Professional Design */}
      <div 
        className="hidden lg:flex lg:w-1/2 relative overflow-hidden"
        style={{
          background: `#0A0F1C`
        }}
      >
        {/* Subtle grid pattern */}
        <div className="absolute inset-0 opacity-[0.03]">
          <div className="absolute inset-0" style={{
            backgroundImage: `
              linear-gradient(rgba(123, 180, 50, 0.5) 1px, transparent 1px),
              linear-gradient(90deg, rgba(123, 180, 50, 0.5) 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }} />
        </div>

        {/* Gradient orb top right */}
        <div 
          className="absolute -top-40 -right-40 w-[500px] h-[500px] rounded-full opacity-20 blur-[120px]"
          style={{
            background: 'radial-gradient(circle, #7BB432 0%, transparent 70%)'
          }}
        />
        
        {/* Gradient orb bottom left */}
        <div 
          className="absolute -bottom-60 -left-40 w-[600px] h-[600px] rounded-full opacity-15 blur-[120px]"
          style={{
            background: 'radial-gradient(circle, #579130 0%, transparent 70%)'
          }}
        />

        {/* Main content */}
        <div className="relative z-10 flex flex-col justify-between w-full h-full p-12">
          {/* Center - Hero content */}
          <div className="flex-1 flex items-center justify-center pt-20">
            <div className="w-full max-w-lg mx-auto text-center space-y-8">
              {/* WorkSight Icon and Title */}
              <div className="flex flex-col items-center gap-4 mb-12">
                <Image 
                  src="/brand/worksighticon.svg" 
                  alt="WorkSight" 
                  width={80}
                  height={55}
                  className="drop-shadow-lg"
                  priority
                />
                <Image 
                  src="/brand/worksighttitle.svg" 
                  alt="WorkSight" 
                  width={280}
                  height={85}
                  className="drop-shadow-lg"
                  priority
                />
              </div>

              {/* Main headline */}
              <div className="space-y-4">
                <h1 className="text-[2.75rem] leading-[1.1] font-semibold text-white tracking-tight">
                  Discover leads that
                  <span className="block text-[#7BB432]">drive revenue</span>
                </h1>
                <p className="text-lg text-white/50 leading-relaxed max-w-md mx-auto">
                  AI-powered property analysis that finds high-value 
                  opportunities and decision-maker contacts.
                </p>
              </div>

              {/* Feature list */}
              <div className="space-y-4 pt-4 flex flex-col items-center">
                {[
                  'Satellite imagery analysis',
                  'Automated lead scoring',
                  'Contact enrichment'
                ].map((feature, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="w-1.5 h-1.5 rounded-full bg-[#7BB432]" />
                    <span className="text-white/70 text-sm">{feature}</span>
                  </div>
                ))}
              </div>

              {/* Stats */}
              <div className="flex justify-center gap-12 pt-8 border-t border-white/10">
                <div className="text-center">
                  <div className="text-2xl font-semibold text-white">50K+</div>
                  <div className="text-sm text-white/40">Properties analyzed</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-semibold text-white">89%</div>
                  <div className="text-sm text-white/40">Contact accuracy</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-semibold text-white">3x</div>
                  <div className="text-sm text-white/40">Faster prospecting</div>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom - Footer */}
          <div className="flex items-center justify-center text-sm text-white/30">
            <span>© 2026 WorkSight</span>
          </div>
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white relative">
        <div className="w-full max-w-md space-y-8 animate-slide-in relative z-10">
          {/* Mobile Logo */}
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <Image 
              src="/brand/worksighticon.svg" 
              alt="WorkSight" 
              width={36}
              height={25}
              priority
            />
            <span className="text-foreground text-lg font-medium tracking-tight">WorkSight</span>
          </div>

          {/* Header */}
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              Welcome back
            </h1>
            <p className="text-muted-foreground">
              Enter your credentials to access your account
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-4">
              {/* Email */}
              <div className="space-y-2">
                <Label htmlFor="email" className="text-foreground text-sm font-medium">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="name@company.com"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={login.isPending}
                  required
                  className="h-11 bg-background border-border/60 focus:border-[#7BB432] focus:ring-[#7BB432]/20"
                />
              </div>

              {/* Password */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-foreground text-sm font-medium">
                    Password
                  </Label>
                  <button
                    type="button"
                    className="text-sm text-[#579130] hover:text-[#7BB432] transition-colors"
                  >
                    Forgot?
                  </button>
                </div>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={login.isPending}
                    required
                    className="h-11 pr-11 bg-background border-border/60 focus:border-[#7BB432] focus:ring-[#7BB432]/20"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/60 hover:text-foreground transition-colors"
                    tabIndex={-1}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Submit Button */}
            <Button
              type="submit"
              disabled={login.isPending}
              className="w-full h-11 font-medium text-white bg-[#579130] hover:bg-[#4a7a29] transition-colors"
            >
              {login.isPending ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Signing in...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  Sign in
                  <ArrowRight className="h-4 w-4" />
                </span>
              )}
            </Button>
          </form>

          {/* Divider */}
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border/40" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-white px-4 text-sm text-muted-foreground">
                New to WorkSight?
              </span>
            </div>
          </div>

          {/* Register Link */}
          <Link href="/register" className="block">
            <Button
              variant="outline"
              className="w-full h-11 font-medium border-border/60 hover:border-[#7BB432]/50 hover:bg-[#7BB432]/5 transition-all"
              type="button"
            >
              Create an account
            </Button>
          </Link>

          {/* Footer */}
          <p className="text-center text-xs text-muted-foreground/60">
            By signing in, you agree to our{' '}
            <button className="text-muted-foreground hover:text-foreground transition-colors">
              Terms
            </button>{' '}
            and{' '}
            <button className="text-muted-foreground hover:text-foreground transition-colors">
              Privacy Policy
            </button>
          </p>
        </div>
      </div>
    </div>
  )
}
