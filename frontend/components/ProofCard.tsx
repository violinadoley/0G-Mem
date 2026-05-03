"use client";

import { ShieldCheck, ShieldX, ExternalLink } from "lucide-react";
import type { QueryProof } from "@/lib/api";
import { formatTimestamp } from "@/lib/utils";
import HashDisplay from "./HashDisplay";

interface ProofCardProps {
  proof: QueryProof;
  verified?: boolean;
}

const ROW_CLASSES = "flex items-start justify-between gap-4 py-2.5 border-b border-border last:border-0";
const LABEL_CLASSES = "text-xs text-muted font-medium uppercase tracking-wide flex-shrink-0 pt-0.5";

export default function ProofCard({ proof, verified }: ProofCardProps) {
  const isVerified = verified ?? proof.verified;

  return (
    <div className="bg-surface-raised border border-border rounded-xl p-5 space-y-1 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-semibold text-white">Query Proof</span>
        {isVerified !== undefined && (
          <span
            className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
              isVerified
                ? "bg-success/10 text-success"
                : "bg-error/10 text-error"
            }`}
          >
            {isVerified ? (
              <ShieldCheck className="w-3.5 h-3.5" />
            ) : (
              <ShieldX className="w-3.5 h-3.5" />
            )}
            {isVerified ? "Verified" : "Invalid"}
          </span>
        )}
      </div>

      <div>
        <div className={ROW_CLASSES}>
          <span className={LABEL_CLASSES}>Agent ID</span>
          <HashDisplay hash={proof.agent_id} chars={22} />
        </div>
        <div className={ROW_CLASSES}>
          <span className={LABEL_CLASSES}>Query Hash</span>
          <HashDisplay hash={proof.query_hash} chars={22} />
        </div>
        <div className={ROW_CLASSES}>
          <span className={LABEL_CLASSES}>Merkle Root</span>
          <HashDisplay hash={proof.merkle_root} chars={22} />
        </div>
        <div className={ROW_CLASSES}>
          <span className={LABEL_CLASSES}>DA Read Tx</span>
          <HashDisplay hash={proof.da_read_tx} chars={22} />
        </div>
        <div className={ROW_CLASSES}>
          <span className={LABEL_CLASSES}>Chain Block</span>
          <span className="text-sm text-muted font-mono">{proof.chain_block ?? "—"}</span>
        </div>
        <div className={ROW_CLASSES}>
          <span className={LABEL_CLASSES}>Blobs Retrieved</span>
          <span className="text-sm text-muted">{proof.blob_ids?.length ?? 0}</span>
        </div>
        <div className={ROW_CLASSES}>
          <span className={LABEL_CLASSES}>Timestamp</span>
          <span className="text-sm text-muted">
            {proof.timestamp ? formatTimestamp(proof.timestamp) : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
