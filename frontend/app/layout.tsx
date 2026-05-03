import type { Metadata } from "next";
import "./globals.css";
import Web3Provider from "@/providers/Web3Provider";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "0G Mem — Verifiable AI Memory",
  description:
    "Provable. Pluggable. Owned by you. On-chain verifiable AI memory powered by 0G Labs.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%238B5CF6'/><text x='50%25' y='55%25' dominant-baseline='middle' text-anchor='middle' fill='white' font-size='14' font-weight='bold' font-family='Inter,sans-serif'>0G</text></svg>",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-white antialiased min-h-screen">
        <Web3Provider>
          <Navbar />
          <main className="min-h-[calc(100vh-4rem)]">{children}</main>
        </Web3Provider>
      </body>
    </html>
  );
}
