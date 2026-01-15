import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { QueryProvider } from '@/lib/providers/query-provider'
import { AuthProvider } from '@/lib/providers/auth-provider'
import { Toaster } from '@/components/ui/toaster'

const inter = Inter({ 
  subsets: ['latin'], 
  weight: ['300', '400', '500', '600', '700'],
  variable: '--font-sans',
  display: 'swap',
  adjustFontFallback: false,
  preload: true,
})

export const metadata: Metadata = {
  title: 'WorkSight - AI-Powered Property Lead Discovery',
  description: 'Discover high-value property leads with AI-powered satellite imagery analysis and business contact enrichment.',
  icons: {
    icon: [
      { url: '/brand/worksighticon.svg', type: 'image/svg+xml' },
      { url: '/brand/favicon.ico', type: 'image/x-icon', sizes: 'any' },
    ],
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning className={inter.variable}>
      <body className="font-sans antialiased">
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
