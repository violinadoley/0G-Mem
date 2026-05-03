"use client";

import { useAccount } from "wagmi";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Brain } from "lucide-react";
import AddMemoryForm from "@/components/AddMemoryForm";
import QueryForm from "@/components/QueryForm";
import MemoryFeed from "@/components/MemoryFeed";
import { AddResponse } from "@/lib/api";

export default function MemoryPage() {
  const { address, isConnected } = useAccount();
  const router = useRouter();
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    if (!isConnected) {
      router.replace("/");
    }
  }, [isConnected, router]);

  if (!isConnected || !address) {
    return null;
  }

  const handleMemoryAdded = (_res: AddResponse) => {
    setRefreshTrigger((t) => t + 1);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-accent/10 border border-accent/20 rounded-xl flex items-center justify-center">
          <Brain className="w-5 h-5 text-accent" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-white">Memory Explorer</h1>
          <p className="text-xs text-muted font-mono mt-0.5 truncate max-w-xs">{address}</p>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Left column — Add + Query */}
        <div className="space-y-6">
          {/* Add Memory */}
          <div className="bg-surface-raised border border-border rounded-xl p-6">
            <h2 className="text-sm font-semibold text-white mb-4">Add Memory</h2>
            <AddMemoryForm agentId={address} onSuccess={handleMemoryAdded} />
          </div>

          {/* Query Memory */}
          <div className="bg-surface-raised border border-border rounded-xl p-6">
            <h2 className="text-sm font-semibold text-white mb-4">Query Memory</h2>
            <QueryForm agentId={address} />
          </div>
        </div>

        {/* Right column — Chain state */}
        <div className="bg-surface-raised border border-border rounded-xl p-6">
          <MemoryFeed agentId={address} refreshTrigger={refreshTrigger} />
        </div>
      </div>
    </div>
  );
}
