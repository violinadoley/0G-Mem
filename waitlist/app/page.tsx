import WaitlistForm from './components/WaitlistForm'

export default function Page() {
  return (
    <div className="min-h-screen bg-[#111] text-[#e8e8e8] flex flex-col">

      {/* Nav */}
      <nav className="flex items-center px-6 md:px-10 py-5 border-b border-[#1e1e1e]">
        <span className="text-[15px] font-medium text-white">0G Mem</span>
      </nav>

      {/* Body */}
      <div className="flex flex-col lg:flex-row flex-1">

        {/* Left */}
        <div className="lg:w-[380px] lg:shrink-0 lg:border-r border-b lg:border-b-0 border-[#1e1e1e] flex flex-col justify-center px-6 md:px-12 py-8 lg:py-20">
          <p className="text-[11px] tracking-[0.2em] text-[#888] uppercase mb-5">Early Access</p>
          <h1 className="text-[36px] md:text-[40px] font-semibold tracking-[-0.03em] leading-[1.1] text-white mb-5">
            Shape what<br />we build.
          </h1>
          <p className="text-[15px] text-[#aaa] leading-relaxed mb-5 max-w-xs">
            We're building memory infrastructure for AI agents. Tell us what you need.
          </p>
          <a
            href="https://x.com/0G_Mem"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-[13px] text-[#888] hover:text-white transition-colors duration-150"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.746l7.73-8.835L1.254 2.25H8.08l4.259 5.632L18.244 2.25zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z"/>
            </svg>
            @0G_Mem
          </a>
        </div>

        {/* Right */}
        <div className="flex-1 flex items-start lg:items-center justify-center px-6 md:px-12 py-8 lg:py-20">
          <div className="w-full max-w-lg">
            <WaitlistForm />
          </div>
        </div>

      </div>

    </div>
  )
}
