"use client";

import { useState } from "react";
import { ShieldCheck, ShieldX, Loader2, ClipboardPaste } from "lucide-react";
import { verifyProof, QueryProof, VerifyResponse } from "@/lib/api";
import ProofCard from "@/components/ProofCard";
import { cn } from "@/lib/utils";

const PLACEHOLDER = JSON.stringify(
  {
    agent_id: "0x...",
    query_hash: "0x...",
    blob_ids: [],
    scores: [],
    merkle_proofs: [],
    merkle_root: "0x...",
    da_read_tx: "0x...",
    chain_block: 123456,
    timestamp: 1744756800,
  },
  null,
  2
);

export default function VerifyPage() {
  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [result, setResult] = useState<{ proof: QueryProof; response: VerifyResponse } | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setParseError(null);
    setApiError(null);
    setResult(null);

    let proof: QueryProof;
    try {
      proof = JSON.parse(raw) as QueryProof;
    } catch {
      setParseError("Invalid JSON — please paste a valid QueryProof object.");
      return;
    }

    const agentId = proof.agent_id;
    if (!agentId) {
      setParseError("The proof must include an 'agent_id' field.");
      return;
    }

    setLoading(true);
    try {
      const response = await verifyProof(agentId, proof);
      setResult({ proof, response });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Verification request failed.");
    } finally {
      setLoading(false);
    }
  };

  const handlePasteExample = () => {
    setRaw(PLACEHOLDER);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-accent/10 border border-accent/20 rounded-xl flex items-center justify-center">
          <ShieldCheck className="w-5 h-5 text-accent" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-white">Verify Proof</h1>
          <p className="text-sm text-muted mt-0.5">
            Paste a QueryProof JSON to verify retrieval integrity on 0G Chain.
          </p>
        </div>
      </div>

      {/* Public notice */}
      <div className="bg-accent/5 border border-accent/20 rounded-xl px-4 py-3 text-sm text-muted">
        This page is public — anyone can verify a proof without connecting a wallet.
      </div>

      {/* Form */}
      <form onSubmit={handleVerify} className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-white">QueryProof JSON</label>
            <button
              type="button"
              onClick={handlePasteExample}
              className="flex items-center gap-1.5 text-xs text-muted hover:text-accent transition-colors"
            >
              <ClipboardPaste className="w-3.5 h-3.5" />
              Load example
            </button>
          </div>
          <textarea
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder={PLACEHOLDER}
            rows={14}
            className={cn(
              "w-full bg-surface border border-border rounded-xl px-4 py-3",
              "text-white placeholder:text-muted/40 text-sm font-mono resize-none",
              "focus:outline-none focus:border-accent transition-colors"
            )}
          />
        </div>

        {parseError && (
          <p className="text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
            {parseError}
          </p>
        )}
        {apiError && (
          <p className="text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
            {apiError}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || !raw.trim()}
          className={cn(
            "w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl",
            "text-sm font-semibold bg-accent hover:bg-accent-hover text-white",
            "transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <ShieldCheck className="w-4 h-4" />
          )}
          {loading ? "Verifying on-chain…" : "Verify Proof"}
        </button>
      </form>

      {/* Result */}
      {result && (
        <div className="space-y-4 animate-slide-up">
          {/* Verdict banner */}
          <div
            className={cn(
              "flex items-center gap-3 px-5 py-4 rounded-xl border",
              result.response.valid
                ? "bg-success/10 border-success/30"
                : "bg-error/10 border-error/30"
            )}
          >
            {result.response.valid ? (
              <ShieldCheck className="w-6 h-6 text-success flex-shrink-0" />
            ) : (
              <ShieldX className="w-6 h-6 text-error flex-shrink-0" />
            )}
            <div>
              <p
                className={cn(
                  "font-semibold text-sm",
                  result.response.valid ? "text-success" : "text-error"
                )}
              >
                {result.response.valid ? "Proof Valid" : "Proof Invalid"}
              </p>
              <p className="text-xs text-muted mt-0.5">{result.response.message}</p>
            </div>
          </div>

          {/* Proof details */}
          <ProofCard proof={result.proof} verified={result.response.valid} />
        </div>
      )}
    </div>
  );
}
