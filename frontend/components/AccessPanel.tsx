"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, Award, UserPlus, UserMinus, RefreshCw, ShieldCheck } from "lucide-react";
import { mintNFT, grantAccess, revokeAccess, getMemoryState, StateResponse, MintResponse, GrantResponse, RevokeResponse } from "@/lib/api";
import { getAuthHeaders } from "@/lib/auth";
import HashDisplay from "./HashDisplay";
import { cn } from "@/lib/utils";

interface AccessPanelProps {
  agentId: string;
}

export default function AccessPanel({ agentId }: AccessPanelProps) {
  const [state, setState] = useState<StateResponse | null>(null);
  const [stateLoading, setStateLoading] = useState(true);

  // Mint
  const [mintLoading, setMintLoading] = useState(false);
  const [mintResult, setMintResult] = useState<MintResponse | null>(null);
  const [mintError, setMintError] = useState<string | null>(null);

  // Grant
  const [grantAddress, setGrantAddress] = useState("");
  const [grantBlobIds, setGrantBlobIds] = useState("");
  const [grantLoading, setGrantLoading] = useState(false);
  const [grantResult, setGrantResult] = useState<GrantResponse | null>(null);
  const [grantError, setGrantError] = useState<string | null>(null);

  // Revoke
  const [revokeAddress, setRevokeAddress] = useState("");
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [revokeResult, setRevokeResult] = useState<RevokeResponse | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const loadState = useCallback(async () => {
    setStateLoading(true);
    try {
      const authHeaders = await getAuthHeaders(agentId);
      const s = await getMemoryState(agentId, authHeaders);
      setState(s);
    } catch {
      // Non-fatal
    } finally {
      setStateLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const handleMint = async () => {
    setMintLoading(true);
    setMintError(null);
    setMintResult(null);
    try {
      const authHeaders = await getAuthHeaders(agentId);
      const res = await mintNFT(authHeaders);
      setMintResult(res);
      loadState();
    } catch (err) {
      setMintError(err instanceof Error ? err.message : "Mint failed.");
    } finally {
      setMintLoading(false);
    }
  };

  const handleGrant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!grantAddress.trim()) return;
    setGrantLoading(true);
    setGrantError(null);
    setGrantResult(null);
    try {
      const authHeaders = await getAuthHeaders(agentId);
      const blobIds = grantBlobIds
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await grantAccess(agentId, grantAddress.trim(), blobIds, authHeaders);
      setGrantResult(res);
      setGrantAddress("");
      setGrantBlobIds("");
    } catch (err) {
      setGrantError(err instanceof Error ? err.message : "Grant failed.");
    } finally {
      setGrantLoading(false);
    }
  };

  const handleRevoke = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!revokeAddress.trim()) return;
    setRevokeLoading(true);
    setRevokeError(null);
    setRevokeResult(null);
    try {
      const authHeaders = await getAuthHeaders(agentId);
      const res = await revokeAccess(agentId, revokeAddress.trim(), authHeaders);
      setRevokeResult(res);
      setRevokeAddress("");
    } catch (err) {
      setRevokeError(err instanceof Error ? err.message : "Revoke failed.");
    } finally {
      setRevokeLoading(false);
    }
  };

  const inputClass = cn(
    "w-full bg-surface border border-border rounded-xl px-4 py-2.5",
    "text-white placeholder:text-muted text-sm",
    "focus:outline-none focus:border-accent transition-colors"
  );

  const btnClass = cn(
    "flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl",
    "text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
  );

  return (
    <div className="space-y-6">
      {/* NFT Status Card */}
      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Award className="w-4 h-4 text-accent" />
            Memory NFT
          </h3>
          <button
            onClick={loadState}
            disabled={stateLoading}
            className="text-muted hover:text-white transition-colors"
          >
            <RefreshCw className={cn("w-4 h-4", stateLoading && "animate-spin")} />
          </button>
        </div>

        {stateLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="w-5 h-5 animate-spin text-muted" />
          </div>
        ) : state ? (
          <div className="space-y-2">
            {state.nft_token_id > 0 ? (
              <div className="flex items-center gap-2 text-success text-sm">
                <ShieldCheck className="w-4 h-4" />
                <span>Minted — Token ID #{state.nft_token_id}</span>
              </div>
            ) : (
              <p className="text-sm text-muted">No NFT minted yet.</p>
            )}
          </div>
        ) : null}

        {mintResult && (
          <div className="mt-3 text-xs text-success bg-success/10 border border-success/20 rounded-lg px-3 py-2">
            <p className="font-medium">NFT Minted — Token #{mintResult.token_id}</p>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-muted">Tx:</span>
              <HashDisplay hash={mintResult.chain_tx_hash} chars={20} />
            </div>
          </div>
        )}

        {mintError && (
          <p className="mt-3 text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
            {mintError}
          </p>
        )}

        {(!state || state.nft_token_id === 0) && !mintResult && (
          <button
            onClick={handleMint}
            disabled={mintLoading}
            className={cn(btnClass, "w-full mt-4 bg-accent hover:bg-accent-hover text-white")}
          >
            {mintLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Award className="w-4 h-4" />
            )}
            {mintLoading ? "Minting…" : "Mint Memory NFT"}
          </button>
        )}
      </div>

      {/* Grant Access */}
      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-4">
          <UserPlus className="w-4 h-4 text-accent" />
          Grant Access
        </h3>
        <form onSubmit={handleGrant} className="space-y-3">
          <input
            value={grantAddress}
            onChange={(e) => setGrantAddress(e.target.value)}
            placeholder="Agent wallet address (0x…)"
            className={inputClass}
            disabled={grantLoading}
          />
          <input
            value={grantBlobIds}
            onChange={(e) => setGrantBlobIds(e.target.value)}
            placeholder="Blob IDs (comma-separated, leave blank for full access)"
            className={inputClass}
            disabled={grantLoading}
          />

          {grantError && (
            <p className="text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
              {grantError}
            </p>
          )}
          {grantResult && (
            <div className="text-xs text-success bg-success/10 border border-success/20 rounded-lg px-3 py-2">
              <p className="font-medium">
                {grantResult.access_type === "full" ? "Full" : "Shard"} access granted
              </p>
              <div className="flex items-center gap-1 mt-0.5">
                <span className="text-muted">Tx:</span>
                <HashDisplay hash={grantResult.chain_tx_hash} chars={20} />
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={grantLoading || !grantAddress.trim()}
            className={cn(btnClass, "w-full bg-accent hover:bg-accent-hover text-white")}
          >
            {grantLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <UserPlus className="w-4 h-4" />
            )}
            {grantLoading ? "Granting…" : "Grant Access"}
          </button>
        </form>
      </div>

      {/* Revoke Access */}
      <div className="bg-surface-raised border border-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2 mb-4">
          <UserMinus className="w-4 h-4 text-error" />
          Revoke Access
        </h3>
        <form onSubmit={handleRevoke} className="space-y-3">
          <input
            value={revokeAddress}
            onChange={(e) => setRevokeAddress(e.target.value)}
            placeholder="Agent wallet address (0x…)"
            className={inputClass}
            disabled={revokeLoading}
          />

          {revokeError && (
            <p className="text-xs text-error bg-error/10 border border-error/20 rounded-lg px-3 py-2">
              {revokeError}
            </p>
          )}
          {revokeResult && (
            <div className="text-xs text-success bg-success/10 border border-success/20 rounded-lg px-3 py-2">
              <p className="font-medium">Access revoked</p>
              <div className="flex items-center gap-1 mt-0.5">
                <span className="text-muted">Tx:</span>
                <HashDisplay hash={revokeResult.chain_tx_hash} chars={20} />
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={revokeLoading || !revokeAddress.trim()}
            className={cn(
              btnClass,
              "w-full bg-error/10 hover:bg-error/20 text-error border border-error/20"
            )}
          >
            {revokeLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <UserMinus className="w-4 h-4" />
            )}
            {revokeLoading ? "Revoking…" : "Revoke Access"}
          </button>
        </form>
      </div>
    </div>
  );
}
