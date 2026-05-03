"use client";

/**
 * api.ts — Fully-typed fetch client for the 0G Mem FastAPI backend.
 * All authenticated endpoints accept X-Wallet-Address, X-Signature, X-Auth-Message headers.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AddResponse {
  agent_id: string;
  blob_id: string;
  merkle_root: string;
  da_tx_hash: string;
  chain_tx_hash: string;
  timestamp: number;
  encrypted: boolean;
}

export interface QueryResult {
  text: string;
  score?: number;
}

export interface QueryProof {
  agent_id: string;
  query_hash: string;
  blob_ids: string[];
  scores: number[];
  merkle_proofs: Record<string, unknown>[];
  merkle_root: string;
  da_read_tx: string;
  chain_block: number;
  timestamp: number;
  verified?: boolean;
}

export interface QueryResponse {
  results: string[];
  proof: QueryProof;
}

export interface StateResponse {
  agent_id: string;
  merkle_root: string;
  block_number: number;
  da_tx_hash: string;
  timestamp: number;
  memory_count: number;
  nft_token_id: number;
}

export interface AuditEntry {
  op_type: "write" | "read";
  timestamp: number;
  agent_id: string;
  blob_id?: string;
  content_preview?: string;
  merkle_root?: string;
  da_tx_hash?: string;
  chain_tx_hash?: string;
  query_hash?: string;
  query_preview?: string;
  retrieved_blob_ids?: string[];
  similarity_scores?: number[];
  da_read_tx?: string;
  merkle_root_used?: string;
}

export interface AuditReport {
  agent_id: string;
  generated_at: number;
  operations: AuditEntry[];
  total_writes: number;
  total_reads: number;
}

export interface VerifyResponse {
  valid: boolean;
  message: string;
}

export interface GrantResponse {
  chain_tx_hash: string;
  agent_address: string;
  access_type: "full" | "shard";
}

export interface RevokeResponse {
  chain_tx_hash: string;
  agent_address: string;
}

export interface MintResponse {
  chain_tx_hash: string;
  token_id: number;
  owner: string;
}

// ─── Auth header type ─────────────────────────────────────────────────────────

export interface AuthHeaders {
  "X-Wallet-Address": string;
  "X-Signature": string;
  "X-Auth-Message": string;
}

// ─── Internal fetch helper ────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit & { authHeaders?: AuthHeaders } = {}
): Promise<T> {
  const { authHeaders, ...rest } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(authHeaders ?? {}),
    ...(rest.headers as Record<string, string> | undefined ?? {}),
  };

  const res = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

// ─── Memory endpoints ─────────────────────────────────────────────────────────

export async function addMemory(
  agentId: string,
  text: string,
  metadata: Record<string, unknown>,
  authHeaders: AuthHeaders
): Promise<AddResponse> {
  return apiFetch<AddResponse>(`/memory/${agentId}/add`, {
    method: "POST",
    body: JSON.stringify({ text, metadata }),
    authHeaders,
  });
}

export async function queryMemory(
  agentId: string,
  text: string,
  topK: number,
  authHeaders: AuthHeaders
): Promise<QueryResponse> {
  return apiFetch<QueryResponse>(`/memory/${agentId}/query`, {
    method: "POST",
    body: JSON.stringify({ text, top_k: topK }),
    authHeaders,
  });
}

export async function getMemoryState(
  agentId: string,
  authHeaders: AuthHeaders
): Promise<StateResponse> {
  return apiFetch<StateResponse>(`/memory/${agentId}/state`, {
    method: "GET",
    authHeaders,
  });
}

export async function getAuditReport(
  agentId: string,
  authHeaders: AuthHeaders,
  fromBlock = 0,
  toBlock = -1
): Promise<AuditReport> {
  return apiFetch<AuditReport>(
    `/memory/${agentId}/audit?from_block=${fromBlock}&to_block=${toBlock}`,
    { method: "GET", authHeaders }
  );
}

export async function verifyProof(
  agentId: string,
  proof: QueryProof
): Promise<VerifyResponse> {
  return apiFetch<VerifyResponse>(`/memory/${agentId}/verify`, {
    method: "POST",
    body: JSON.stringify({ proof }),
  });
}

export async function grantAccess(
  agentId: string,
  agentAddress: string,
  shardBlobIds: string[],
  authHeaders: AuthHeaders
): Promise<GrantResponse> {
  return apiFetch<GrantResponse>(`/memory/${agentId}/grant`, {
    method: "POST",
    body: JSON.stringify({ agent_address: agentAddress, shard_blob_ids: shardBlobIds }),
    authHeaders,
  });
}

export async function revokeAccess(
  agentId: string,
  agentAddress: string,
  authHeaders: AuthHeaders
): Promise<RevokeResponse> {
  return apiFetch<RevokeResponse>(`/memory/${agentId}/revoke`, {
    method: "POST",
    body: JSON.stringify({ agent_address: agentAddress }),
    authHeaders,
  });
}

// ─── NFT endpoints ────────────────────────────────────────────────────────────

export async function mintNFT(authHeaders: AuthHeaders): Promise<MintResponse> {
  return apiFetch<MintResponse>("/nft/mint", {
    method: "POST",
    authHeaders,
  });
}
