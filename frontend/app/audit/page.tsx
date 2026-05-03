"use client";

import { useAccount } from "wagmi";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { FileText } from "lucide-react";
import AuditTimeline from "@/components/AuditTimeline";

export default function AuditPage() {
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
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-accent/10 border border-accent/20 rounded-xl flex items-center justify-center">
          <FileText className="w-5 h-5 text-accent" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-white">Audit Log</h1>
          <p className="text-xs text-muted font-mono mt-0.5 truncate max-w-xs">{address}</p>
        </div>
      </div>

      {/* EU AI Act notice */}
      <div className="bg-accent/5 border border-accent/20 rounded-xl px-4 py-3 text-sm text-muted">
        EU AI Act Article 12 compliant audit trail — all read and write operations are
        anchored on-chain with cryptographic proofs.
      </div>

      <AuditTimeline agentId={address} />
    </div>
  );
}
