"""Allow `python -m tui` to launch the TUI."""
import sys

# Pre-warm the embedding model in the main thread before Textual starts its async
# event loop and thread-pool executor. On macOS Python 3.12+, the first call to
# model.encode() spawns torch's OpenMP worker threads. When that first call happens
# inside run_in_executor() (a worker thread), the macOS fork-safety check raises
# "bad value(s) in fds_to_keep". Running a warmup encode() here, synchronously in
# the main thread before any threads exist, fully initialises torch and avoids the race.
try:
    from ogmem.compute import _get_local_model
    _m = _get_local_model()
    _m.encode("warmup", normalize_embeddings=True)  # fully init torch OpenMP workers
    del _m
except Exception:
    pass  # sentence-transformers not installed or model unavailable — handled at runtime

from tui.app import run_oneshot, run_tui

if len(sys.argv) > 1:
    run_oneshot(" ".join(sys.argv[1:]))
else:
    run_tui()
