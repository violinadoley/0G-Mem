"""Tests for the Agent Runtime (inference + tool calls + memory write)."""

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch

from ogmem.memory import VerifiableMemory
from ogmem.inference import ZeroGInferenceClient, ChatMessage
from runtime.agent import AgentRuntime, AgentConfig, Turn
from runtime.tools import Tool, ToolResult, BUILTIN_TOOLS, _calculate

from tests.test_memory import MockStorage, MockCompute, MockDA, MockChain


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_memory(agent_id: str | None = None) -> VerifiableMemory:
    aid = agent_id or f"rt-test-{uuid.uuid4().hex[:8]}"
    return VerifiableMemory(
        agent_id=aid,
        private_key="0x" + "a" * 64,
        network="0g-testnet",
        _storage=MockStorage(),
        _compute=MockCompute(),
        _da=MockDA(),
        _chain=MockChain(),
    )


def _mock_inference_client(reply: str = "Hello! How can I help?") -> ZeroGInferenceClient:
    """Return a ZeroGInferenceClient whose chat() always returns `reply`."""
    client = ZeroGInferenceClient.__new__(ZeroGInferenceClient)
    client.service_url = ""
    client.api_key = ""
    client.model = "test-model"
    client.max_tokens = 100
    client.temperature = 0.7
    client.timeout = 10
    client._client = None
    client.chat = MagicMock(return_value=reply)
    client.stream = MagicMock(return_value=iter([reply]))
    client._build_payload = ZeroGInferenceClient._build_payload.__get__(client)
    client._get_client = MagicMock(return_value=None)
    return client


def make_runtime(
    reply: str = "Hello! How can I help?",
    tools: list | None = None,
) -> AgentRuntime:
    mem = make_memory()
    cfg = AgentConfig(tools=tools if tools is not None else [])
    rt = AgentRuntime(memory=mem, config=cfg)
    rt._inference = _mock_inference_client(reply)
    return rt


# ── ZeroGInferenceClient ───────────────────────────────────────────────────────

class TestZeroGInferenceClient:

    def test_chat_returns_string(self):
        client = ZeroGInferenceClient.__new__(ZeroGInferenceClient)
        client.chat = MagicMock(return_value="test reply")
        result = client.chat([ChatMessage("user", "hi")])
        assert isinstance(result, str)

    def test_build_payload_no_system(self):
        client = ZeroGInferenceClient(service_url="", api_key="")
        msgs = [ChatMessage("user", "hello"), ChatMessage("assistant", "hi")]
        payload = client._build_payload(msgs)
        assert len(payload) == 2
        assert payload[0] == {"role": "user", "content": "hello"}

    def test_build_payload_with_system(self):
        client = ZeroGInferenceClient(service_url="", api_key="")
        msgs = [ChatMessage("user", "hello")]
        payload = client._build_payload(msgs, system="You are helpful")
        assert payload[0]["role"] == "system"
        assert payload[1]["role"] == "user"

    def test_raises_without_credentials(self):
        client = ZeroGInferenceClient(service_url="", api_key="")
        # Ensure OPENAI_API_KEY is not set
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("ZEROG_API_KEY", None)
            os.environ.pop("ZEROG_SERVICE_URL", None)
            with pytest.raises(RuntimeError, match="No 0G Compute credentials"):
                client._get_client()

    def test_uses_zerog_env_vars(self):
        with patch.dict(os.environ, {
            "ZEROG_SERVICE_URL": "https://fake.0g.ai",
            "ZEROG_API_KEY": "app-sk-test",
        }):
            client = ZeroGInferenceClient()
            assert client.service_url == "https://fake.0g.ai"
            assert client.api_key == "app-sk-test"


# ── Built-in tools ─────────────────────────────────────────────────────────────

class TestBuiltinTools:

    def test_calculate_basic(self):
        assert _calculate("2 + 2") == "4"

    def test_calculate_power(self):
        assert _calculate("2 ** 10") == "1024"

    def test_calculate_division(self):
        result = _calculate("10 / 4")
        assert float(result) == 2.5

    def test_calculate_rejects_import(self):
        result = _calculate("__import__('os').system('id')")
        assert "error" in result.lower() or "unsafe" in result.lower()

    def test_tool_call_returns_tool_result(self):
        calc = next(t for t in BUILTIN_TOOLS if t.name == "calculate")
        result = calc.call(expression="3 * 7")
        assert isinstance(result, ToolResult)
        assert result.output == "21"
        assert result.error is False

    def test_tool_call_error_sets_flag(self):
        bad_tool = Tool(
            name="boom",
            description="always fails",
            parameters={},
            fn=lambda: (_ for _ in ()).throw(ValueError("boom")),
        )
        result = bad_tool.call()
        assert result.error is True

    def test_to_openai_schema(self):
        calc = next(t for t in BUILTIN_TOOLS if t.name == "calculate")
        schema = calc.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calculate"
        assert "parameters" in schema["function"]


# ── AgentRuntime ───────────────────────────────────────────────────────────────

class TestAgentRuntime:

    def test_run_returns_turn(self):
        rt = make_runtime()
        turn = rt.run("Hello!")
        assert isinstance(turn, Turn)

    def test_run_reply_matches_mock(self):
        rt = make_runtime(reply="Mocked reply")
        turn = rt.run("Hello!")
        assert turn.assistant_reply == "Mocked reply"

    def test_run_stores_memories(self):
        rt = make_runtime()
        turn = rt.run("Remember this: I love Python")
        # User + assistant turn stored
        assert len(rt.memory._entries) == 2

    def test_run_single_chain_tx_per_turn(self):
        rt = make_runtime()
        chain: MockChain = rt.memory._chain  # type: ignore
        before = len(chain._history)
        rt.run("Hello")
        after = len(chain._history)
        # Session batching: exactly 1 chain tx
        assert after - before == 1

    def test_run_retrieves_past_memories(self):
        rt = make_runtime()
        rt.memory.add("User loves TypeScript", memory_type="procedural")
        turn = rt.run("What do I prefer?")
        assert len(turn.retrieved_memories) >= 1

    def test_run_has_latency_ms(self):
        rt = make_runtime()
        turn = rt.run("Hi")
        assert turn.latency_ms >= 0

    def test_run_has_write_receipts(self):
        rt = make_runtime()
        turn = rt.run("Test")
        assert len(turn.write_receipts) == 2  # user + assistant

    def test_history_accumulates(self):
        rt = make_runtime()
        rt.run("First message")
        rt.run("Second message")
        # 2 user + 2 assistant = 4 history entries
        assert len(rt._history) == 4

    def test_reset_history_clears_history(self):
        rt = make_runtime()
        rt.run("Hello")
        rt.reset_history()
        assert len(rt._history) == 0

    def test_turn_to_dict(self):
        rt = make_runtime()
        turn = rt.run("Test")
        d = turn.to_dict()
        assert "user_message" in d
        assert "assistant_reply" in d
        assert "retrieved_memories" in d
        assert "tool_calls" in d
        assert "write_receipts" in d

    def test_multiple_turns_chain_txs(self):
        rt = make_runtime()
        chain: MockChain = rt.memory._chain  # type: ignore
        before = len(chain._history)
        rt.run("Turn 1")
        rt.run("Turn 2")
        rt.run("Turn 3")
        after = len(chain._history)
        # 3 turns × 1 chain tx each = 3
        assert after - before == 3


# ── Tool execution in runtime ──────────────────────────────────────────────────

class TestRuntimeToolExecution:

    def _make_runtime_with_tool_mock(self, tool_reply: str) -> tuple[AgentRuntime, MagicMock]:
        """Create runtime where the OpenAI client returns a tool call then a final reply."""
        mem = make_memory()
        cfg = AgentConfig(tools=list(BUILTIN_TOOLS))
        rt = AgentRuntime(memory=mem, config=cfg)

        # Mock the OpenAI client to first return a tool call, then a plain reply
        mock_client = MagicMock()

        # First response: tool call
        fn_mock = MagicMock()
        fn_mock.name = "calculate"
        fn_mock.arguments = '{"expression": "6 * 7"}'
        tc_mock = MagicMock()
        tc_mock.id = "call_1"
        tc_mock.function = fn_mock
        tool_call_msg = MagicMock()
        tool_call_msg.tool_calls = [tc_mock]
        tool_call_msg.content = None
        tool_call_msg.model_dump.return_value = {
            "role": "assistant", "tool_calls": [], "content": None
        }
        first_response = MagicMock()
        first_response.choices = [MagicMock(message=tool_call_msg)]

        # Second response: final text
        final_msg = MagicMock()
        final_msg.tool_calls = None
        final_msg.content = tool_reply
        second_response = MagicMock()
        second_response.choices = [MagicMock(message=final_msg)]

        mock_client.chat.completions.create.side_effect = [first_response, second_response]

        rt._inference._client = mock_client
        rt._inference._get_client = MagicMock(return_value=mock_client)
        return rt, mock_client

    def test_tool_call_is_executed(self):
        rt, _ = self._make_runtime_with_tool_mock("6 × 7 = 42")
        turn = rt.run("What is 6 times 7?")
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].name == "calculate"

    def test_tool_result_captured(self):
        rt, _ = self._make_runtime_with_tool_mock("6 × 7 = 42")
        turn = rt.run("What is 6 times 7?")
        assert len(turn.tool_results) == 1
        assert turn.tool_results[0].output == "42"

    def test_final_reply_after_tool(self):
        rt, _ = self._make_runtime_with_tool_mock("6 × 7 = 42")
        turn = rt.run("What is 6 times 7?")
        assert turn.assistant_reply == "6 × 7 = 42"


# ── DA turn logging ────────────────────────────────────────────────────────────

def _make_rt_with_memory(mem):
    """Create a runtime with a specific VerifiableMemory instance."""
    cfg = AgentConfig(tools=[])
    rt = AgentRuntime(memory=mem, config=cfg)
    rt._inference = _mock_inference_client()
    return rt


class TestDATurnLogging:

    def test_da_hash_set_on_turn(self):
        """Each turn's DA hash is non-empty when DA is available."""
        mem = make_memory()
        rt = _make_rt_with_memory(mem)
        turn = rt.run("hello")
        assert turn.da_hash, f"Expected non-empty da_hash, got: {turn.da_hash!r}"
        assert isinstance(turn.da_hash, str)

    def test_da_hash_empty_when_da_unavailable(self):
        """If memory has no DA client, da_hash is empty string."""
        mem = make_memory()
        rt = _make_rt_with_memory(mem)
        rt._da = None
        turn = rt.run("hello")
        assert turn.da_hash == ""

    def test_da_receives_commitment(self):
        """DA commitment is posted for each turn."""
        from tests.test_memory import MockDA
        mem = make_memory()
        rt = _make_rt_with_memory(mem)
        rt.run("first message")
        rt.run("second message")
        da: MockDA = mem._da  # type: ignore
        # Each turn should post one commitment (plus memory writes from VerifiableMemory)
        write_commitments = [e for e in da._log if e.get("type") == "memory_write"]
        assert len(write_commitments) >= 2

    def test_da_hash_field_on_turn(self):
        """Turn dataclass has a da_hash field."""
        rt = make_runtime()
        turn = rt.run("test")
        assert hasattr(turn, "da_hash")
        assert isinstance(turn.da_hash, str)
