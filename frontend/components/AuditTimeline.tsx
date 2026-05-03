"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw, Loader2, FileText, Search } from "lucide-react";
import { getAuditReport, AuditEntry, AuditReport } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import HashDisplay from "./HashDisplay";
import { formatTimestamp, cn } from "@/lib/utils";

interface AuditTimelineProps {
  agentId: string;
}

export default function AuditTimeline({ agentId }: AuditTimelineProps) {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const authHeaders = await getAuthHeaders(agentId);
      const r = await getAuditReport(agentId, authHeaders);
      setReport(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit.");
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Audit Timeline</h2>
          {report && (
            <p className="text-xs text-muted mt-0.5">
              {report.total_writes} writes · {report.total_reads} reads ·
              Generated {formatTimestamp(report.generated_at)}
            </p>
          )}
        </div>
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
        <p className="text-sm text-error bg-error/10 border border-error/20 rounded-lg px-4 py-3">
          {error}
        </p>
      )}

      {loading && !report && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-muted" />
        </div>
      )}

      {report && report.operations.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <FileText className="w-10 h-10 text-muted mb-3" />
          <p className="text-sm text-muted">No audit entries yet.</p>
          <p className="text-xs text-muted mt-1">
            Store or query memories to generate an audit trail.
          </p>
        </div>
      )}

      {report && report.operations.length > 0 && (
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />

          <div className="space-y-0">
            {[...report.operations]
              .sort((a, b) => b.timestamp - a.timestamp)
              .map((entry, i) => (
                <AuditEntryRow key={i} entry={entry} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AuditEntryRow({ entry }: { entry: AuditEntry }) {
  const isWrite = entry.op_type === "write";

  return (
    <div className="flex gap-4 pb-4 animate-fade-in">
      {/* Icon */}
      <div
        className={cn(
          "relative z-10 flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center",
          isWrite
            ? "bg-accent/10 border border-accent/30"
            : "bg-blue-500/10 border border-blue-500/30"
        )}
      >
        {isWrite ? (
          <FileText className="w-4 h-4 text-accent" />
        ) : (
          <Search className="w-4 h-4 text-blue-400" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 bg-surface-raised border border-border rounded-xl p-4 min-w-0">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <span
            className={cn(
              "text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full",
              isWrite
                ? "bg-accent/10 text-accent"
                : "bg-blue-500/10 text-blue-400"
            )}
          >
            {isWrite ? "Write" : "Read"}
          </span>
          <span className="text-xs text-muted">
            {formatTimestamp(entry.timestamp)}
          </span>
        </div>

        <div className="space-y-1.5 text-xs">
          {entry.blob_id && (
            <div className="flex items-center gap-2">
              <span className="text-muted w-24 flex-shrink-0">Blob ID</span>
              <HashDisplay hash={entry.blob_id} chars={24} />
            </div>
          )}
          {entry.content_preview && (
            <div className="flex items-center gap-2">
              <span className="text-muted w-24 flex-shrink-0">Content</span>
              <span className="text-muted truncate">{entry.content_preview}</span>
            </div>
          )}
          {entry.query_hash && (
            <div className="flex items-center gap-2">
              <span className="text-muted w-24 flex-shrink-0">Query Hash</span>
              <HashDisplay hash={entry.query_hash} chars={24} />
            </div>
          )}
          {entry.query_preview && (
            <div className="flex items-center gap-2">
              <span className="text-muted w-24 flex-shrink-0">Query</span>
              <span className="text-muted truncate">{entry.query_preview}</span>
            </div>
          )}
          {(entry.merkle_root || entry.merkle_root_used) && (
            <div className="flex items-center gap-2">
              <span className="text-muted w-24 flex-shrink-0">Merkle Root</span>
              <HashDisplay hash={(entry.merkle_root || entry.merkle_root_used)!} chars={24} />
            </div>
          )}
          {(entry.da_tx_hash || entry.da_read_tx) && (
            <div className="flex items-center gap-2">
              <span className="text-muted w-24 flex-shrink-0">DA Tx</span>
              <HashDisplay hash={(entry.da_tx_hash || entry.da_read_tx)!} chars={24} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
