"""
Agent Runtime — memory-augmented inference on 0G Compute.

Pipeline per turn:
  1. Retrieve relevant memories (VerifiableMemory.query)
  2. Build system prompt (persona + retrieved context)
  3. Inference via 0G Compute (ZeroGInferenceClient)
  4. Parse tool calls → execute tools → second inference pass (if tools used)
  5. Write interaction to memory (session batched → 1 chain tx)
  6. Return Turn with full trace
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional

from ogmem.inference import ChatMessage, ZeroGInferenceClient
from ogmem.memory import VerifiableMemory
from ogmem.proof import WriteReceipt
from .tools import BUILTIN_TOOLS, Tool, ToolResult


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """Runtime configuration."""
    # Inference
    service_url: str = ""           # 0G Compute service URL
    api_key: str = ""               # app-sk-<SECRET>
    model: str = "Qwen/Qwen2.5-7B-Instruct"
    max_tokens: int = 2048
    temperature: float = 0.7

    # Memory
    memory_top_k: int = 5           # how many memories to retrieve per turn
    memory_types: Optional[list[str]] = None  # None = all types

    # Agent persona
    system_prompt: str = (
        "You are a helpful AI assistant with verifiable, persistent memory. "
        "You remember past conversations and can use tools to answer questions. "
        "Always be concise and accurate."
    )

    # Tools
    tools: list[Tool] = field(default_factory=lambda: list(BUILTIN_TOOLS))
    max_tool_rounds: int = 3        # max sequential tool-call iterations


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Turn:
    """A single agent turn with full provenance."""
    user_message: str
    assistant_reply: str
    retrieved_memories: list[str]
    tool_calls: list[ToolCall]
    tool_results: list[ToolResult]
    write_receipts: list[WriteReceipt]
    latency_ms: int
    timestamp: int = field(default_factory=lambda: int(time.time()))
    da_hash: str = ""   # 0G DA hash of the full turn trace (empty if DA unavailable)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
            "user_message": self.user_message,
            "assistant_reply": self.assistant_reply,
            "retrieved_memories": self.retrieved_memories,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in self.tool_calls
            ],
            "tool_results": [
                {"name": tr.name, "output": tr.output, "error": tr.error}
                for tr in self.tool_results
            ],
            "write_receipts": [
                {"blob_id": r.blob_id, "chain_tx_hash": r.chain_tx_hash}
                for r in self.write_receipts
            ],
        }


# ── AgentRuntime ───────────────────────────────────────────────────────────────

class AgentRuntime:
    """
    Memory-augmented agent runtime wired to 0G Compute + VerifiableMemory.

    Quick start:
        mem = VerifiableMemory(agent_id="my-agent", private_key="0x...", network="0g-testnet")
        cfg = AgentConfig(service_url="https://...", api_key="app-sk-...")
        agent = AgentRuntime(memory=mem, config=cfg)
        turn = agent.run("What did we talk about yesterday?")
        print(turn.assistant_reply)
    """

    def __init__(self, memory: VerifiableMemory, config: Optional[AgentConfig] = None):
        self.memory = memory
        self.config = config or AgentConfig()
        self._inference = ZeroGInferenceClient(
            service_url=self.config.service_url,
            api_key=self.config.api_key,
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        self._tool_map: dict[str, Tool] = {t.name: t for t in self.config.tools}
        self._history: list[ChatMessage] = []   # in-memory conversation history
        # DA client — initialised lazily from memory's internal DA client
        self._da = getattr(memory, "_da", None)

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, user_message: str) -> Turn:
        """Process a user message and return a Turn with the full trace."""
        t0 = time.time()

        # 1. Retrieve relevant memories
        memories, _ = self.memory.query(
            user_message,
            top_k=self.config.memory_top_k,
            memory_types=self.config.memory_types,
        )

        # 2. Build messages
        system = self._build_system_prompt(memories)
        self._history.append(ChatMessage("user", user_message))

        # 3. Inference (with optional tool loop)
        tool_calls_all: list[ToolCall] = []
        tool_results_all: list[ToolResult] = []
        messages = list(self._history)

        reply = self._inference_with_tools(
            system=system,
            messages=messages,
            tool_calls_out=tool_calls_all,
            tool_results_out=tool_results_all,
        )

        self._history.append(ChatMessage("assistant", reply))

        # 4. Persist interaction to memory (1 chain tx via session)
        receipts: list[WriteReceipt] = []
        with self.memory.session() as sess:
            r1 = sess.add(f"User: {user_message}", memory_type="episodic")
            r2 = sess.add(f"Assistant: {reply}", memory_type="episodic")
            receipts.extend([r1, r2])

        latency_ms = int((time.time() - t0) * 1000)

        turn = Turn(
            user_message=user_message,
            assistant_reply=reply,
            retrieved_memories=memories,
            tool_calls=tool_calls_all,
            tool_results=tool_results_all,
            write_receipts=receipts,
            latency_ms=latency_ms,
        )

        # 5. Log full turn trace to 0G DA (non-blocking; failures are silent)
        turn.da_hash = self._log_turn_to_da(turn)

        return turn

    def _log_turn_to_da(self, turn: Turn) -> str:
        """Post the full turn execution trace to 0G DA. Returns da_hash or '' on failure."""
        if self._da is None:
            return ""
        try:
            wr = turn.write_receipts
            merkle_root = wr[0].merkle_root if wr else ""
            write_blob_ids = [r.blob_id for r in wr]
            tool_calls_data = [
                {"name": tc.name, "arguments": tc.arguments}
                for tc in turn.tool_calls
            ]
            return self._da.post_agent_turn(
                agent_id=self.memory.agent_id,
                user_message=turn.user_message,
                assistant_reply=turn.assistant_reply,
                memories_retrieved=turn.retrieved_memories,
                tool_calls=tool_calls_data,
                write_blob_ids=write_blob_ids,
                merkle_root=merkle_root,
                latency_ms=turn.latency_ms,
            )
        except Exception:
            return ""

    def stream(self, user_message: str) -> Iterator[str]:
        """
        Stream the assistant reply token-by-token.
        Memory retrieval and persistence still happen (non-streaming).
        Yields text chunks; after the last chunk a Turn is NOT returned
        (use run() if you need full provenance).
        """
        memories, _ = self.memory.query(
            user_message,
            top_k=self.config.memory_top_k,
            memory_types=self.config.memory_types,
        )
        system = self._build_system_prompt(memories)
        self._history.append(ChatMessage("user", user_message))
        messages = list(self._history)

        reply_parts: list[str] = []
        for chunk in self._inference.stream(messages, system=system):
            reply_parts.append(chunk)
            yield chunk

        reply = "".join(reply_parts)
        self._history.append(ChatMessage("assistant", reply))

        with self.memory.session() as sess:
            sess.add(f"User: {user_message}", memory_type="episodic")
            sess.add(f"Assistant: {reply}", memory_type="episodic")

    def reset_history(self) -> None:
        """Clear the in-memory conversation history (memory on-chain is untouched)."""
        self._history.clear()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_system_prompt(self, memories: list[str]) -> str:
        base = self.config.system_prompt
        if not memories:
            return base
        ctx = "\n".join(f"- {m}" for m in memories)
        return (
            f"{base}\n\n"
            f"Relevant memories from past interactions:\n{ctx}\n\n"
            "Use this context to personalise your response where appropriate."
        )

    def _inference_with_tools(
        self,
        system: str,
        messages: list[ChatMessage],
        tool_calls_out: list[ToolCall],
        tool_results_out: list[ToolResult],
    ) -> str:
        """Run inference, handle tool calls in a loop, return final reply."""
        if not self._tool_map:
            return self._inference.chat(messages, system=system)

        # Build OpenAI tool schemas
        tools_schema = [t.to_openai_schema() for t in self.config.tools]
        payload = self._inference._build_payload(messages, system=system)
        client = self._inference._get_client()

        for _round in range(self.config.max_tool_rounds):
            try:
                response = client.chat.completions.create(
                    model=self.config.model,
                    messages=payload,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    tools=tools_schema,
                    tool_choice="auto",
                )
            except Exception:
                # Provider doesn't support function calling — fall back to plain chat
                return self._inference.chat(messages, system=system)
            msg = response.choices[0].message

            # No tool calls → we have the final answer
            if not msg.tool_calls:
                return msg.content or ""

            # Execute tool calls
            payload.append(msg.model_dump(exclude_unset=True))

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}

                tool_call = ToolCall(id=tc.id, name=fn_name, arguments=fn_args)
                tool_calls_out.append(tool_call)

                if fn_name in self._tool_map:
                    result = self._tool_map[fn_name].call(**fn_args)
                else:
                    result = ToolResult(name=fn_name, output=f"Unknown tool: {fn_name}", error=True)
                tool_results_out.append(result)

                payload.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.output,
                })

        # If we exhausted tool rounds, do a final pass
        response = client.chat.completions.create(
            model=self.config.model,
            messages=payload,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        return response.choices[0].message.content or ""
