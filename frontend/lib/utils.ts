/**
 * Utility helpers — formatting, clsx merge, clipboard.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a unix timestamp (seconds) as "Apr 15, 2026 at 9:41 PM"
 */
export function formatTimestamp(unixSeconds: number): string {
  const date = new Date(unixSeconds * 1000);
  return format(date, "MMM d, yyyy 'at' h:mm a");
}

/**
 * Truncate a hex hash/address to first 20 chars + "..."
 */
export function truncateHash(hash: string, chars = 20): string {
  if (!hash) return "—";
  if (hash.length <= chars) return hash;
  return `${hash.slice(0, chars)}...`;
}

/**
 * Copy text to clipboard. Returns true on success.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
