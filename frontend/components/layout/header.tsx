'use client'

import { useAuth } from '@/lib/providers/auth-provider'
import { Button } from '@/components/ui/button'
import { useRouter } from 'next/navigation'
import { LogOut } from 'lucide-react'

export function Header() {
  const { user, logout } = useAuth()
  const router = useRouter()

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-12 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold">Sidewalk Safety</h1>
        </div>
        <div className="flex items-center gap-4">
          {user && (
            <>
              <span className="text-sm text-muted-foreground">{user.company_name}</span>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}

