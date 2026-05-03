'use client'

import { useState, useRef, useEffect } from 'react'

type FormData = {
  name: string
  email: string
  role: string[]
  framework: string[]
  pain_point: string[]
  priority: string
  data_sharing: string
  would_pay: string
}

const INITIAL: FormData = {
  name: '',
  email: '',
  role: [],
  framework: [],
  pain_point: [],
  priority: '',
  data_sharing: '',
  would_pay: '',
}

const inputClass =
  'w-full bg-[#222] border border-[#444] rounded-lg px-4 py-3 text-[14px] text-white placeholder-[#888] transition-all duration-150 focus:border-[#777] focus:bg-[#262626]'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[13px] text-[#bbb] mb-2">{label}</label>
      {children}
    </div>
  )
}

function MultiSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string[]
  onChange: (v: string[]) => void
  options: { value: string; label: string }[]
  placeholder: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const toggle = (v: string) => {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  }

  const displayLabel =
    value.length === 0
      ? placeholder
      : options
          .filter((o) => value.includes(o.value))
          .map((o) => o.label)
          .join(', ')

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={inputClass + ' cursor-pointer text-left flex items-center justify-between'}
        style={{ color: value.length ? '#ffffff' : '#888' }}
      >
        <span className="truncate pr-2">{displayLabel}</span>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="shrink-0 text-[#555]"><path d="M2.5 4.5L6 8L9.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </button>

      {open && (
        <div className="absolute z-10 top-full mt-1 w-full bg-[#1a1a1a] border border-[#333] rounded-lg overflow-hidden shadow-xl">
          {options.map((o) => {
            const selected = value.includes(o.value)
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => toggle(o.value)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-[13px] text-left hover:bg-[#252525] transition-colors duration-100"
              >
                <span
                  className={`w-4 h-4 rounded shrink-0 border flex items-center justify-center transition-colors duration-100 ${
                    selected ? 'bg-white border-white' : 'border-[#444]'
                  }`}
                >
                  {selected && (
                    <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
                      <path d="M1 3.5L3.5 6L8 1" stroke="#000" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className={selected ? 'text-white' : 'text-[#999]'}>{o.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function RadioGroup({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`text-[13px] px-5 py-2.5 rounded-lg border transition-all duration-150 ${
            value === o.value
              ? 'border-white bg-white text-black font-medium'
              : 'border-[#444] bg-[#222] text-[#999] hover:border-[#666] hover:text-[#ccc]'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function SuccessState({ name }: { name: string }) {
  const first = name ? name.split(' ')[0] : null
  return (
    <div>
      <p className="text-[17px] text-white font-medium mb-2 tracking-tight">
        {first ? `You're on the list, ${first}.` : "You're on the list."}
      </p>
      <p className="text-[14px] text-[#555] leading-relaxed mb-8">
        We'll reach out when we're ready.
      </p>
      <a
        href="https://x.com/0G_Mem"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-3 bg-white hover:bg-[#f0f0f0] text-black text-[14px] font-medium rounded-lg px-5 py-3 transition-colors duration-150"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.746l7.73-8.835L1.254 2.25H8.08l4.259 5.632L18.244 2.25zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z"/>
        </svg>
        Follow @0G_Mem for updates
      </a>
    </div>
  )
}

export default function WaitlistForm() {
  const [form, setForm] = useState<FormData>(INITIAL)
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('loading')
    setErrorMsg('')

    try {
      const payload = {
        ...form,
        role: form.role.join(', '),
        framework: form.framework.join(', '),
        pain_point: form.pain_point.join(', '),
      }
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Something went wrong')
      setStatus('success')
    } catch (err) {
      setStatus('error')
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong')
      setTimeout(() => setStatus('idle'), 4000)
    }
  }

  if (status === 'success') return <SuccessState name={form.name} />

  return (
    <form onSubmit={handleSubmit} className="space-y-4">

      <div className="grid grid-cols-2 gap-3">
        <Field label="Name">
          <input
            type="text"
            placeholder="Your name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field label="Email">
          <input
            type="email"
            placeholder="you@example.com"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            required
            className={inputClass}
          />
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Role">
          <MultiSelect
            value={form.role}
            onChange={(v) => setForm((f) => ({ ...f, role: v }))}
            placeholder="Select one or more"
            options={[
              { value: 'developer', label: 'Developer' },
              { value: 'founder', label: 'Founder' },
              { value: 'researcher', label: 'Researcher' },
              { value: 'enterprise', label: 'Enterprise' },
              { value: 'other', label: 'Other' },
            ]}
          />
        </Field>
        <Field label="What do you build with?">
          <MultiSelect
            value={form.framework}
            onChange={(v) => setForm((f) => ({ ...f, framework: v }))}
            placeholder="Select one or more"
            options={[
              { value: 'langchain', label: 'LangChain' },
              { value: 'autogen', label: 'AutoGen' },
              { value: 'crewai', label: 'CrewAI' },
              { value: 'custom', label: 'Custom' },
              { value: 'none', label: 'None yet' },
              { value: 'other', label: 'Other' },
            ]}
          />
        </Field>
      </div>

      <Field label="Biggest frustrations with AI agent memory">
        <MultiSelect
          value={form.pain_point}
          onChange={(v) => setForm((f) => ({ ...f, pain_point: v }))}
          placeholder="Select all that apply →"
          options={[
            { value: 'no_persistence', label: "Memory doesn't persist across sessions" },
            { value: 'no_control', label: 'No control over what gets remembered' },
            { value: 'not_portable', label: "Can't use memory across different agents" },
            { value: 'provider_owned', label: 'Memory is stored by the provider, not me' },
            { value: 'no_verification', label: "Can't verify what's actually in memory" },
            { value: 'no_sharing', label: "Can't selectively share memory with agents" },
            { value: 'gets_stale', label: 'Memory gets outdated or irrelevant' },
          ]}
        />
      </Field>

      <Field label="What matters most to you?">
        <RadioGroup
          value={form.priority}
          onChange={(v) => setForm((f) => ({ ...f, priority: v }))}
          options={[
            { value: 'control', label: 'Complete control over my memory' },
            { value: 'portable', label: 'Pluggable across any agent or framework' },
          ]}
        />
      </Field>

      <Field label="Would you use a paid version?">
        <RadioGroup
          value={form.would_pay}
          onChange={(v) => setForm((f) => ({ ...f, would_pay: v }))}
          options={[
            { value: 'yes', label: 'Yes' },
            { value: 'maybe', label: 'Maybe' },
            { value: 'no', label: 'No' },
          ]}
        />
      </Field>

      <Field label="Does it concern you that cloud AI memory providers store and can access your agent's data?">
        <RadioGroup
          value={form.data_sharing}
          onChange={(v) => setForm((f) => ({ ...f, data_sharing: v }))}
          options={[
            { value: 'yes', label: 'Yes' },
            { value: 'somewhat', label: 'Somewhat' },
            { value: 'not_really', label: 'Not really' },
          ]}
        />
      </Field>

      {status === 'error' && (
        <p className="text-[12px] text-red-400">{errorMsg}</p>
      )}

      <button
        type="submit"
        disabled={status === 'loading'}
        className="w-full bg-white hover:bg-[#f0f0f0] disabled:opacity-40 disabled:cursor-not-allowed text-[#0c0c0c] text-[14px] font-semibold tracking-tight rounded-lg px-4 py-2.5 transition-colors duration-150 mt-2"
      >
        {status === 'loading' ? 'Joining...' : 'Join the waitlist'}
      </button>

    </form>
  )
}
