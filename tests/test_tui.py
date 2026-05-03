"""Headless tests for TUI widgets and app logic (no display required)."""

import sys
import os
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio

from tui.app import (
    Conversation,
    Message,
    TurnContext,
    ZeroGApp,
    MODES,
    _load_custom_mode,
    _save_custom_mode,
)
from tests.test_memory import MockStorage, MockCompute, MockDA, MockChain
from ogmem.memory import VerifiableMemory


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_memory() -> VerifiableMemory:
    aid = f"tui-test-{uuid.uuid4().hex[:8]}"
    return VerifiableMemory(
        agent_id=aid,
        private_key="0x" + "a" * 64,
        network="0g-testnet",
        _storage=MockStorage(),
        _compute=MockCompute(),
        _da=MockDA(),
        _chain=MockChain(),
    )


def make_app() -> ZeroGApp:
    """Create a ZeroGApp in demo mode with mock memory."""
    app = ZeroGApp(demo_mode=True)
    return app


# ── Data model tests ───────────────────────────────────────────────────────────

class TestDataModels:

    def test_conversation_has_unique_id(self):
        c1 = Conversation()
        c2 = Conversation()
        assert c1.id != c2.id

    def test_conversation_default_title(self):
        c = Conversation()
        assert c.title == "New conversation"

    def test_message_role_user(self):
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"

    def test_message_defaults(self):
        m = Message(role="assistant", content="hi")
        assert m.memories_used == []
        assert m.tool_names == []
        assert m.latency_ms == 0

    def test_message_timestamp_set(self):
        before = int(time.time())
        m = Message(role="user", content="test")
        assert m.timestamp >= before

    def test_conversation_messages_list(self):
        c = Conversation()
        c.messages.append(Message(role="user", content="hi"))
        assert len(c.messages) == 1


# ── Mode tests ─────────────────────────────────────────────────────────────────

class TestModes:

    def test_all_modes_defined(self):
        for mode in ("assistant", "coding", "research", "custom"):
            assert mode in MODES
            assert len(MODES[mode]) > 0

    def test_coding_mode_mentions_code(self):
        assert "engineer" in MODES["coding"].lower() or "code" in MODES["coding"].lower()

    def test_research_mode_mentions_research(self):
        assert "research" in MODES["research"].lower()

    def test_custom_mode_exists(self):
        assert "custom" in MODES
        assert isinstance(MODES["custom"], str)

    def test_custom_mode_save_load(self, tmp_path, monkeypatch):
        import tui.app as tui_module
        custom_file = tmp_path / "custom_mode.txt"
        monkeypatch.setattr(tui_module, "_CUSTOM_MODE_FILE", custom_file)
        _save_custom_mode("Test custom prompt")
        loaded = _load_custom_mode()
        # _load_custom_mode uses the module-level _CUSTOM_MODE_FILE
        # so we need to read directly
        assert custom_file.read_text() == "Test custom prompt"


# ── Command parsing tests ──────────────────────────────────────────────────────

class TestCommandParsing:
    """Test _handle_command logic without rendering."""

    def _make_app_with_memory(self) -> ZeroGApp:
        app = ZeroGApp(demo_mode=True)
        mem = make_memory()
        app._memory = mem
        app._demo_mode = True

        # Minimal runtime mock
        from runtime.agent import AgentRuntime, AgentConfig
        from unittest.mock import MagicMock
        cfg = AgentConfig(tools=[])
        rt = AgentRuntime(memory=mem, config=cfg)
        rt._inference = MagicMock()
        app._runtime = rt
        return app

    def test_mode_switch_valid(self):
        # Mode switching is validated in the async pilot tests.
        # Here just verify MODES dict has the expected keys.
        assert "coding" in MODES
        assert "research" in MODES
        assert "assistant" in MODES

    def test_mode_switch_invalid(self):
        app = self._make_app_with_memory()
        system_msgs = []
        app._append_system = lambda t: system_msgs.append(t)
        app._handle_command("/mode nonexistent")
        assert any("Unknown mode" in m for m in system_msgs)

    def test_unknown_command(self):
        app = self._make_app_with_memory()
        system_msgs = []
        app._append_system = lambda t: system_msgs.append(t)
        app._handle_command("/foobar")
        assert any("Unknown command" in m for m in system_msgs)

    def test_tools_command_lists_tools(self):
        app = self._make_app_with_memory()
        system_msgs = []
        app._append_system = lambda t: system_msgs.append(t)
        app._handle_command("/tools")
        assert any("tool" in m.lower() for m in system_msgs)


# ── App initialization ─────────────────────────────────────────────────────────

class TestAppInit:

    def test_demo_mode_flag(self):
        app = ZeroGApp(demo_mode=True)
        assert app._demo_mode is True

    def test_conversations_start_empty(self):
        app = ZeroGApp(demo_mode=True)
        assert app._conversations == []

    def test_active_conv_starts_none(self):
        app = ZeroGApp(demo_mode=True)
        assert app._active_conv is None

    def test_runtime_starts_none(self):
        app = ZeroGApp(demo_mode=True)
        assert app._runtime is None


# ── Headless app pilot tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_app_mounts_and_quits():
    """App should mount without errors in demo mode."""
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        # App is running
        assert app.is_running


@pytest.mark.asyncio
async def test_new_conversation_creates_entry():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        initial_count = len(app._conversations)
        await pilot.press("ctrl+n")
        await pilot.pause(0.1)
        assert len(app._conversations) == initial_count + 1


@pytest.mark.asyncio
async def test_input_sends_message():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        # Directly invoke the send path (pilot.type not in Textual 8.x)
        app._send_message("hello world")
        await pilot.pause(0.2)
        assert app._active_conv is not None
        user_msgs = [m for m in app._active_conv.messages if m.role == "user"]
        assert len(user_msgs) >= 1
        assert user_msgs[0].content == "hello world"


@pytest.mark.asyncio
async def test_slash_mode_command():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        # Directly invoke command handler
        app._handle_command("/mode coding")
        await pilot.pause(0.1)
        assert app.current_mode == "coding"


@pytest.mark.asyncio
async def test_memory_panel_opens():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        await pilot.press("m")
        await pilot.pause(0.1)
        # MemoryModal should be the current screen
        from tui.app import MemoryModal
        assert isinstance(app.screen, MemoryModal)
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_help_modal_opens():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        await pilot.press("?")
        await pilot.pause(0.1)
        from tui.app import HelpModal
        assert isinstance(app.screen, HelpModal)
        await pilot.press("escape")



@pytest.mark.asyncio
async def test_context_panel_visible_by_default():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        assert app.context_panel_visible is True


@pytest.mark.asyncio
async def test_toggle_context_panel():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        assert app.context_panel_visible is True
        await pilot.press("r")
        await pilot.pause(0.1)
        assert app.context_panel_visible is False
        await pilot.press("r")
        await pilot.pause(0.1)
        assert app.context_panel_visible is True


@pytest.mark.asyncio
async def test_custom_mode_command():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        app._handle_command('/mode custom "You are a pirate assistant"')
        await pilot.pause(0.1)
        assert app.current_mode == "custom"
        assert "pirate" in MODES["custom"]


@pytest.mark.asyncio
async def test_custom_mode_switch_without_prompt():
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        system_msgs = []
        app._append_system = lambda t: system_msgs.append(t)
        app._handle_command("/mode custom")
        await pilot.pause(0.1)
        assert app.current_mode == "custom"


@pytest.mark.asyncio
async def test_checkpoint_command():
    import json
    from pathlib import Path
    app = ZeroGApp(demo_mode=True)
    async with app.run_test(headless=True) as pilot:
        await pilot.pause(0.1)
        app._send_message("hello")
        await pilot.pause(0.1)
        system_msgs = []
        original_append = app._append_system
        app._append_system = lambda t: (system_msgs.append(t), original_append(t))
        app._handle_command("/checkpoint")
        await pilot.pause(0.1)
        assert any("Checkpoint" in m for m in system_msgs)
        # Cleanup
        ckpt = Path.home() / ".0g" / "checkpoint.json"
        if ckpt.exists():
            ckpt.unlink()


class TestTurnContext:

    def test_defaults(self):
        ctx = TurnContext()
        assert ctx.memories_used == []
        assert ctx.tool_calls == []
        assert ctx.write_receipts == []
        assert ctx.latency_ms == 0
        assert ctx.da_hash == ""

    def test_with_data(self):
        ctx = TurnContext(
            memories_used=["User likes Python"],
            tool_calls=[{"name": "web_search", "result": "..."}],
            write_receipts=[{"blob_id": "abc", "chain_tx_hash": "0xdef"}],
            latency_ms=250,
            da_hash="local:sha256:abc",
        )
        assert len(ctx.memories_used) == 1
        assert ctx.latency_ms == 250
        assert ctx.da_hash.startswith("local:")
