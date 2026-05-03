"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { truncateHash, copyToClipboard, cn } from "@/lib/utils";

interface HashDisplayProps {
  hash: string;
  chars?: number;
  className?: string;
  mono?: boolean;
}

export default function HashDisplay({
  hash,
  chars = 20,
  className,
  mono = true,
}: HashDisplayProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const ok = await copyToClipboard(hash);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  if (!hash || hash === "—") {
    return <span className={cn("text-muted text-sm", className)}>—</span>;
  }

  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span
        className={cn(
          "text-sm",
          mono && "font-mono",
          "text-muted"
        )}
        title={hash}
      >
        {truncateHash(hash, chars)}
      </span>
      <button
        onClick={handleCopy}
        className="text-muted hover:text-white transition-colors flex-shrink-0"
        title="Copy to clipboard"
      >
        {copied ? (
          <Check className="w-3.5 h-3.5 text-success" />
        ) : (
          <Copy className="w-3.5 h-3.5" />
        )}
      </button>
    </span>
  );
}
