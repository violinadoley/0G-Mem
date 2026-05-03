"""Tests for the Telegram bot (logic + unit, no real Telegram connection needed)."""

import sys
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from telegram_bot.bot import (
    _escape_md,
    _format_memories,
    _format_tools,
    _get_runtime,
    _runtimes,
    _TUI_REDIRECT_KEYWORDS,
    AGENT_MODES,
    cmd_clear,
    cmd_forget,
    cmd_help,
    cmd_memory,
    cmd_mode,
    cmd_remember,
    cmd_start,
    cmd_stats,
    handle_message,
)
from ogmem.memory import VerifiableMemory
from runtime.agent import AgentRuntime
from tests.test_memory import MockStorage, MockCompute, MockDA, MockChain


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_update(
    user_id: int = 12345,
    text: str = "Hello",
    args: list[str] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Return (update, context) mocks for handler tests."""
    user = MagicMock()
    user.id = user_id
    user.first_name = "Test"

    message = MagicMock()
    message.text = text
    message.reply_text = AsyncMock()
    message.chat.send_action = AsyncMock()

    update = MagicMock()
    update.effective_user = user
    update.message = message

    context = MagicMock()
    context.args = args or []

    return update, context


def _fresh_uid() -> int:
    """Unique user ID per test to avoid runtime state bleed."""
    return int(uuid.uuid4().int % 10**9)


def _patch_runtime(uid: int, reply: str = "Test reply") -> AgentRuntime:
    """Inject a mock-backed AgentRuntime for a user."""
    mem = VerifiableMemory(
        agent_id=f"tg-test-{uid}",
        private_key="0x" + "a" * 64,
        network="0g-testnet",
        _storage=MockStorage(),
        _compute=MockCompute(),
        _da=MockDA(),
        _chain=MockChain(),
    )
    from runtime.agent import AgentConfig, Turn, ToolCall, WriteReceipt
    from ogmem.proof import WriteReceipt as WR
    cfg = AgentConfig(tools=[])
    rt = AgentRuntime(memory=mem, config=cfg)

    # Mock inference
    mock_turn = Turn(
        user_message="",
        assistant_reply=reply,
        retrieved_memories=["User prefers Python"],
        tool_calls=[],
        tool_results=[],
        write_receipts=[],
        latency_ms=120,
    )
    rt.run = MagicMock(return_value=mock_turn)
    _runtimes[uid] = rt
    return rt


# ── Utility function tests ─────────────────────────────────────────────────────

class TestEscapeMd:

    def test_escapes_underscore(self):
        assert "\\*" in _escape_md("hello *world*")

    def test_escapes_dot(self):
        assert "\\." in _escape_md("v1.0")

    def test_plain_text_unchanged(self):
        assert _escape_md("hello world") == "hello world"

    def test_escapes_parens(self):
        result = _escape_md("(test)")
        assert "\\(" in result and "\\)" in result


class TestFormatMemories:

    def test_empty_returns_empty_string(self):
        assert _format_memories([]) == ""

    def test_formats_up_to_3(self):
        mems = ["mem 1", "mem 2", "mem 3", "mem 4"]
        result = _format_memories(mems)
        assert "mem 1" in result
        assert "mem 4" not in result  # only top 3

    def test_includes_header(self):
        result = _format_memories(["something"])
        assert "Memories" in result or "memories" in result


class TestFormatTools:

    def test_empty_returns_empty(self):
        assert _format_tools([]) == ""

    def test_includes_tool_name(self):
        result = _format_tools(["web_search"])
        # _escape_md escapes the underscore → "web\_search"
        assert "web" in result and "search" in result


class TestGetRuntime:

    def test_creates_runtime_for_new_user(self):
        uid = _fresh_uid()
        with patch.dict(os.environ, {"AGENT_KEY": "0x" + "a" * 64}):
            rt = _get_runtime(uid)
        assert isinstance(rt, AgentRuntime)
        _runtimes.pop(uid, None)

    def test_returns_same_runtime_for_same_user(self):
        uid = _fresh_uid()
        with patch.dict(os.environ, {"AGENT_KEY": "0x" + "a" * 64}):
            rt1 = _get_runtime(uid)
            rt2 = _get_runtime(uid)
        assert rt1 is rt2
        _runtimes.pop(uid, None)

    def test_different_users_get_different_runtimes(self):
        uid1, uid2 = _fresh_uid(), _fresh_uid()
        with patch.dict(os.environ, {"AGENT_KEY": "0x" + "a" * 64}):
            rt1 = _get_runtime(uid1)
            rt2 = _get_runtime(uid2)
        assert rt1 is not rt2
        _runtimes.pop(uid1, None)
        _runtimes.pop(uid2, None)


class TestAgentModes:

    def test_all_modes_exist(self):
        for mode in ("assistant", "coding", "research"):
            assert mode in AGENT_MODES

    def test_coding_mode_mentions_tui(self):
        assert "TUI" in AGENT_MODES["coding"] or "0g" in AGENT_MODES["coding"]

    def test_redirect_keywords_defined(self):
        assert len(_TUI_REDIRECT_KEYWORDS) > 0


# ── Command handler tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_start_replies():
    uid = _fresh_uid()
    update, context = _make_update(user_id=uid)
    await cmd_start(update, context)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "0G" in call_args or "0g" in call_args


@pytest.mark.asyncio
async def test_cmd_help_replies():
    uid = _fresh_uid()
    update, context = _make_update(user_id=uid)
    await cmd_help(update, context)
    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "/memory" in call_text
    assert "/mode" in call_text


@pytest.mark.asyncio
async def test_cmd_memory_shows_stats():
    uid = _fresh_uid()
    _patch_runtime(uid)
    # Add a memory entry
    _runtimes[uid].memory.add("Test memory", memory_type="semantic")
    update, context = _make_update(user_id=uid)
    await cmd_memory(update, context)
    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "Memory" in call_text
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_cmd_mode_valid():
    uid = _fresh_uid()
    _patch_runtime(uid)
    update, context = _make_update(user_id=uid)
    context.args = ["coding"]
    await cmd_mode(update, context)
    update.message.reply_text.assert_called_once()
    assert _runtimes[uid].config.system_prompt == AGENT_MODES["coding"]
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_cmd_mode_invalid():
    uid = _fresh_uid()
    update, context = _make_update(user_id=uid)
    context.args = ["nonexistent"]
    await cmd_mode(update, context)
    call_text = update.message.reply_text.call_args[0][0]
    assert "Usage" in call_text or "mode" in call_text.lower()


@pytest.mark.asyncio
async def test_cmd_remember_adds_memory():
    uid = _fresh_uid()
    _patch_runtime(uid)
    update, context = _make_update(user_id=uid)
    context.args = ["I", "prefer", "dark", "mode"]
    initial = len(_runtimes[uid].memory._entries)
    await cmd_remember(update, context)
    assert len(_runtimes[uid].memory._entries) == initial + 1
    update.message.reply_text.assert_called_once()
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_cmd_remember_no_args():
    uid = _fresh_uid()
    update, context = _make_update(user_id=uid)
    context.args = []
    await cmd_remember(update, context)
    call_text = update.message.reply_text.call_args[0][0]
    assert "Usage" in call_text


@pytest.mark.asyncio
async def test_cmd_forget_deletes_last():
    uid = _fresh_uid()
    _patch_runtime(uid)
    _runtimes[uid].memory.add("Memory to forget")
    initial = len(_runtimes[uid].memory._entries)
    update, context = _make_update(user_id=uid)
    await cmd_forget(update, context)
    assert len(_runtimes[uid].memory._entries) == initial - 1
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_cmd_forget_empty_memory():
    uid = _fresh_uid()
    _patch_runtime(uid)
    update, context = _make_update(user_id=uid)
    await cmd_forget(update, context)
    call_text = update.message.reply_text.call_args[0][0]
    assert "No memories" in call_text or "forget" in call_text.lower()
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_cmd_clear_resets_history():
    uid = _fresh_uid()
    _patch_runtime(uid)
    _runtimes[uid]._history = [MagicMock(), MagicMock()]
    update, context = _make_update(user_id=uid)
    await cmd_clear(update, context)
    assert _runtimes[uid]._history == []
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_cmd_stats_shows_breakdown():
    uid = _fresh_uid()
    _patch_runtime(uid)
    update, context = _make_update(user_id=uid)
    await cmd_stats(update, context)
    call_text = update.message.reply_text.call_args[0][0]
    assert "Stats" in call_text or "Total" in call_text
    _runtimes.pop(uid, None)


# ── Message handler tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_message_calls_runtime():
    uid = _fresh_uid()
    _patch_runtime(uid, reply="42 is the answer")
    update, context = _make_update(user_id=uid, text="What is 6 times 7?")
    await handle_message(update, context)
    _runtimes[uid].run.assert_called_once_with("What is 6 times 7?")
    update.message.reply_text.assert_called_once()
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_handle_message_reply_contains_text():
    uid = _fresh_uid()
    _patch_runtime(uid, reply="The answer is 42")
    update, context = _make_update(user_id=uid, text="What is 6x7?")
    await handle_message(update, context)
    call_text = update.message.reply_text.call_args[0][0]
    assert "42" in call_text
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_handle_message_deep_work_redirects():
    """Long 'refactor' messages should redirect to TUI."""
    uid = _fresh_uid()
    update, context = _make_update(
        user_id=uid,
        text="refactor " + "the entire auth module " * 10,  # >120 chars + keyword
    )
    await handle_message(update, context)
    call_text = update.message.reply_text.call_args[0][0]
    assert "TUI" in call_text or "0g" in call_text
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_handle_message_short_deep_work_not_redirected():
    """Short messages with deep-work keywords should still go to agent."""
    uid = _fresh_uid()
    _patch_runtime(uid, reply="Sure, here's how to refactor that")
    update, context = _make_update(user_id=uid, text="refactor this")
    await handle_message(update, context)
    # Should NOT redirect (message is short)
    call_text = update.message.reply_text.call_args[0][0]
    assert "Sure" in call_text or "refactor" in call_text.lower()
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_handle_message_runtime_error_replies_gracefully():
    uid = _fresh_uid()
    _patch_runtime(uid)
    _runtimes[uid].run = MagicMock(side_effect=RuntimeError("inference failed"))
    update, context = _make_update(user_id=uid, text="hello")
    await handle_message(update, context)
    call_text = update.message.reply_text.call_args[0][0]
    assert "Error" in call_text or "error" in call_text
    _runtimes.pop(uid, None)


@pytest.mark.asyncio
async def test_handle_message_sends_typing_action():
    uid = _fresh_uid()
    _patch_runtime(uid)
    update, context = _make_update(user_id=uid, text="hello")
    await handle_message(update, context)
    update.message.chat.send_action.assert_called_once()
    _runtimes.pop(uid, None)
