'use client'

import { useState } from 'react'
import { useAuth } from '@/lib/providers/auth-provider'
import { useRouter, usePathname } from 'next/navigation'
import Image from 'next/image'
import { cn } from '@/lib/utils'
import { 
  LogOut, 
  User, 
  Settings, 
  ChevronDown,
  Map,
  BarChart2
} from 'lucide-react'

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Discover', icon: Map },
  { href: '/usage', label: 'Usage', icon: BarChart2 },
]

export function Header() {
  const { user, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [showUserMenu, setShowUserMenu] = useState(false)

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  return (
    <header className="sticky top-0 z-50 w-full h-14 bg-background border-b border-border">
      <div className="h-full flex items-center justify-between px-4">
        {/* Left: Logo + Nav */}
        <div className="flex items-center gap-6">
          {/* Logo */}
          <div 
            className="flex items-center cursor-pointer" 
            onClick={() => router.push('/dashboard')}
          >
            <Image 
              src="/brand/worksighticon.svg" 
              alt="WorkSight" 
              width={48}
              height={33}
              className="h-8 w-auto"
            />
          </div>

          {/* Nav Links */}
          <nav className="flex items-center">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon
              const isActive = pathname === item.href || 
                (item.href === '/dashboard' && pathname === '/')
              
              return (
                <button
                  key={item.href}
                  onClick={() => router.push(item.href)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
                    isActive 
                      ? 'text-foreground bg-muted' 
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </button>
              )
            })}
          </nav>
        </div>

        {/* Right: User */}
        {user && (
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-muted transition-colors"
            >
              <div className="h-6 w-6 rounded-full bg-foreground/10 flex items-center justify-center text-xs font-medium">
                {user.company_name?.charAt(0)?.toUpperCase() || 'U'}
              </div>
              <span className="text-sm font-medium hidden sm:block">{user.company_name}</span>
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>

            {/* Dropdown */}
            {showUserMenu && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
                <div className="absolute right-0 top-full mt-1 w-48 bg-card border border-border rounded-lg shadow-lg overflow-hidden z-50">
                  <div className="px-3 py-2 border-b border-border">
                    <p className="text-sm font-medium truncate">{user.company_name}</p>
                    <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                  </div>
                  <div className="p-1">
                    <DropdownItem icon={Settings} label="Settings" onClick={() => { setShowUserMenu(false); router.push('/settings') }} />
                  </div>
                  <div className="p-1 border-t border-border">
                    <DropdownItem icon={LogOut} label="Sign out" onClick={handleLogout} danger />
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </header>
  )
}

function DropdownItem({ 
  icon: Icon, 
  label, 
  onClick,
  danger
}: { 
  icon: typeof User
  label: string
  onClick?: () => void
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors',
        danger 
          ? 'text-destructive hover:bg-destructive/10' 
          : 'text-foreground hover:bg-muted'
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}
