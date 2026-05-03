import { http, createConfig } from "wagmi";
import { defineChain } from "viem";
import { injected } from "wagmi/connectors";

// 0G Galileo Testnet (v3) — chain_id 16602
export const zgGalileo = defineChain({
  id: 16602,
  name: "0G Galileo Testnet",
  nativeCurrency: { name: "A0GI", symbol: "A0GI", decimals: 18 },
  rpcUrls: {
    default: { http: ["https://evmrpc-testnet.0g.ai"] },
  },
  blockExplorers: {
    default: {
      name: "0G Explorer",
      url: "https://chainscan-galileo.0g.ai",
    },
  },
  testnet: true,
});

export const wagmiConfig = createConfig({
  chains: [zgGalileo],
  connectors: [injected()],
  transports: {
    [zgGalileo.id]: http(),
  },
  ssr: true,
});

declare module "wagmi" {
  interface Register {
    config: typeof wagmiConfig;
  }
}
