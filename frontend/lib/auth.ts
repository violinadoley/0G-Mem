"use client";

/**
 * auth.ts — MetaMask signature-based authentication helpers.
 * The user's private key NEVER leaves the browser. We only use `signMessage`
 * to produce a signature that proves wallet ownership.
 */

export interface AuthHeaders {
  "X-Wallet-Address": string;
  "X-Signature": string;
  "X-Auth-Message": string;
}

/**
 * Build the canonical authentication message that the user will sign.
 * Including the timestamp prevents replay attacks within a session.
 */
export function buildAuthMessage(walletAddress: string): string {
  const timestamp = Date.now();
  return `0G Mem authentication | Wallet: ${walletAddress} | Timestamp: ${timestamp}`;
}

/**
 * Sign the auth message via window.ethereum directly (bypasses wagmi's
 * chain-match validation, which is irrelevant for message signing).
 */
export async function getAuthHeaders(walletAddress: string): Promise<AuthHeaders> {
  const message = buildAuthMessage(walletAddress);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ethereum = (window as any).ethereum;
  if (!ethereum) throw new Error("No wallet detected. Please install MetaMask.");
  const signature = await ethereum.request({
    method: "personal_sign",
    params: [message, walletAddress],
  });
  return {
    "X-Wallet-Address": walletAddress,
    "X-Signature": signature,
    "X-Auth-Message": message,
  };
}
