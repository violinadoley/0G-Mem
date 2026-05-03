"""
0G TUI — Keyboard-driven terminal interface for the 0G Mem Agent Runtime.

    python -m tui              # open full TUI
    python -m tui "question"   # one-shot answer, no TUI
    python tui/app.py          # same as python -m tui
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Textual imports ────────────────────────────────────────────────────────────
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

# ── Project imports ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from ogmem.memory import VerifiableMemory
from ogmem.proof import MemoryType
from runtime.agent import AgentConfig, AgentRuntime


# ── Agent modes ────────────────────────────────────────────────────────────────

_CUSTOM_MODE_FILE = Path.home() / ".0g" / "custom_mode.txt"


def _load_custom_mode() -> str:
    try:
        if _CUSTOM_MODE_FILE.exists():
            return _CUSTOM_MODE_FILE.read_text().strip()
    except Exception:
        pass
    return "You are a custom AI assistant. Edit with /mode custom \"Your prompt here\"."


def _save_custom_mode(prompt: str) -> None:
    try:
        _CUSTOM_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CUSTOM_MODE_FILE.write_text(prompt)
    except Exception:
        pass


MODES: dict[str, str] = {
    "assistant": (
        "You are a helpful AI assistant with verifiable, persistent memory. "
        "You remember past conversations and can use tools to answer questions. "
        "Always be concise and accurate."
    ),
    "coding": (
        "You are an expert software engineer with verifiable, persistent memory. "
        "You know the user's tech stack, conventions, and ongoing projects. "
        "Write clean code, output diffs when modifying files, be direct."
    ),
    "research": (
        "You are a research assistant with verifiable, persistent memory. "
        "You connect current queries to past research sessions the user has had. "
        "Be thorough, cite sources when you can, summarise findings clearly."
    ),
    "custom": _load_custom_mode(),
}


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class TurnContext:
    """Context from the last completed turn, for the right panel."""
    memories_used: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)   # [{name, result}]
    write_receipts: list[dict] = field(default_factory=list)  # [{blob_id, tx}]
    latency_ms: int = 0
    da_hash: str = ""


@dataclass
class Message:
    role: str           # "user" | "assistant" | "system"
    content: str
    memories_used: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    latency_ms: int = 0
    timestamp: int = field(default_factory=lambda: int(time.time()))


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = "New conversation"
    messages: list[Message] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time()))


# ── Widgets ────────────────────────────────────────────────────────────────────

class ConversationItem(ListItem):
    """Sidebar list item for a conversation."""

    def __init__(self, conv: Conversation) -> None:
        super().__init__()
        self.conv = conv

    def compose(self) -> ComposeResult:
        title = self.conv.title[:18] + "…" if len(self.conv.title) > 18 else self.conv.title
        yield Label(f"> {title}")




class MemoryRow(Widget):
    """A single row in the memory list."""

    def __init__(self, entry: dict) -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        mt = self.entry.get("memory_type", "episodic")
        text = self.entry.get("text", "")[:60]
        count = self.entry.get("retrieval_count", 0)
        stale = self.entry.get("stale", False)
        stale_mark = " ⚠" if stale else ""
        badge_class = f"mem-type-{mt}" + (" mem-stale" if stale else "")
        yield Label(f"[{mt}]{stale_mark}", classes=f"mem-type-badge {badge_class}")
        yield Label(text, classes="mem-text")
        yield Label(f"{count}x", classes="mem-meta")


# ── Modals ─────────────────────────────────────────────────────────────────────

class MemoryModal(ModalScreen):
    """Full memory panel accessible via ctrl+m."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("ctrl+y", "dismiss", "Close"),
    ]

    def __init__(self, memory: Optional[VerifiableMemory]) -> None:
        super().__init__()
        self._memory = memory

    def compose(self) -> ComposeResult:
        if self._memory is None:
            with Container(id="memory-dialog"):
                yield Label("Memory Panel", id="memory-title")
                yield Label("Memory not configured. Set AGENT_KEY to enable verifiable memory.", classes="mem-text")
            return
        stats = self._memory.stats()
        total = stats.get("total", 0)
        stale_count = stats.get("stale_count", 0)
        entries = list(self._memory._entries)

        with Container(id="memory-dialog"):
            yield Label(f"Memory Panel  ·  {total} memories  ·  {stale_count} stale", id="memory-title")

            with TabbedContent(id="memory-tabs"):
                # Tab 1: Explorer
                with TabPane("Explorer", id="tab-memories"):
                    with ScrollableContainer():
                        if not entries:
                            yield Label("No memories yet. Start chatting!", classes="mem-text")
                        for entry in entries:
                            yield MemoryRow(entry)

                # Tab 2: Stats
                with TabPane("Stats", id="tab-stats"):
                    yield Markdown(self._format_stats(stats))

                # Tab 3: Activity
                with TabPane("Activity", id="tab-activity"):
                    yield Markdown(self._format_activity())

                # Tab 4: Access
                with TabPane("Access", id="tab-access"):
                    yield Markdown(
                        "**Access control** is managed on-chain via MemoryNFT.\n\n"
                        "Use the REST API `/memory/{agent_id}/grant` and `/revoke` "
                        "endpoints to manage access, or call `memory.grant_access()` "
                        "directly from the SDK."
                    )

                # Tab 5: Portability
                with TabPane("Portability", id="tab-portability"):
                    yield Markdown(
                        "**Export:** `memory.export_audit()` — full EU AI Act compliant JSON.\n\n"
                        "**Distill:** Run `/memory distill` to compress old episodic → semantic.\n\n"
                        "**Evolve:** Run `/memory evolve` to reweight memories.\n\n"
                        "**Delete:** Select an entry above and press `d`."
                    )

    def _format_stats(self, stats: dict) -> str:
        by_type = stats.get("by_type", {})
        top = stats.get("top_retrieved", [])
        lines = [
            "### Memory Stats\n",
            f"**Total:** {stats.get('total', 0)}  ",
            f"**Stale:** {stats.get('stale_count', 0)}\n",
            "\n### By Type\n",
        ]
        for mt in MemoryType:
            count = by_type.get(mt.value, 0)
            lines.append(f"- **{mt.value}**: {count}")
        if top:
            lines.append("\n### Most Retrieved\n")
            for item in top[:5]:
                lines.append(f"- `{item['text'][:50]}` — {item['count']}x")
        return "\n".join(lines)

    def _format_activity(self) -> str:
        entries = list(self._memory._entries)
        if not entries:
            return "_No activity yet._"
        # Sort by last_retrieved descending
        sorted_entries = sorted(
            entries,
            key=lambda e: e.get("last_retrieved", 0),
            reverse=True,
        )
        lines = ["### Recent Activity\n"]
        for e in sorted_entries[:10]:
            ts = e.get("last_retrieved") or e.get("timestamp", 0)
            when = time.strftime("%m/%d %H:%M", time.localtime(ts)) if ts else "—"
            mt = e.get("memory_type", "?")
            text = e.get("text", "")[:50]
            count = e.get("retrieval_count", 0)
            lines.append(f"- `{when}` **{mt}** · {count}x — {text}")
        return "\n".join(lines)


class HelpModal(ModalScreen):
    """Keyboard shortcuts and commands."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("ctrl+slash", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Markdown(
                "## 0G — Keybindings\n\n"
                "| Key | Action |\n"
                "|---|---|\n"
                "| `tab` | Switch panel focus |\n"
                "| `m` | Memory panel |\n"
                "| `r` | Toggle context panel |\n"
                "| `ctrl+n` | New conversation |\n"
                "| `ctrl+e` | Open reply in $EDITOR |\n"
                "| `ctrl+c` | Copy last reply |\n"
                "| `?` | This help |\n"
                "| `esc` | Close modal / back |\n\n"
                "## Slash Commands\n\n"
                "| Command | Effect |\n"
                "|---|---|\n"
                "| `/mode coding` | Switch to coding mode |\n"
                "| `/mode research` | Switch to research mode |\n"
                "| `/mode assistant` | Switch to assistant mode |\n"
                "| `/mode custom \"prompt\"` | Set a custom system prompt |\n"
                "| `/memory evolve` | Run memory evolution pass |\n"
                "| `/memory distill` | Compress old episodic → semantic |\n"
                "| `/memory stats` | Show memory stats |\n"
                "| `/tools` | List available tools |\n"
                "| `/clear` | Clear conversation history |\n"
                "| `/help` | Show this help |\n"
                "| `/checkpoint` | Save context checkpoint |\n"
            )


class SetupModal(ModalScreen):
    """Shown when credentials are not configured."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Container(id="setup-dialog"):
            yield Markdown(
                "## Setup Required\n\n"
                "To use 0G with real inference and storage, set these env vars:\n\n"
                "```bash\n"
                "# Wallet key (for memory storage on-chain)\n"
                "export AGENT_KEY=0x_your_private_key\n\n"
                "# 0G Compute (inference)\n"
                "export ZEROG_SERVICE_URL=https://<provider>.0g.ai\n"
                "export ZEROG_API_KEY=app-sk-your_secret\n"
                "```\n\n"
                "**Running in demo mode** — memory is in-memory only, "
                "inference is echoed back.\n\n"
                "Press `esc` to continue."
            )


# ── Main App ───────────────────────────────────────────────────────────────────

class ZeroGApp(App):
    """0G — Verifiable AI agent memory in your terminal."""

    CSS_PATH = Path(__file__).parent / "styles.tcss"

    BINDINGS = [
        Binding("ctrl+y", "show_memory", "Memory"),
        Binding("ctrl+r", "toggle_context", "Context"),
        Binding("ctrl+n", "new_conversation", "New"),
        Binding("ctrl+slash", "show_help", "Help"),
        Binding("ctrl+e", "open_in_editor", "Editor"),
        Binding("ctrl+c", "copy_last", "Copy", show=False),
    ]

    # Reactive state
    current_mode: reactive[str] = reactive("assistant")
    memory_count: reactive[int] = reactive(0)
    is_thinking: reactive[bool] = reactive(False)
    context_panel_visible: reactive[bool] = reactive(True)

    def __init__(self, demo_mode: bool = False):
        super().__init__()
        self._demo_mode = demo_mode  # kept for test compat; always False in production
        self._conversations: list[Conversation] = []
        self._active_conv: Optional[Conversation] = None
        self._last_reply: str = ""
        self._memory: Optional[VerifiableMemory] = None
        self._runtime: Optional[AgentRuntime] = None
        self._last_turn_ctx: TurnContext = TurnContext()
        self._start_error: str = ""
        self._inference_warning: bool = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        try:
            self._init_backend()
        except Exception as e:
            self._start_error = str(e)
        self._new_conversation()

    def _init_backend(self) -> None:
        """Initialise memory + runtime. Raises if required credentials are missing."""
        agent_key = os.environ.get("AGENT_KEY", "")
        if not agent_key:
            raise RuntimeError(
                "AGENT_KEY not set.\n\n"
                "Export your 0G wallet private key:\n"
                "  export AGENT_KEY=0x<your_private_key>\n\n"
                "Get testnet OG tokens: https://faucet.0g.ai"
            )

        try:
            from eth_account import Account
            wallet_addr = Account.from_key(agent_key).address.lower()
        except Exception as e:
            raise RuntimeError(f"Invalid AGENT_KEY: {e}") from e

        self._memory = VerifiableMemory(
            agent_id=wallet_addr,
            private_key=agent_key,
            network="0g-testnet",
        )

        service_url = os.environ.get("ZEROG_SERVICE_URL", "")
        api_key = os.environ.get("ZEROG_API_KEY", "")
        if not (service_url and api_key):
            self._inference_warning = True

        cfg = AgentConfig(
            service_url=service_url,
            api_key=api_key,
            model=os.environ.get("ZEROG_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
            system_prompt=MODES[self.current_mode],
        )
        self._runtime = AgentRuntime(memory=self._memory, config=cfg)
        self.memory_count = len(self._memory._entries)

    # ── Layout ─────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        # Header bar
        with Horizontal(id="header-bar"):
            yield Label("0G", id="header-title")
            yield Label("·", id="header-sep")
            yield Label(self._agent_address(), id="header-address")
            yield Label(f"{self.memory_count} memories", id="header-mem-count")
            yield Label(f"[{self.current_mode}]", id="header-mode")
            yield Label("[ctrl+/] help  [ctrl+y] memory  [ctrl+r] context  [ctrl+n] new", id="header-help")

        # Main area
        with Horizontal(id="main-area"):
            # Sidebar
            with Vertical(id="sidebar"):
                yield Label("Conversations", id="sidebar-title")
                yield ListView(id="conv-list")

            # Chat panel
            with Vertical(id="chat-panel"):
                yield ScrollableContainer(id="messages")
                with Horizontal(id="input-area"):
                    yield Label(f"{self.current_mode}> ", id="input-mode-label")
                    yield Input(placeholder="Type a message or /command…", id="input-box")

            # Right context panel
            with Vertical(id="context-panel"):
                yield Label("Context", id="ctx-title")
                yield ScrollableContainer(id="ctx-body")

        # Status bar
        yield Label(
            "tab: panels  ctrl+y: memory  ctrl+r: context  ctrl+n: new conversation  ctrl+/: help",
            id="status-bar",
        )

    # ── Watches ────────────────────────────────────────────────────────────────

    def watch_current_mode(self, mode: str) -> None:
        try:
            self.query_one("#input-mode-label", Label).update(f"{mode}> ")
            self.query_one("#header-mode", Label).update(f"[{mode}]")
        except Exception:
            pass
        if self._runtime:
            self._runtime.config.system_prompt = MODES.get(mode, MODES["assistant"])
            self._runtime.reset_history()

    def watch_memory_count(self, count: int) -> None:
        try:
            self.query_one("#header-mem-count", Label).update(f"{count} memories")
        except Exception:
            pass

    def watch_is_thinking(self, thinking: bool) -> None:
        try:
            inp = self.query_one("#input-box", Input)
            inp.disabled = thinking
            inp.placeholder = "Thinking…" if thinking else "Type a message or /command…"
        except NoMatches:
            pass

    def watch_context_panel_visible(self, visible: bool) -> None:
        try:
            panel = self.query_one("#context-panel", Vertical)
            panel.display = visible
        except NoMatches:
            pass

    # ── Input handling ─────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        if text.startswith("/"):
            self._handle_command(text)
        else:
            self._send_message(text)

    def _handle_command(self, cmd: str) -> None:
        # Support quoted args: /mode custom "my prompt here"
        import shlex
        try:
            parts = shlex.split(cmd.lstrip("/"))
        except ValueError:
            parts = cmd.lstrip("/").split()

        verb = parts[0].lower() if parts else ""
        args = parts[1:]

        if verb == "mode" and args:
            mode = args[0].lower()
            if mode == "custom":
                if len(args) > 1:
                    new_prompt = " ".join(args[1:])
                    MODES["custom"] = new_prompt
                    _save_custom_mode(new_prompt)
                    self.current_mode = "custom"
                    self._append_system(f"Custom mode set:\n\n> _{new_prompt}_")
                else:
                    self.current_mode = "custom"
                    self._append_system(
                        f"Switched to **custom** mode.\n\nCurrent prompt:\n\n"
                        f"> _{MODES['custom']}_\n\n"
                        f"To change: `/mode custom \"Your new prompt here\"`"
                    )
            elif mode in MODES:
                self.current_mode = mode
                self._append_system(f"Switched to **{mode}** mode.")
            else:
                self._append_system(
                    f"Unknown mode `{mode}`. Options: {', '.join(MODES)}"
                )

        elif verb == "memory":
            sub = args[0].lower() if args else "show"
            if sub == "evolve":
                self._run_evolve()
            elif sub == "distill":
                self._run_distill()
            else:
                self.action_show_memory()

        elif verb == "tools":
            if self._runtime:
                names = [t.name for t in self._runtime.config.tools]
                self._append_system(
                    "**Available tools:**\n" + "\n".join(f"- `{n}`" for n in names)
                )

        elif verb == "clear":
            if self._runtime:
                self._runtime.reset_history()
            self._active_conv = None
            self._new_conversation()
            self._append_system("Conversation cleared. On-chain memory is untouched.")

        elif verb == "help":
            self.action_show_help()

        elif verb == "checkpoint":
            self._save_checkpoint()

        else:
            self._append_system(f"Unknown command `/{verb}`. Type `/help` for commands.")

    def _send_message(self, text: str) -> None:
        if not self._active_conv:
            self._new_conversation()

        msg = Message(role="user", content=text)
        self._active_conv.messages.append(msg)

        if len(self._active_conv.messages) == 1:
            self._active_conv.title = text[:30]
            self._refresh_sidebar()

        self._render_message(msg)
        self.is_thinking = True

        self.run_worker(self._do_inference(text), exclusive=True)

    async def _do_inference(self, text: str) -> None:
        if not self._runtime:
            reply = (
                "**Setup required** — credentials not configured.\n\n"
                + self._start_error
            )
            ctx = TurnContext()
        else:
            try:
                reply, ctx = await self._real_inference(text)
            except RuntimeError as exc:
                msg_lower = str(exc).lower()
                if "credentials" in msg_lower or "zerog" in msg_lower or "api_key" in msg_lower:
                    reply = (
                        "**Inference not configured.**\n\n"
                        "Set `ZEROG_SERVICE_URL` and `ZEROG_API_KEY` to use 0G Compute:\n\n"
                        "```bash\nexport ZEROG_SERVICE_URL=https://<provider>.0g.ai\n"
                        "export ZEROG_API_KEY=app-sk-...\n```\n\n"
                        "See `.env.example` for full setup."
                    )
                else:
                    reply = f"_Error: {exc}_"
                ctx = TurnContext()
            except Exception as exc:
                reply = f"_Error: {exc}_"
                ctx = TurnContext()

        self._last_reply = reply
        self._last_turn_ctx = ctx

        msg = Message(
            role="assistant",
            content=reply,
            memories_used=ctx.memories_used,
            tool_names=[tc.get("name", "") for tc in ctx.tool_calls],
            latency_ms=ctx.latency_ms,
        )
        if self._active_conv:
            self._active_conv.messages.append(msg)

        self._render_message(msg)
        self._after_inference(ctx)

    async def _real_inference(self, text: str) -> tuple[str, TurnContext]:
        loop = asyncio.get_event_loop()
        turn = await loop.run_in_executor(None, self._runtime.run, text)
        ctx = TurnContext(
            memories_used=turn.retrieved_memories,
            tool_calls=[
                {"name": tc.name, "result": tr.output[:60] if tr.output else ""}
                for tc, tr in zip(turn.tool_calls, turn.tool_results)
            ],
            write_receipts=[
                {"blob_id": wr.blob_id, "chain_tx_hash": wr.chain_tx_hash}
                for wr in turn.write_receipts
            ],
            latency_ms=turn.latency_ms,
            da_hash=getattr(turn, "da_hash", ""),
        )
        return turn.assistant_reply, ctx

    def _after_inference(self, ctx: TurnContext) -> None:
        self.is_thinking = False
        if self._memory:
            self.memory_count = len(self._memory._entries)
        # Update right panel
        try:
            stats = self._memory.stats() if self._memory else {}
            self._update_context_panel(ctx, stats)
        except Exception:
            pass

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _render_message(self, msg: Message) -> None:
        try:
            container = self.query_one("#messages", ScrollableContainer)
        except NoMatches:
            return

        if msg.role == "user":
            md = f"**You**\n\n{msg.content}"
        elif msg.role == "assistant":
            ts = time.strftime("%H:%M", time.localtime(msg.timestamp))
            latency = f" · {msg.latency_ms}ms" if msg.latency_ms else ""
            header = f"**Agent** · {ts}{latency}"
            md = f"{header}\n\n{msg.content}"

            if msg.memories_used:
                mem_lines = "\n".join(f"> {m}" for m in msg.memories_used[:3])
                md += f"\n\n_Memories used:_\n{mem_lines}"

            if msg.tool_names:
                tools_str = ", ".join(f"`{t}`" for t in msg.tool_names)
                md += f"\n\n_Tools called: {tools_str}_"
        else:
            md = f"_{msg.content}_"

        widget = Markdown(md)
        container.mount(widget)
        container.scroll_end(animate=False)

    def _append_system(self, text: str) -> None:
        msg = Message(role="system", content=text)
        self._render_message(msg)

    # ── Actions ────────────────────────────────────────────────────────────────

    def action_show_memory(self) -> None:
        self.push_screen(MemoryModal(self._memory))

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def action_toggle_context(self) -> None:
        self.context_panel_visible = not self.context_panel_visible

    def _update_context_panel(self, ctx: TurnContext, mem_stats: dict) -> None:
        """Update the right context panel with turn data."""
        try:
            body = self.query_one("#ctx-body", ScrollableContainer)
        except NoMatches:
            return

        body.remove_children()

        # ── Memory stats ──
        total = mem_stats.get("total", 0)
        by_type = mem_stats.get("by_type", {})
        lines = [f"[b]Memory[/b]  {total} total"]
        for mt in MemoryType:
            n = by_type.get(mt.value, 0)
            if n:
                lines.append(f"  {mt.value}: {n}")
        body.mount(Static("\n".join(lines), classes="ctx-section"))

        # ── Last turn ──
        if ctx.memories_used:
            mem_text = "[b]Used[/b]\n" + "\n".join(
                f"  › {m[:43]}…" if len(m) > 43 else f"  › {m}"
                for m in ctx.memories_used[:4]
            )
            body.mount(Static(mem_text, classes="ctx-section ctx-used"))

        if ctx.tool_calls:
            tool_lines = ["[b]Tools[/b]"]
            for tc in ctx.tool_calls:
                name = tc.get("name", "?")
                result = tc.get("result", "")[:38]
                tool_lines.append(f"  ✓ {name}")
                if result:
                    tool_lines.append(f"    {result}")
            body.mount(Static("\n".join(tool_lines), classes="ctx-section ctx-tools"))

        if ctx.write_receipts:
            rec = ctx.write_receipts[0]
            blob = rec.get("blob_id", "")[:12]
            tx = rec.get("chain_tx_hash", "")[:12]
            body.mount(Static(
                f"[b]Chain[/b]\n  blob: {blob}…\n  tx:   {tx}…",
                classes="ctx-section ctx-chain",
            ))

        if ctx.da_hash:
            body.mount(Static(
                f"[b]DA[/b]  {ctx.da_hash[:20]}…",
                classes="ctx-section ctx-chain",
            ))

        if ctx.latency_ms:
            body.mount(Static(f"[dim]{ctx.latency_ms}ms[/dim]", classes="ctx-latency"))

    def action_new_conversation(self) -> None:
        if self._runtime:
            self._runtime.reset_history()
        self._new_conversation()

    def action_open_in_editor(self) -> None:
        if not self._last_reply:
            return
        import tempfile, subprocess
        editor = os.environ.get("EDITOR", "nano")
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(self._last_reply)
            fname = f.name
        self.suspend()
        subprocess.run([editor, fname])
        self.resume()

    def action_copy_last(self) -> None:
        if not self._last_reply:
            return
        try:
            import subprocess
            proc = subprocess.run(
                ["pbcopy"], input=self._last_reply.encode(), capture_output=True
            )
            if proc.returncode != 0:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=self._last_reply.encode(),
                )
        except Exception:
            pass

    # ── Checkpoint ─────────────────────────────────────────────────────────────

    def _save_checkpoint(self) -> None:
        """Save conversation history to ~/.0g/checkpoint.json."""
        import json
        checkpoint_dir = Path.home() / ".0g"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = checkpoint_dir / "checkpoint.json"

        data = []
        for conv in self._conversations:
            data.append({
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at,
                "messages": [
                    {
                        "role": m.role,
                        "content": m.content,
                        "timestamp": m.timestamp,
                        "latency_ms": m.latency_ms,
                    }
                    for m in conv.messages
                ],
            })

        try:
            checkpoint_path.write_text(json.dumps(data, indent=2))
            self._append_system(
                f"**Checkpoint saved** → `{checkpoint_path}`\n\n"
                f"{len(self._conversations)} conversation(s), "
                f"{sum(len(c.messages) for c in self._conversations)} messages."
            )
        except Exception as e:
            self._append_system(f"_Checkpoint failed: {e}_")

    # ── Workers for memory operations ──────────────────────────────────────────

    def _run_evolve(self) -> None:
        self.run_worker(self._do_evolve(), exclusive=False)

    async def _do_evolve(self) -> None:
        if not self._memory:
            return
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(None, self._memory.evolve)
        self._append_system(f"**Memory evolved:** {report.summary()}")
        if self._memory:
            self.memory_count = len(self._memory._entries)

    def _run_distill(self) -> None:
        self.run_worker(self._do_distill(), exclusive=False)

    async def _do_distill(self) -> None:
        if not self._memory:
            return
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(None, lambda: self._memory.distill(older_than_days=0))
        self._append_system(
            f"**Distillation complete:** {report.source_count} episodic → "
            f"{report.target_count} semantic entries."
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _new_conversation(self) -> None:
        conv = Conversation()
        self._conversations.append(conv)
        self._active_conv = conv
        self._refresh_sidebar()

        try:
            msgs = self.query_one("#messages", ScrollableContainer)
            msgs.remove_children()
        except NoMatches:
            pass

        if self._start_error:
            self._append_system(
                "**⚠ Setup required**\n\n"
                + self._start_error + "\n\n"
                "_Memory and inference unavailable until credentials are set._"
            )
        elif self._inference_warning:
            self._append_system(
                "**0G** — Verifiable agent memory on 0G Labs.\n\n"
                "⚠ _Inference not configured._ Memory is live on 0G Storage + Chain.\n"
                "Set `ZEROG_SERVICE_URL` and `ZEROG_API_KEY` to enable 0G Compute inference.\n\n"
                "Type a message to start. `/help` for commands."
            )
        else:
            self._append_system(
                "**0G** — Verifiable agent memory on 0G Labs.\n\n"
                "Type a message to start. `/help` for commands."
            )

    def _refresh_sidebar(self) -> None:
        try:
            lv = self.query_one("#conv-list", ListView)
            lv.clear()
            for conv in reversed(self._conversations):
                item = ConversationItem(conv)
                if conv is self._active_conv:
                    item.add_class("active")
                lv.append(item)
        except NoMatches:
            pass

    def _agent_address(self) -> str:
        key = os.environ.get("AGENT_KEY", "")
        if key and len(key) > 10:
            return f"0x{key[2:8]}…" if key.startswith("0x") else f"{key[:6]}…"
        return "demo"

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ConversationItem):
            self._switch_conversation(event.item.conv)

    def _switch_conversation(self, conv: Conversation) -> None:
        from ogmem.inference import ChatMessage as _ChatMessage
        self._active_conv = conv
        if self._runtime:
            self._runtime.reset_history()
            # Replay history into runtime context using proper ChatMessage objects
            for msg in conv.messages:
                if msg.role in ("user", "assistant"):
                    self._runtime._history.append(_ChatMessage(msg.role, msg.content))
        self._refresh_sidebar()
        try:
            msgs = self.query_one("#messages", ScrollableContainer)
            msgs.remove_children()
        except NoMatches:
            pass
        for msg in conv.messages:
            self._render_message(msg)


# ── Entry points ───────────────────────────────────────────────────────────────

def run_tui() -> None:
    """Launch the full TUI."""
    app = ZeroGApp()
    app.run()


def run_oneshot(query: str) -> None:
    """Answer a single question without the TUI (for scripting)."""
    from ogmem.inference import ZeroGInferenceClient, ChatMessage

    service_url = os.environ.get("ZEROG_SERVICE_URL", "")
    api_key = os.environ.get("ZEROG_API_KEY", "")

    if not (service_url and api_key):
        print("Error: ZEROG_SERVICE_URL and ZEROG_API_KEY must be set for one-shot mode.", file=sys.stderr)
        sys.exit(1)

    client = ZeroGInferenceClient(service_url=service_url, api_key=api_key)
    for chunk in client.stream([ChatMessage("user", query)]):
        print(chunk, end="", flush=True)
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_oneshot(" ".join(sys.argv[1:]))
    else:
        run_tui()
