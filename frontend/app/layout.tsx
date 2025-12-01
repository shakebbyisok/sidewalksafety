import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { QueryProvider } from '@/lib/providers/query-provider'
import { AuthProvider } from '@/lib/providers/auth-provider'
import { Toaster } from '@/components/ui/toaster'

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' })

export const metadata: Metadata = {
  title: 'Sidewalk Safety - Parking Lot Deal Evaluation',
  description: 'Evaluate parking lot deals for sidewalk repair opportunities',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.variable}>
        <QueryProvider>
          <AuthProvider>
            {children}
            <Toaster />
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  )
}

