"use client";

import Link from "next/link";
import { useAccount } from "wagmi";
import { useConnect } from "wagmi";
import { injected } from "wagmi/connectors";
import { ShieldCheck, Lock, User, ArrowRight, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Verifiable",
    description:
      "Every memory operation is anchored on 0G Chain with a cryptographic Merkle proof. Any third party can verify retrieval integrity on-chain.",
    color: "text-accent",
    bg: "bg-accent/10",
    border: "border-accent/20",
  },
  {
    icon: Lock,
    title: "Encrypted",
    description:
      "Memory blobs are encrypted before being uploaded to 0G decentralized storage (DA). Your data remains private by default.",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
  },
  {
    icon: User,
    title: "Owned",
    description:
      "Your wallet address is your agent ID. Mint a MemoryNFT to take ownership on-chain, and grant or revoke access to other agents at any time.",
    color: "text-green-400",
    bg: "bg-green-500/10",
    border: "border-green-500/20",
  },
];

export default function LandingPage() {
  const { isConnected } = useAccount();
  const { connect, isPending } = useConnect();

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 space-y-20">
      {/* Hero */}
      <section className="text-center space-y-8 pt-8">
        <div className="inline-flex items-center gap-2 bg-accent/10 border border-accent/20 rounded-full px-4 py-1.5 text-sm text-accent font-medium">
          <span className="w-2 h-2 rounded-full bg-accent" />
          Powered by 0G Labs
        </div>

        <div className="space-y-4">
          <h1 className="text-5xl sm:text-6xl font-bold text-white tracking-tight leading-tight">
            AI Memory that&apos;s
            <br />
            <span className="text-accent">Provable.</span>
          </h1>
          <p className="text-xl text-muted max-w-2xl mx-auto leading-relaxed">
            Pluggable. Owned by you. Store your agent&apos;s memory on 0G decentralized
            infrastructure — with cryptographic proofs for every retrieval.
          </p>
        </div>

        <div className="flex items-center justify-center gap-4 flex-wrap">
          {isConnected ? (
            <Link
              href="/memory"
              className={cn(
                "flex items-center gap-2 px-6 py-3 rounded-xl text-base font-semibold",
                "bg-accent hover:bg-accent-hover text-white transition-all"
              )}
            >
              Open Memory Explorer
              <ArrowRight className="w-4 h-4" />
            </Link>
          ) : (
            <button
              onClick={() => connect({ connector: injected() })}
              disabled={isPending}
              className={cn(
                "flex items-center gap-2 px-6 py-3 rounded-xl text-base font-semibold",
                "bg-accent hover:bg-accent-hover text-white transition-all",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {isPending ? "Connecting…" : "Connect Wallet to Start"}
              <ArrowRight className="w-4 h-4" />
            </button>
          )}

          <Link
            href="/verify"
            className={cn(
              "flex items-center gap-2 px-6 py-3 rounded-xl text-base font-medium",
              "border border-border hover:border-accent text-muted hover:text-white transition-all"
            )}
          >
            Verify a Proof
            <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      {/* Feature Cards */}
      <section>
        <div className="grid sm:grid-cols-3 gap-4">
          {FEATURES.map(({ icon: Icon, title, description, color, bg, border }) => (
            <div
              key={title}
              className={cn(
                "bg-surface-raised border rounded-xl p-6 space-y-4 transition-all hover:border-opacity-60",
                border
              )}
            >
              <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", bg, border, "border")}>
                <Icon className={cn("w-5 h-5", color)} />
              </div>
              <div>
                <h3 className="text-base font-semibold text-white mb-2">{title}</h3>
                <p className="text-sm text-muted leading-relaxed">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Pluggable SDK section */}
      <section className="space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-semibold text-white">Drop-in memory for any AI agent</h2>
          <p className="text-sm text-muted max-w-xl mx-auto">
            Plug 0G Mem into LangChain, AutoGPT, or any custom agent in three lines of code.
          </p>
        </div>
        <div className="bg-surface border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-surface-raised">
            <span className="w-3 h-3 rounded-full bg-red-500/60" />
            <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
            <span className="w-3 h-3 rounded-full bg-green-500/60" />
            <span className="text-xs text-muted ml-2 font-mono">agent.py</span>
          </div>
          <pre className="px-6 py-5 text-sm font-mono leading-relaxed overflow-x-auto">
            <code>
              <span className="text-blue-400">from</span>
              <span className="text-white"> ogmem </span>
              <span className="text-blue-400">import</span>
              <span className="text-white"> VerifiableMemory{"\n\n"}</span>
              <span className="text-green-400"># Plug into any agent — wallet address = agent ID{"\n"}</span>
              <span className="text-white">memory = VerifiableMemory(agent_id=</span>
              <span className="text-yellow-300">&quot;0xYourWallet&quot;</span>
              <span className="text-white">, network=</span>
              <span className="text-yellow-300">&quot;0g-testnet&quot;</span>
              <span className="text-white">){"\n\n"}</span>
              <span className="text-green-400"># Store encrypted memory on 0G DA{"\n"}</span>
              <span className="text-white">memory.add(</span>
              <span className="text-yellow-300">&quot;The user prefers dark mode&quot;</span>
              <span className="text-white">){"\n\n"}</span>
              <span className="text-green-400"># Query with cryptographic proof{"\n"}</span>
              <span className="text-white">results, proof = memory.query(</span>
              <span className="text-yellow-300">&quot;user preferences&quot;</span>
              <span className="text-white">, top_k=</span>
              <span className="text-accent">3</span>
              <span className="text-white">){"\n\n"}</span>
              <span className="text-green-400"># Anyone can verify on 0G Chain{"\n"}</span>
              <span className="text-white">memory.verify_proof(proof)  </span>
              <span className="text-green-400"># True</span>
            </code>
          </pre>
        </div>
      </section>

      {/* How it works */}
      <section className="space-y-8">
        <h2 className="text-2xl font-semibold text-white text-center">How it works</h2>
        <div className="grid sm:grid-cols-4 gap-4">
          {[
            { step: "01", title: "Connect", desc: "Connect your MetaMask wallet. Your address becomes your Agent ID." },
            { step: "02", title: "Store", desc: "Add memories via the API or UI. Each entry is encrypted and stored on 0G DA." },
            { step: "03", title: "Query", desc: "Semantic search returns top-k results with a cryptographic QueryProof." },
            { step: "04", title: "Verify", desc: "Share your proof. Anyone can verify retrieval integrity on 0G Chain." },
          ].map(({ step, title, desc }) => (
            <div key={step} className="bg-surface border border-border rounded-xl p-5">
              <span className="text-xs font-mono text-accent font-semibold">{step}</span>
              <h4 className="text-sm font-semibold text-white mt-2 mb-1">{title}</h4>
              <p className="text-xs text-muted leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA footer */}
      <section className="text-center pb-8">
        <div className="bg-surface-raised border border-border rounded-2xl px-8 py-10 space-y-4">
          <h2 className="text-2xl font-semibold text-white">
            Ready to own your memory?
          </h2>
          <p className="text-muted text-sm max-w-md mx-auto">
            Connect your wallet and start storing verifiable, encrypted memories on 0G Labs decentralized infrastructure.
          </p>
          {isConnected ? (
            <Link
              href="/memory"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold bg-accent hover:bg-accent-hover text-white transition-all"
            >
              Go to Memory Explorer <ArrowRight className="w-4 h-4" />
            </Link>
          ) : (
            <button
              onClick={() => connect({ connector: injected() })}
              disabled={isPending}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold bg-accent hover:bg-accent-hover text-white transition-all disabled:opacity-50"
            >
              {isPending ? "Connecting…" : "Get Started"} <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
