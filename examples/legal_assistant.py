"""
Demo: Legal Contract Assistant with Verifiable Memory on 0G Testnet

Requirements:
    export AGENT_KEY=0x<your_private_key>   # funded from https://faucet.0g.ai

Optional (for better embeddings):
    export OPENAI_API_KEY=<key>

Run:
    python examples/legal_assistant.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ogmem import VerifiableMemory

AGENT_KEY = os.environ.get("AGENT_KEY", "")
if not AGENT_KEY:
    print("Error: AGENT_KEY not set.", file=sys.stderr)
    print("\n  export AGENT_KEY=0x<your_private_key>", file=sys.stderr)
    print("  Get testnet OG tokens: https://faucet.0g.ai", file=sys.stderr)
    sys.exit(1)


CONTRACT_CLAUSES = [
    "Section 3.1 Liability: The total liability of either party shall not exceed "
    "the fees paid in the twelve (12) months preceding the claim.",

    "Section 4.2 Termination: Either party may terminate this agreement with "
    "30 days written notice. Immediate termination is permitted in case of material breach.",

    "Section 5.1 Confidentiality: Both parties agree to keep confidential all "
    "proprietary information disclosed during the term and for 3 years thereafter.",

    "Section 6.3 Intellectual Property: All work product created by the service provider "
    "under this agreement shall be considered work-for-hire and owned by the client.",

    "Section 7.1 Governing Law: This agreement shall be governed by the laws of "
    "the State of Delaware, without regard to conflict of law provisions.",

    "Section 8.2 Force Majeure: Neither party shall be liable for delays caused by "
    "circumstances beyond their reasonable control, including acts of God, war, or pandemic.",

    "Section 9.1 Dispute Resolution: Any disputes shall first be subject to mediation. "
    "If mediation fails, disputes shall be resolved by binding arbitration in New York.",

    "Section 10.4 Amendment: This agreement may only be amended by written consent "
    "signed by authorized representatives of both parties.",
]

QUESTIONS = [
    "What is the liability cap?",
    "How much notice is required to terminate?",
    "How long does the confidentiality obligation last?",
    "Who owns the work product?",
    "Where will disputes be resolved?",
]


def main():
    print("=" * 60)
    print("0G Mem — Legal Assistant Demo")
    print("Verifiable AI Memory on 0G Labs Testnet")
    print("=" * 60)
    print()

    from eth_account import Account
    wallet_addr = Account.from_key(AGENT_KEY).address.lower()
    print(f"Wallet: {wallet_addr}")
    print(f"Network: 0G Galileo Testnet (chain ID 16602)")
    print()

    memory = VerifiableMemory(
        agent_id=wallet_addr,
        private_key=AGENT_KEY,
        network="0g-testnet",
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
    )

    print("Ingesting contract clauses into 0G Storage...")
    print()

    receipts = []
    for i, clause in enumerate(CONTRACT_CLAUSES):
        receipt = memory.add(clause, metadata={"section": f"clause_{i+1}"})
        receipts.append(receipt)
        print(f"  Clause {i+1} stored")
        print(f"    blob_id:     {receipt.blob_id[:20]}...")
        print(f"    merkle_root: {receipt.merkle_root[:20]}...")
        print(f"    da_tx_hash:  {receipt.da_tx_hash[:20]}...")
        print(f"    chain_tx:    {receipt.chain_tx_hash[:20]}...")
        print()

    print(f"{len(CONTRACT_CLAUSES)} clauses anchored on 0G Chain + DA")
    print()

    print("Answering questions with verifiable retrieval...")
    print()

    for question in QUESTIONS:
        results, proof = memory.query(question, top_k=2)

        print(f"Q: {question}")
        print(f"A: {results[0] if results else 'No relevant clause found'}")
        print()
        print(f"  Proof:")
        print(f"  query_hash:  {proof.query_hash[:20]}...")
        print(f"  retrieved:   {len(proof.blob_ids)} clauses")
        print(f"  scores:      {[round(s, 3) for s in proof.scores]}")
        print(f"  merkle_root: {proof.merkle_root[:20]}...")
        print(f"  da_read_tx:  {proof.da_read_tx[:20]}...")
        print(f"  chain_block: {proof.chain_block}")
        print()

        is_valid = memory.verify_proof(proof)
        print(f"  Proof valid: {is_valid}")
        print("-" * 60)
        print()

    print("Generating audit report...")
    report = memory.export_audit()
    print(report.summary())
    print(f"  Total operations: {report.total_writes + report.total_reads}")
    print(f"  Writes: {report.total_writes}  |  Reads: {report.total_reads}")
    print(f"  EU AI Act Articles: {', '.join(report.eu_ai_act_articles)}")
    print()

    with open("audit_report.json", "w") as f:
        f.write(report.to_json())
    print("  Saved: audit_report.json")
    print()
    print("=" * 60)
    print("Every answer is cryptographically provable on 0G Chain + DA.")
    print("=" * 60)


if __name__ == "__main__":
    main()
