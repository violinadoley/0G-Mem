"use client";

import { useState } from "react";
import { PlusCircle, Loader2 } from "lucide-react";
import { addMemory, AddResponse } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface AddMemoryFormProps {
  agentId: string;
  onSuccess?: (res: AddResponse) => void;
}

export default function AddMemoryForm({ agentId, onSuccess }: AddMemoryFormProps) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<AddResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const authHeaders = await getAuthHeaders(agentId);
      const res = await addMemory(agentId, text.trim(), {}, authHeaders);
      setSuccess(res);
      setText("");
      onSuccess?.(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add memory.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Enter a memory to store on-chain…"
        rows={5}
        disabled={loading}
        className={cn(
          "w-full bg-surface border border-border rounded-xl px-4 py-3",
          "text-white placeholder:text-muted text-sm resize-none",
          "focus:outline-none focus:border-accent transition-colors",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      />

      {error && (
        <p className="text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {success && (
        <div className="text-xs text-success bg-success/10 border border-success/20 rounded-lg px-3 py-2 space-y-0.5">
          <p className="font-medium">Memory stored on-chain</p>
          <p className="text-muted font-mono truncate">Blob: {success.blob_id}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={loading || !text.trim()}
        className={cn(
          "w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl",
          "text-sm font-medium bg-accent hover:bg-accent-hover text-white",
          "transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <PlusCircle className="w-4 h-4" />
        )}
        {loading ? "Signing & Storing…" : "Add Memory"}
      </button>
    </form>
  );
}
