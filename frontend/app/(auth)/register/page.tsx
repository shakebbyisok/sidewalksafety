'use client'

import { useState } from 'react'
import { useRegister } from '@/lib/queries/use-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Link from 'next/link'
import Image from 'next/image'
import { Eye, EyeOff, ArrowRight, ArrowLeft, Check } from 'lucide-react'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [phone, setPhone] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const register = useRegister()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    register.mutate({
      email,
      password,
      company_name: companyName,
      phone: phone || undefined,
    })
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
                  Start finding leads
                  <span className="block text-[#7BB432]">in minutes</span>
                </h1>
                <p className="text-lg text-white/50 leading-relaxed max-w-md mx-auto">
                  Join hundreds of landscape and property service 
                  companies using AI to grow their business.
                </p>
              </div>

              {/* Benefits list */}
              <div className="space-y-4 pt-4 flex flex-col items-center">
                {[
                  { text: 'Free trial with 50 properties', highlight: true },
                  { text: 'No credit card required', highlight: false },
                  { text: 'Setup in under 2 minutes', highlight: false },
                  { text: 'Cancel anytime', highlight: false }
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center ${
                      item.highlight ? 'bg-[#7BB432]' : 'bg-white/10'
                    }`}>
                      <Check className={`w-3 h-3 ${item.highlight ? 'text-white' : 'text-white/60'}`} />
                    </div>
                    <span className={`text-sm ${item.highlight ? 'text-white' : 'text-white/60'}`}>
                      {item.text}
                    </span>
                  </div>
                ))}
              </div>

              {/* Testimonial */}
              <div className="pt-8 border-t border-white/10 max-w-md mx-auto">
                <p className="text-white/60 text-sm italic leading-relaxed">
                  "WorkSight helped us identify $50K in new contracts within the first month. 
                  The property analysis is incredibly accurate."
                </p>
                <div className="mt-4 flex items-center justify-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center text-white/70 text-sm font-medium">
                    JM
                  </div>
                  <div className="text-left">
                    <div className="text-white text-sm font-medium">James Mitchell</div>
                    <div className="text-white/40 text-xs">CEO, Mitchell Landscaping</div>
                  </div>
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

      {/* Right Side - Register Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white relative">
        <div className="w-full max-w-md space-y-6 animate-slide-in relative z-10">
          {/* Mobile Logo */}
          <div className="lg:hidden flex items-center gap-3 mb-6">
            <Image 
              src="/brand/worksighticon.svg" 
              alt="WorkSight" 
              width={36}
              height={25}
              priority
            />
            <span className="text-foreground text-lg font-medium tracking-tight">WorkSight</span>
          </div>

          {/* Back to Login */}
          <Link 
            href="/login" 
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to sign in
          </Link>

          {/* Header */}
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              Create your account
            </h1>
            <p className="text-muted-foreground">
              Start your free trial today
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Company Name */}
            <div className="space-y-2">
              <Label htmlFor="company" className="text-foreground text-sm font-medium">
                Company name
              </Label>
              <Input
                id="company"
                type="text"
                placeholder="Acme Landscaping"
                autoComplete="organization"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                disabled={register.isPending}
                required
                className="h-11 bg-background border-border/60 focus:border-[#7BB432] focus:ring-[#7BB432]/20"
              />
            </div>

            {/* Email */}
            <div className="space-y-2">
              <Label htmlFor="email" className="text-foreground text-sm font-medium">
                Work email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="name@company.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={register.isPending}
                required
                className="h-11 bg-background border-border/60 focus:border-[#7BB432] focus:ring-[#7BB432]/20"
              />
            </div>

            {/* Password */}
            <div className="space-y-2">
              <Label htmlFor="password" className="text-foreground text-sm font-medium">
                Password
              </Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Min. 8 characters"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={register.isPending}
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

            {/* Phone */}
            <div className="space-y-2">
              <Label htmlFor="phone" className="text-foreground text-sm font-medium">
                Phone <span className="text-muted-foreground/60 font-normal">(optional)</span>
              </Label>
              <Input
                id="phone"
                type="tel"
                placeholder="+1 (555) 000-0000"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={register.isPending}
                className="h-11 bg-background border-border/60 focus:border-[#7BB432] focus:ring-[#7BB432]/20"
              />
            </div>

            {/* Submit Button */}
            <Button
              type="submit"
              disabled={register.isPending}
              className="w-full h-11 font-medium text-white bg-[#579130] hover:bg-[#4a7a29] transition-colors mt-2"
            >
              {register.isPending ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Creating account...
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2">
                  Start free trial
                  <ArrowRight className="h-4 w-4" />
                </span>
              )}
            </Button>
          </form>

          {/* Footer */}
          <p className="text-center text-xs text-muted-foreground/60 pt-2">
            By creating an account, you agree to our{' '}
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
