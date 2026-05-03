"use client";

import { useState } from "react";
import { Search, Loader2, ChevronDown, Copy, Check } from "lucide-react";
import { queryMemory, QueryResponse } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import ProofCard from "./ProofCard";
import { cn } from "@/lib/utils";

interface QueryFormProps {
  agentId: string;
}

const TOP_K_OPTIONS = [1, 3, 5, 10];

export default function QueryForm({ agentId }: QueryFormProps) {
  const [queryText, setQueryText] = useState("");
  const [topK, setTopK] = useState(3);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [showProof, setShowProof] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopyProof = () => {
    if (!result?.proof) return;
    navigator.clipboard.writeText(JSON.stringify(result.proof, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryText.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setShowProof(false);

    try {
      const authHeaders = await getAuthHeaders(agentId);
      const res = await queryMemory(agentId, queryText.trim(), topK, authHeaders);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-2">
          <input
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            placeholder="Search your memories…"
            disabled={loading}
            className={cn(
              "flex-1 bg-surface border border-border rounded-xl px-4 py-2.5",
              "text-white placeholder:text-muted text-sm",
              "focus:outline-none focus:border-accent transition-colors",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          />
          <div className="relative">
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              disabled={loading}
              className={cn(
                "appearance-none bg-surface border border-border rounded-xl",
                "px-3 py-2.5 pr-7 text-sm text-white",
                "focus:outline-none focus:border-accent transition-colors",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {TOP_K_OPTIONS.map((k) => (
                <option key={k} value={k}>
                  Top {k}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted pointer-events-none" />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !queryText.trim()}
          className={cn(
            "w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl",
            "text-sm font-medium bg-accent hover:bg-accent-hover text-white",
            "transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Search className="w-4 h-4" />
          )}
          {loading ? "Querying…" : "Search"}
        </button>
      </form>

      {error && (
        <p className="text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-3 animate-fade-in">
          <div className="space-y-2">
            {result.results.length === 0 ? (
              <p className="text-sm text-muted text-center py-4">
                No results found.
              </p>
            ) : (
              result.results.map((text, i) => (
                <div
                  key={i}
                  className="bg-surface border border-border rounded-xl px-4 py-3"
                >
                  <span className="text-xs text-accent font-mono mr-2">#{i + 1}</span>
                  <span className="text-sm text-white">{text}</span>
                </div>
              ))
            )}
          </div>

          {result.proof && (
            <div>
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setShowProof((p) => !p)}
                  className="text-xs text-accent hover:underline flex items-center gap-1"
                >
                  <ChevronDown
                    className={cn(
                      "w-3.5 h-3.5 transition-transform",
                      showProof && "rotate-180"
                    )}
                  />
                  {showProof ? "Hide" : "Show"} cryptographic proof
                </button>
                <button
                  onClick={handleCopyProof}
                  className="flex items-center gap-1 text-xs text-muted hover:text-white transition-colors"
                >
                  {copied ? (
                    <><Check className="w-3.5 h-3.5 text-success" /> Copied!</>
                  ) : (
                    <><Copy className="w-3.5 h-3.5" /> Copy proof JSON</>
                  )}
                </button>
              </div>
              {showProof && (
                <div className="mt-2">
                  <ProofCard proof={result.proof} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
