import type { Metadata } from 'next'
import { Space_Grotesk } from 'next/font/google'
import './globals.css'

const spaceGrotesk = Space_Grotesk({ subsets: ['latin'], variable: '--font-space' })

export const metadata: Metadata = {
  title: '0G Mem',
  description: 'Provable. Pluggable. Owned by you. Join the waitlist for 0G Mem — cryptographically verifiable AI agent memory built on 0G Labs.',
  openGraph: {
    title: '0G Mem',
    description: 'The first verifiable, encrypted, user-owned memory layer for AI agents.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={spaceGrotesk.variable}>
      <body>{children}</body>
    </html>
  )
}
