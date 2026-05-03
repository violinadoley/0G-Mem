import { createClient } from '@supabase/supabase-js'
import { Resend } from 'resend'
import { NextResponse } from 'next/server'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SECRET_KEY!
)

const resend = new Resend(process.env.RESEND_API_KEY!)

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { name, email, role, framework, pain_point, priority, data_sharing, would_pay } = body

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return NextResponse.json({ error: 'A valid email is required.' }, { status: 400 })
    }

    const { error } = await supabase
      .from('waitlist')
      .insert([{ name, email, role, framework, pain_point, priority, data_sharing, would_pay }])

    if (error) {
      if (error.code === '23505') {
        return NextResponse.json(
          { error: 'This email is already on the waitlist.' },
          { status: 409 }
        )
      }
      console.error('Supabase error:', error)
      return NextResponse.json({ error: 'Failed to save. Please try again.' }, { status: 500 })
    }

    const firstName = name ? name.split(' ')[0] : null

    await resend.emails.send({
      from: '0G Mem <onboarding@resend.dev>',
      to: 'violinadoley21@gmail.com',
      subject: `New waitlist signup — ${email}`,
      html: `
        <div style="font-family:-apple-system,sans-serif;max-width:480px;padding:32px;background:#fff;color:#111;">
          <h2 style="font-size:18px;font-weight:600;margin:0 0 20px;">New signup</h2>
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <tr><td style="padding:8px 0;color:#888;width:120px;">Name</td><td style="padding:8px 0;">${name || '—'}</td></tr>
            <tr><td style="padding:8px 0;color:#888;">Email</td><td style="padding:8px 0;">${email}</td></tr>
            <tr><td style="padding:8px 0;color:#888;">Role</td><td style="padding:8px 0;">${role || '—'}</td></tr>
            <tr><td style="padding:8px 0;color:#888;">Framework</td><td style="padding:8px 0;">${framework || '—'}</td></tr>
            <tr><td style="padding:8px 0;color:#888;vertical-align:top;">Pain points</td><td style="padding:8px 0;">${pain_point || '—'}</td></tr>
            <tr><td style="padding:8px 0;color:#888;">Priority</td><td style="padding:8px 0;">${priority || '—'}</td></tr>
            <tr><td style="padding:8px 0;color:#888;">Would pay</td><td style="padding:8px 0;">${would_pay || '—'}</td></tr>
            <tr><td style="padding:8px 0;color:#888;">Data sharing</td><td style="padding:8px 0;">${data_sharing || '—'}</td></tr>
          </table>
        </div>
      `.trim(),
    })

    return NextResponse.json({ success: true })
  } catch (err) {
    console.error('Waitlist API error:', err)
    return NextResponse.json({ error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
