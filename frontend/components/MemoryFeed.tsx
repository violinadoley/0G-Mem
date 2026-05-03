"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw, Loader2, Database } from "lucide-react";
import { getMemoryState, StateResponse } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import HashDisplay from "./HashDisplay";
import { formatTimestamp, cn } from "@/lib/utils";

interface MemoryFeedProps {
  agentId: string;
  refreshTrigger?: number;
}

export default function MemoryFeed({ agentId, refreshTrigger }: MemoryFeedProps) {
  const [state, setState] = useState<StateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const authHeaders = await getAuthHeaders(agentId);
      const s = await getMemoryState(agentId, authHeaders);
      setState(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load state.");
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    if (refreshTrigger && refreshTrigger > 0) {
      load();
    }
  }, [load, refreshTrigger]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Chain State</h3>
        <button
          onClick={load}
          disabled={loading}
          className="text-muted hover:text-white transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {error && (
        <p className="text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {!state && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Database className="w-8 h-8 text-muted mb-3" />
          <p className="text-sm text-muted mb-3">Click to load chain state.</p>
          <button
            onClick={load}
            className="text-xs bg-accent/10 hover:bg-accent/20 border border-accent/30 text-accent px-3 py-1.5 rounded-lg transition-colors"
          >
            Load State
          </button>
        </div>
      )}

      {loading && !state && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-muted" />
        </div>
      )}

      {state && (
        <div className="bg-surface-raised border border-border rounded-xl divide-y divide-border">
          <Stat label="Memory Count" value={String(state.memory_count)} />
          <Stat label="NFT Token ID" value={state.nft_token_id > 0 ? String(state.nft_token_id) : "Not minted"} />
          <Stat label="Block Number" value={state.block_number > 0 ? String(state.block_number) : "—"} />
          <Stat
            label="Last Updated"
            value={state.timestamp > 0 ? formatTimestamp(state.timestamp) : "—"}
          />
          <div className="flex items-start justify-between gap-4 px-4 py-3">
            <span className="text-xs text-muted font-medium uppercase tracking-wide flex-shrink-0 pt-0.5">
              Merkle Root
            </span>
            <HashDisplay hash={state.merkle_root} />
          </div>
          <div className="flex items-start justify-between gap-4 px-4 py-3">
            <span className="text-xs text-muted font-medium uppercase tracking-wide flex-shrink-0 pt-0.5">
              DA Tx Hash
            </span>
            <HashDisplay hash={state.da_tx_hash} />
          </div>
        </div>
      )}

      {state && state.memory_count === 0 && (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Database className="w-8 h-8 text-muted mb-2" />
          <p className="text-sm text-muted">No memories stored yet.</p>
          <p className="text-xs text-muted mt-1">Add your first memory above.</p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <span className="text-xs text-muted font-medium uppercase tracking-wide">{label}</span>
      <span className="text-sm text-white">{value}</span>
    </div>
  );
}
