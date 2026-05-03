"""
0G Mem Agent — Autonomous Multi-Agent Research Pipeline
========================================================

4 specialized agents collaborate autonomously via verifiable shared memory
on 0G decentralized infrastructure. Every step is cryptographically proven
on 0G Chain + 0G DA. Single command → complete research report.

Agents:
  OrchestratorAgent  — decomposes the task, coordinates the pipeline
  ResearcherAgent    — gathers information using web search tools
  AnalystAgent       — analyzes findings, draws strategic insights
  WriterAgent        — synthesizes everything into a final report

Usage:
    python examples/multi_agent_demo.py
    python examples/multi_agent_demo.py "Your research topic here"

Required env vars:
    AGENT_KEY           — 0G wallet private key (funded from faucet.0g.ai)
    ZEROG_SERVICE_URL   — 0G Compute inference endpoint
    ZEROG_API_KEY       — 0G Compute API key (app-sk-...)

Optional:
    ZEROG_MODEL         — model override (default: Qwen/Qwen2.5-7B-Instruct)
"""

import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from eth_account import Account

from ogmem.memory import VerifiableMemory
from ogmem.proof import WriteReceipt
from runtime.agent import AgentRuntime, AgentConfig, Turn
from runtime.tools import BUILTIN_TOOLS


# ── ANSI colours ───────────────────────────────────────────────────────────────

R   = "\033[0m"
B   = "\033[1m"
DIM = "\033[2m"
CYN = "\033[36m"    # orchestrator
GRN = "\033[32m"    # researcher
YLW = "\033[33m"    # analyst
MGT = "\033[35m"    # writer
RED = "\033[31m"
WHT = "\033[97m"

AGENT_CLR = {
    "orchestrator": CYN,
    "researcher":   GRN,
    "analyst":      YLW,
    "writer":       MGT,
}

AGENT_ICON = {
    "orchestrator": "⬡",
    "researcher":   "◎",
    "analyst":      "◈",
    "writer":       "◉",
}


# ── Display helpers ────────────────────────────────────────────────────────────

def hr(char="═", n=72):
    print(f"{B}{char * n}{R}")

def section(title: str, color: str = WHT):
    print()
    hr("─")
    print(f"{color}{B}  {title}{R}")
    hr("─")

def agent_log(name: str, msg: str):
    c = AGENT_CLR[name]
    icon = AGENT_ICON[name]
    print(f"{c}{B}{icon} {name.upper()}{R}  {msg}")

def proof_line(label: str, value: str, color: str = DIM):
    short = value[:24] + "..." if len(value) > 27 else value
    print(f"    {DIM}│{R}  {B}{label:<14}{R} {color}{short}{R}")

def print_receipt(r: WriteReceipt, color: str):
    proof_line("blob_id",     r.blob_id,        color)
    proof_line("merkle_root", r.merkle_root or "pending", color)
    proof_line("da_tx",       r.da_tx_hash or "pending",  color)
    proof_line("chain_tx",    r.chain_tx_hash or "pending", color)

def truncate(text: str, n: int = 500) -> str:
    return text[:n] + f"\n{DIM}  ... [{len(text) - n} more chars]{R}" if len(text) > n else text


# ── Validation ─────────────────────────────────────────────────────────────────

def validate():
    missing = [v for v in ("AGENT_KEY", "ZEROG_SERVICE_URL", "ZEROG_API_KEY")
               if not os.environ.get(v)]
    if missing:
        print(f"\n{RED}{B}✗ Missing required env vars:{R} {', '.join(missing)}\n")
        for v in missing:
            print(f"  export {v}=<value>")
        if "AGENT_KEY" in missing:
            print(f"\n  Get testnet OG tokens: https://faucet.0g.ai")
        sys.exit(1)


# ── Agent factory ──────────────────────────────────────────────────────────────

def make_agent(role: str, system_prompt: str, use_tools: bool = False) -> tuple[VerifiableMemory, AgentRuntime]:
    key  = os.environ["AGENT_KEY"]
    addr = Account.from_key(key).address.lower()

    mem = VerifiableMemory(
        agent_id=f"{addr}-{role}",
        private_key=key,
        network="0g-testnet",
    )

    cfg = AgentConfig(
        service_url   = os.environ["ZEROG_SERVICE_URL"],
        api_key       = os.environ["ZEROG_API_KEY"],
        model         = os.environ.get("ZEROG_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        system_prompt = system_prompt,
        tools         = list(BUILTIN_TOOLS) if use_tools else [],
        memory_top_k  = 3,
        max_tokens    = 2048,
        temperature   = 0.7,
    )

    return mem, AgentRuntime(memory=mem, config=cfg)


# ── System prompts ─────────────────────────────────────────────────────────────

ORCHESTRATOR_PROMPT = """You are an OrchestratorAgent managing an autonomous research pipeline.

Your job: analyze the research request and produce a clear, structured task plan.

Output format (plain text, no JSON required):
1. RESEARCH TASKS — specific questions and topics for the ResearcherAgent to investigate
2. ANALYSIS FOCUS — what patterns, risks, and opportunities the AnalystAgent should examine
3. REPORT STRUCTURE — the sections and format the WriterAgent should use

Be specific, actionable, and thorough. This plan drives the entire pipeline."""


RESEARCHER_PROMPT = """You are a ResearcherAgent with access to web search tools.

Your job: execute the research tasks assigned to you by the OrchestratorAgent.

Instructions:
- Use web_search to find current, factual information
- Run multiple searches to cover different angles
- Compile findings with specific facts, data points, and evidence
- Structure output clearly so the AnalystAgent can work with it

Be thorough and factual. Cite specific data where possible."""


ANALYST_PROMPT = """You are an AnalystAgent specializing in strategic analysis.

Your job: analyze the research findings provided and produce deep strategic insights.

Instructions:
- Identify key patterns and trends in the data
- Assess strengths, weaknesses, opportunities, and risks
- Draw meaningful conclusions supported by the evidence
- Highlight the most important strategic implications

Be rigorous, analytical, and insightful. Your analysis directly shapes the final report."""


WRITER_PROMPT = """You are a WriterAgent producing professional research reports.

Your job: synthesize the research findings and analysis into a compelling, well-structured report.

Required sections:
1. Executive Summary (3-5 sentences capturing the key takeaway)
2. Key Findings (bullet points of the most important facts)
3. Analysis & Insights (narrative based on the analyst's work)
4. Conclusions
5. Strategic Implications

Write clearly and professionally. This is the final deliverable."""


# ── Pipeline steps ─────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    topic:    str
    outputs:  dict[str, str]
    turns:    dict[str, Turn]
    duration: float


def run_orchestrator(runtime: AgentRuntime, topic: str) -> Turn:
    agent_log("orchestrator", "Decomposing research request...")
    return runtime.run(
        f"Research request: {topic}\n\n"
        f"Create a detailed task plan for the ResearcherAgent, AnalystAgent, and WriterAgent."
    )


def run_researcher(runtime: AgentRuntime, plan: str) -> Turn:
    agent_log("researcher", "Executing research tasks with web search...")
    return runtime.run(
        f"OrchestratorAgent task plan:\n\n{plan}\n\n"
        f"Execute the RESEARCH TASKS section. Use web_search for each topic. "
        f"Compile comprehensive findings with specific facts and data points."
    )


def run_analyst(runtime: AgentRuntime, plan: str, findings: str) -> Turn:
    agent_log("analyst", "Analyzing research findings...")
    return runtime.run(
        f"Orchestrator plan (context):\n\n{plan}\n\n"
        f"Research findings from ResearcherAgent:\n\n{findings}\n\n"
        f"Execute the ANALYSIS FOCUS section. Produce strategic insights, patterns, "
        f"risks, and opportunities backed by the research findings."
    )


def run_writer(runtime: AgentRuntime, topic: str, plan: str, findings: str, analysis: str) -> Turn:
    agent_log("writer", "Synthesizing final report...")
    return runtime.run(
        f"Research topic: {topic}\n\n"
        f"Orchestrator report structure:\n\n{plan}\n\n"
        f"Research findings:\n\n{findings}\n\n"
        f"Analysis & insights:\n\n{analysis}\n\n"
        f"Write the final report following the REPORT STRUCTURE. "
        f"Synthesize all information into a professional, compelling document."
    )


def attempt_shard_grant(mem_from: VerifiableMemory, receipts: list[WriteReceipt],
                        to_agent_id: str, _label: str, color: str):
    """Grant shard-level access on 0G Chain. Non-fatal if NFT not yet minted."""
    if not receipts:
        return
    blob_ids = [r.blob_id for r in receipts]
    print(f"    {DIM}│{R}  Granting shard access → {to_agent_id[:28]}...")
    try:
        tx = mem_from.grant_access(to_agent_id, shard_blob_ids=blob_ids)
        print(f"    {DIM}│{R}  {color}✓ Access granted{R}  chain_tx: {DIM}{tx[:24]}...{R}")
    except Exception as e:
        # NFT may not be minted yet — access control infrastructure is in place
        print(f"    {DIM}│  (shard grant pending NFT mint: {str(e)[:60]}){R}")


def print_turn_proof(name: str, turn: Turn):
    color = AGENT_CLR[name]
    print(f"\n  {color}{B}On-chain proof — {name.upper()}{R}")
    if turn.write_receipts:
        for r in turn.write_receipts:
            print_receipt(r, color)
    else:
        print(f"    {DIM}│  no write receipts{R}")
    if turn.da_hash:
        proof_line("da_turn_hash", turn.da_hash, DIM)
    print(f"    {DIM}│  latency: {turn.latency_ms}ms{R}")


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_pipeline(topic: str) -> PipelineResult:
    validate()
    t_start = time.time()

    # ── Header ────────────────────────────────────────────────────────────────
    hr()
    print(f"{B}  0G Mem Agent  ·  Autonomous Multi-Agent Research Pipeline{R}")
    print(f"{DIM}  0G Chain · 0G Storage · 0G DA · 0G Compute  ·  Galileo Testnet{R}")
    hr()
    print(f"\n  {B}Topic:{R} {topic}\n")

    # ── Phase 0: Initialise agents ────────────────────────────────────────────
    section("Phase 0 — Initialising Agent Network", WHT)

    agents: dict[str, tuple[VerifiableMemory, AgentRuntime]] = {
        "orchestrator": make_agent("orchestrator", ORCHESTRATOR_PROMPT, use_tools=False),
        "researcher":   make_agent("researcher",   RESEARCHER_PROMPT,   use_tools=True),
        "analyst":      make_agent("analyst",       ANALYST_PROMPT,      use_tools=False),
        "writer":       make_agent("writer",        WRITER_PROMPT,       use_tools=False),
    }

    for name, (mem, _) in agents.items():
        c = AGENT_CLR[name]
        print(f"  {c}✓{R}  {B}{name.capitalize()}Agent{R}  {DIM}{mem.agent_id}{R}")

    print(f"\n  {DIM}Network:  0G Galileo Testnet (Chain ID 16602){R}")
    print(f"  {DIM}Contract: 0xEDF95D9CFb157F5F38C1125B7DFB3968E05d2c4b  (MemoryRegistry){R}")
    print(f"  {DIM}Contract: 0x70ad85300f522A41689954a4153744BF6E57E488  (MemoryNFT){R}")

    outputs: dict[str, str] = {}
    turns:   dict[str, Turn] = {}

    # ── Phase 1: Orchestrator ─────────────────────────────────────────────────
    section("Phase 1 — OrchestratorAgent: Task Decomposition", CYN)

    mem_orch, rt_orch = agents["orchestrator"]
    turns["orchestrator"] = run_orchestrator(rt_orch, topic)
    outputs["orchestrator"] = turns["orchestrator"].assistant_reply

    print(f"\n{DIM}{truncate(outputs['orchestrator'], 600)}{R}\n")
    print_turn_proof("orchestrator", turns["orchestrator"])

    # Grant researcher access to orchestrator's blobs
    _, rt_res = agents["researcher"]
    mem_res, _ = agents["researcher"]
    attempt_shard_grant(mem_orch, turns["orchestrator"].write_receipts,
                        mem_res.agent_id, "ResearcherAgent", CYN)

    # ── Phase 2: Researcher ───────────────────────────────────────────────────
    section("Phase 2 — ResearcherAgent: Information Gathering", GRN)

    mem_res, rt_res = agents["researcher"]
    turns["researcher"] = run_researcher(rt_res, outputs["orchestrator"])
    outputs["researcher"] = turns["researcher"].assistant_reply

    if turns["researcher"].tool_calls:
        names = [tc.name for tc in turns["researcher"].tool_calls]
        agent_log("researcher", f"Tools invoked: {', '.join(names)}")

    print(f"\n{DIM}{truncate(outputs['researcher'], 700)}{R}\n")
    print_turn_proof("researcher", turns["researcher"])

    # Grant analyst access to researcher's blobs
    mem_ana, _ = agents["analyst"]
    attempt_shard_grant(mem_res, turns["researcher"].write_receipts,
                        mem_ana.agent_id, "AnalystAgent", GRN)

    # ── Phase 3: Analyst ──────────────────────────────────────────────────────
    section("Phase 3 — AnalystAgent: Strategic Analysis", YLW)

    mem_ana, rt_ana = agents["analyst"]
    turns["analyst"] = run_analyst(rt_ana, outputs["orchestrator"], outputs["researcher"])
    outputs["analyst"] = turns["analyst"].assistant_reply

    print(f"\n{DIM}{truncate(outputs['analyst'], 700)}{R}\n")
    print_turn_proof("analyst", turns["analyst"])

    # Grant writer access to analyst's blobs
    mem_wri, _ = agents["writer"]
    attempt_shard_grant(mem_ana, turns["analyst"].write_receipts,
                        mem_wri.agent_id, "WriterAgent", YLW)

    # ── Phase 4: Writer ───────────────────────────────────────────────────────
    section("Phase 4 — WriterAgent: Final Report", MGT)

    mem_wri, rt_wri = agents["writer"]
    turns["writer"] = run_writer(
        rt_wri, topic,
        outputs["orchestrator"],
        outputs["researcher"],
        outputs["analyst"],
    )
    outputs["writer"] = turns["writer"].assistant_reply

    print_turn_proof("writer", turns["writer"])

    # ── Final Report ──────────────────────────────────────────────────────────
    hr()
    print(f"{B}  FINAL REPORT{R}")
    hr()
    print()
    print(outputs["writer"])
    print()

    # ── Proof Trail ───────────────────────────────────────────────────────────
    hr("─")
    print(f"{B}  COMPLETE ON-CHAIN PROOF TRAIL{R}")
    print(f"{DIM}  Every agent action is independently verifiable on 0G Chain + 0G DA{R}")
    hr("─")

    total_writes = 0
    for name in ("orchestrator", "researcher", "analyst", "writer"):
        turn = turns[name]
        c = AGENT_CLR[name]
        icon = AGENT_ICON[name]
        recs = turn.write_receipts
        total_writes += len(recs)
        print(f"\n  {c}{B}{icon} {name.upper()}  ({len(recs)} write(s)){R}")
        if recs:
            for r in recs:
                print(f"    blob_id:     {r.blob_id}")
                print(f"    merkle_root: {r.merkle_root or 'pending'}")
                print(f"    da_tx:       {r.da_tx_hash or 'pending'}")
                print(f"    chain_tx:    {r.chain_tx_hash or 'pending'}")
                print()
        if turn.da_hash:
            print(f"    turn_da_hash: {turn.da_hash}")
        print(f"    latency:     {turn.latency_ms}ms")

    duration = time.time() - t_start
    print()
    hr("─")
    print(f"  {B}Summary{R}")
    print(f"    Agents:        4  (orchestrator · researcher · analyst · writer)")
    print(f"    Memory writes: {total_writes}")
    print(f"    Tool calls:    {sum(len(t.tool_calls) for t in turns.values())}")
    print(f"    Total time:    {duration:.1f}s")
    print(f"    Network:       0G Galileo Testnet  (Chain ID 16602)")
    hr("─")
    print(f"\n  {GRN}{B}✓ Pipeline complete.{R}  All agent actions are provable on 0G Chain.\n")

    # ── Save to file ──────────────────────────────────────────────────────────
    out_path = Path("multi_agent_report.md")
    with open(out_path, "w") as f:
        f.write(f"# Research Report\n\n**Topic:** {topic}\n\n")
        f.write(f"*Generated by 0G Mem Agent Autonomous Multi-Agent Pipeline*\n\n---\n\n")
        f.write(outputs["writer"])
        f.write("\n\n---\n\n## On-Chain Proof Trail\n\n")
        f.write("Every agent action below is independently verifiable on 0G Chain + 0G DA.\n\n")
        for name in ("orchestrator", "researcher", "analyst", "writer"):
            turn = turns[name]
            f.write(f"### {name.capitalize()}Agent\n\n")
            for r in turn.write_receipts:
                f.write(f"| Field | Value |\n|---|---|\n")
                f.write(f"| blob_id | `{r.blob_id}` |\n")
                f.write(f"| merkle_root | `{r.merkle_root or 'pending'}` |\n")
                f.write(f"| da_tx | `{r.da_tx_hash or 'pending'}` |\n")
                f.write(f"| chain_tx | `{r.chain_tx_hash or 'pending'}` |\n\n")
            if turn.da_hash:
                f.write(f"**Turn DA hash:** `{turn.da_hash}`\n\n")

    print(f"  {DIM}Report saved → {out_path}{R}\n")

    return PipelineResult(
        topic=topic,
        outputs=outputs,
        turns=turns,
        duration=duration,
    )


# ── Entry point ────────────────────────────────────────────────────────────────

DEFAULT_TOPIC = (
    "0G Labs decentralized AI infrastructure: "
    "capabilities, competitive positioning, and strategic opportunities "
    "in the autonomous agent ecosystem"
)

if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_TOPIC
    run_pipeline(topic)
