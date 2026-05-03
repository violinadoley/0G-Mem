"use client";

import { useAccount } from "wagmi";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Award } from "lucide-react";
import AccessPanel from "@/components/AccessPanel";

export default function AccessPage() {
  const { address, isConnected } = useAccount();
  const router = useRouter();

  useEffect(() => {
    if (!isConnected) {
      router.replace("/");
    }
  }, [isConnected, router]);

  if (!isConnected || !address) {
    return null;
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-accent/10 border border-accent/20 rounded-xl flex items-center justify-center">
          <Award className="w-5 h-5 text-accent" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-white">Access Control</h1>
          <p className="text-xs text-muted font-mono mt-0.5 truncate max-w-xs">{address}</p>
        </div>
      </div>

      <p className="text-sm text-muted">
        Mint your MemoryNFT to take on-chain ownership of your memory, then grant or revoke
        access to other agents.
      </p>

      <AccessPanel agentId={address} />
    </div>
  );
}
