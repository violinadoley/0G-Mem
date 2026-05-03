"""
0G Telegram Bot — same agent runtime, same memory, quick mobile interface.

Setup:
    1. Create a bot via @BotFather → get TELEGRAM_BOT_TOKEN
    2. Set env vars (same as TUI):
         TELEGRAM_BOT_TOKEN=your_token
         AGENT_KEY=0x_your_private_key
         ZEROG_SERVICE_URL=https://<provider>.0g.ai
         ZEROG_API_KEY=app-sk-your_secret
    3. Run: python -m telegram_bot

Philosophy:
  - Quick captures and lookups → great here
  - Deep work, diffs, code review → bot redirects to TUI
  - Same encrypted memory store as TUI; one continuous context across both
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from telegram import Update, BotCommand
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from ogmem.memory import VerifiableMemory
from ogmem.proof import MemoryType
from runtime.agent import AgentConfig, AgentRuntime
from runtime.tools import BUILTIN_TOOLS

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Per-user runtime registry ──────────────────────────────────────────────────
# Each Telegram user ID maps to their own AgentRuntime + VerifiableMemory.
# Runtimes idle for more than _RUNTIME_TTL_SECONDS are evicted to prevent leaks.
_runtimes: dict[int, AgentRuntime] = {}
_runtime_last_used: dict[int, float] = {}
_RUNTIME_TTL_SECONDS = 3600  # 1 hour


def _evict_stale_runtimes() -> None:
    """Remove runtimes that have been idle longer than TTL."""
    now = time.time()
    stale = [uid for uid, ts in _runtime_last_used.items() if now - ts > _RUNTIME_TTL_SECONDS]
    for uid in stale:
        _runtimes.pop(uid, None)
        _runtime_last_used.pop(uid, None)

AGENT_MODES = {
    "assistant": (
        "You are a helpful AI assistant with verifiable, persistent memory. "
        "You remember past conversations. Be concise — this is a Telegram chat. "
        "For deep work, code diffs, or multi-step tasks suggest the user use the TUI (`0g` command)."
    ),
    "coding": (
        "You are an expert software engineer. You know the user's stack and projects. "
        "Be direct. For multi-file changes or diffs, tell the user: 'Better in the TUI — run `0g --coding`'."
    ),
    "research": (
        "You are a research assistant. Connect current questions to past research. "
        "Summarise findings concisely for a mobile reading experience."
    ),
}

# ── Runtime factory ────────────────────────────────────────────────────────────

def _get_runtime(user_id: int, mode: str = "assistant") -> AgentRuntime:
    """Get or create an AgentRuntime for a Telegram user."""
    _evict_stale_runtimes()
    _runtime_last_used[user_id] = time.time()

    if user_id not in _runtimes:
        agent_key = os.environ.get("AGENT_KEY", "")
        from eth_account import Account
        wallet_addr = Account.from_key(agent_key).address.lower()

        memory = VerifiableMemory(
            agent_id=wallet_addr,
            private_key=agent_key,
            network="0g-testnet",
        )
        cfg = AgentConfig(
            service_url=os.environ.get("ZEROG_SERVICE_URL", ""),
            api_key=os.environ.get("ZEROG_API_KEY", ""),
            model=os.environ.get("ZEROG_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
            system_prompt=AGENT_MODES[mode],
            tools=list(BUILTIN_TOOLS),
        )
        # Auto-sync on first load: pull all snapshots from chain so memories
        # survive Railway redeploys (no persistent disk on Railway).
        try:
            report = memory.pull_index()
            if report.added > 0:
                logger.info("Auto-sync on startup: pulled %d memories from chain.", report.added)
        except Exception as e:
            logger.warning("Auto-sync on startup failed (non-fatal): %s", e)

        _runtimes[user_id] = AgentRuntime(memory=memory, config=cfg)

    return _runtimes[user_id]


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _escape_md(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    specials = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in specials else c for c in text)


def _format_memories(memories: list[str]) -> str:
    if not memories:
        return ""
    lines = "\n".join(f"• {_escape_md(m[:80])}" for m in memories[:3])
    return f"\n\n_Memories used:_\n{lines}"


def _format_tools(tool_names: list[str]) -> str:
    if not tool_names:
        return ""
    tools = ", ".join(f"`{_escape_md(t)}`" for t in tool_names)
    return f"\n_Tools: {tools}_"


# ── Command handlers ───────────────────────────────────────────────────────────

async def cmd_start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    inference_note = (
        "\n\n⚠️ *Inference not configured* — set `ZEROG\\_SERVICE\\_URL` \\+ `ZEROG\\_API\\_KEY` for 0G Compute\\."
        if not (os.environ.get("ZEROG_SERVICE_URL") and os.environ.get("ZEROG_API_KEY")) else ""
    )
    await update.message.reply_text(
        f"👋 Hey {_escape_md(user.first_name or 'there')}\\!\n\n"
        f"I'm your *0G agent* — verifiable memory, running on 0G Labs infrastructure\\.\n\n"
        f"Same memory as your TUI sessions\\. One continuous context across both\\.\n\n"
        f"Just send me a message\\. Or:\n"
        f"/help — commands\n"
        f"/memory — your memory stats\n"
        f"/mode coding\\|research\\|assistant\n"
        f"/remember \\<text\\> — quick memory capture"
        f"{inference_note}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*0G Bot Commands*\n\n"
        "/start — welcome\n"
        "/help — this message\n"
        "/memory — memory stats \\+ recent entries\n"
        "/mode \\<assistant\\|coding\\|research\\> — switch agent mode\n"
        "/remember \\<text\\> — capture a memory directly\n"
        "/forget — delete the most recently added memory\n"
        "/clear — clear conversation history \\(memory stays\\)\n"
        "/stats — detailed memory breakdown\n\n"
        "*For deep work:* Use the TUI → `0g` in your terminal\\.\n"
        "Your memory is shared — context carries over\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_memory(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    rt = _get_runtime(uid)
    stats = rt.memory.stats()
    total = stats.get("total", 0)
    stale = stats.get("stale_count", 0)
    by_type = stats.get("by_type", {})
    entries = rt.memory._entries[-5:]  # last 5

    lines = [
        f"*Memory* — {_escape_md(str(total))} entries \\| {_escape_md(str(stale))} stale\n",
        "*By type:*",
    ]
    for mt in MemoryType:
        count = by_type.get(mt.value, 0)
        if count:
            lines.append(f"  {_escape_md(mt.value)}: {_escape_md(str(count))}")

    if entries:
        lines.append("\n*Recent:*")
        for e in reversed(entries):
            mt = e.get("memory_type", "episodic")
            text = e.get("text", "")[:60]
            stale_mark = " ⚠" if e.get("stale") else ""
            lines.append(f"  \\[{_escape_md(mt)}\\]{_escape_md(stale_mark)} {_escape_md(text)}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    args = context.args or []
    mode = args[0].lower() if args else ""

    if mode not in AGENT_MODES:
        modes = "\\|".join(AGENT_MODES.keys())
        await update.message.reply_text(
            f"Usage: /mode \\<{modes}\\>",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    rt = _get_runtime(uid, mode=mode)
    rt.config.system_prompt = AGENT_MODES[mode]
    rt.reset_history()

    await update.message.reply_text(
        f"Switched to *{_escape_md(mode)}* mode\\. Session context reset \\(memories untouched\\)\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_remember(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("Usage: /remember \\<text to remember\\>",
                                         parse_mode=ParseMode.MARKDOWN_V2)
        return

    rt = _get_runtime(uid)
    receipt = rt.memory.add(text, memory_type="semantic")

    await update.message.reply_text(
        f"✓ Remembered\\.\n`{_escape_md(receipt.blob_id[:12])}\\.\\.\\.`",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_forget(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    rt = _get_runtime(uid)
    entries = rt.memory._entries

    if not entries:
        await update.message.reply_text("No memories to forget\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    # Delete the last full turn: assistant reply + its paired user message
    to_delete = [entries[-1]]
    if len(entries) >= 2 and entries[-2].get("text", "").startswith("User:"):
        to_delete.append(entries[-2])

    deleted_count = sum(1 for e in to_delete if rt.memory.delete_memory(e["blob_id"]))
    if deleted_count:
        text_preview = _escape_md(to_delete[0].get("text", "")[:50])
        await update.message.reply_text(
            f"Deleted {deleted_count} entr{'y' if deleted_count == 1 else 'ies'}: _{text_preview}_",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await update.message.reply_text("Could not delete\\.", parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_clear(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    rt = _get_runtime(uid)
    rt.reset_history()
    await update.message.reply_text(
        "Session context reset\\. Your on\\-chain memories are untouched\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_sync(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    rt = _get_runtime(uid)
    await update.message.reply_text("Syncing memories from 0G Storage…")

    try:
        report = rt.memory.pull_index()
        if report.added > 0:
            msg = (
                f"*Sync complete* ✓\n"
                f"\\+{_escape_md(str(report.added))} new memories pulled\n"
                f"{_escape_md(str(report.skipped))} already present"
            )
        elif report.failed > 0:
            msg = f"Sync failed: {_escape_md(report.message or 'unknown error')}"
        else:
            msg = f"Already up to date \\({_escape_md(str(report.skipped))} entries\\)\\."
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        await update.message.reply_text(f"Sync error: {_escape_md(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_stats(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    rt = _get_runtime(uid)
    stats = rt.memory.stats()
    top = stats.get("top_retrieved", [])

    lines = ["*Memory Stats*\n"]
    lines.append(f"Total: {_escape_md(str(stats.get('total', 0)))}")
    lines.append(f"Stale: {_escape_md(str(stats.get('stale_count', 0)))}")

    if top:
        lines.append("\n*Most retrieved:*")
        for item in top[:5]:
            count = _escape_md(str(item['count']))
            text = _escape_md(item['text'][:50])
            lines.append(f"  {count}x — {text}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ── Message handler ────────────────────────────────────────────────────────────

# Phrases that suggest deep work → redirect to TUI
_TUI_REDIRECT_KEYWORDS = (
    "refactor", "diff", "patch", "pull request", "pr ", " pr\n",
    "debug this", "rewrite", "migrate", "implement", "architecture",
)


async def handle_message(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    text = update.message.text or ""

    # Check if this looks like deep work
    text_lower = text.lower()
    if any(kw in text_lower for kw in _TUI_REDIRECT_KEYWORDS) and len(text) > 120:
        await update.message.reply_text(
            "This sounds like a deep\\-work task 🛠\n\n"
            "Better in the TUI where I can show diffs and run tools properly\\.\n\n"
            "Run: `0g \\-\\-coding`\n"
            "Your full memory context will be ready\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # Show typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)

    rt = _get_runtime(uid)

    # Run inference in executor to not block the event loop
    loop = asyncio.get_event_loop()
    try:
        turn = await loop.run_in_executor(None, rt.run, text)
    except Exception as exc:
        logger.exception("Inference error for user %d", uid)
        await update.message.reply_text(
            f"⚠️ Error: {_escape_md(str(exc)[:200])}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    reply = turn.assistant_reply
    mem_note = _format_memories(turn.retrieved_memories)
    tool_note = _format_tools([tc.name for tc in turn.tool_calls])
    latency = f"\n_{_escape_md(str(turn.latency_ms))}ms_" if turn.latency_ms else ""

    # Telegram message limit is 4096 chars; truncate if needed
    full_msg = f"{_escape_md(reply)}{mem_note}{tool_note}{latency}"
    if len(full_msg) > 4000:
        full_msg = full_msg[:3990] + _escape_md("…")

    await update.message.reply_text(full_msg, parse_mode=ParseMode.MARKDOWN_V2)


# ── Error handler ──────────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update %s caused error: %s", update, context.error, exc_info=context.error)


# ── Bot setup ──────────────────────────────────────────────────────────────────

def build_application() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Get one from @BotFather and set it in your environment."
        )

    app = Application.builder().token(token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("remember", cmd_remember))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    return app


async def set_commands(app: Application) -> None:
    """Register command list shown in Telegram UI."""
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("help", "Command reference"),
        BotCommand("memory", "Show memory entries"),
        BotCommand("mode", "Switch agent mode (assistant|coding|research)"),
        BotCommand("remember", "Capture a memory: /remember <text>"),
        BotCommand("forget", "Delete last memory"),
        BotCommand("clear", "Clear conversation history"),
        BotCommand("stats", "Memory stats"),
        BotCommand("sync", "Pull latest memories from 0G Storage"),
    ]
    await app.bot.set_my_commands(commands)


def run() -> None:
    """Start the bot (blocking)."""
    agent_key = os.environ.get("AGENT_KEY", "")
    if not agent_key:
        raise RuntimeError(
            "AGENT_KEY not set. Export your 0G wallet private key:\n"
            "  export AGENT_KEY=0x<your_private_key>\n\n"
            "Get testnet OG tokens: https://faucet.0g.ai"
        )

    app = build_application()

    async def post_init(application: Application) -> None:
        await set_commands(application)
        has_inference = bool(os.environ.get("ZEROG_SERVICE_URL") and os.environ.get("ZEROG_API_KEY"))
        logger.info(
            "0G Telegram Bot started. Inference: %s",
            "0G Compute" if has_inference else "OpenAI fallback (ZEROG_SERVICE_URL not set)",
        )

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)
