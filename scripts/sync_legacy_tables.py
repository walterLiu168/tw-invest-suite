#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_legacy_tables_fixed.py — D052h replacement for runtime sync_legacy_tables.py
Differences from runtime:
  - Does NOT close all active market_screen_picks (chatGPT F2 D)
    Closing is handled by market_screen_runner.py after new run
    succeeds. This prevents the 23:30 sync-legacy from closing
    today's 18:00 picks before they get a full day of active
    performance updates.
  - Otherwise delegates to runtime's sync_legacy_tables for the
    legacy 4 tables.

Schedule: daily 23:30 (before publish at 23:50).
"""
import os
import sys
import runpy
from pathlib import Path

RUNTIME_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
RUNTIME_SCRIPT = RUNTIME_DIR / "sync_legacy_tables.py"

# Step 1: run the runtime version with monkey-patch to disable close
sys.path.insert(0, str(RUNTIME_DIR))
import sync_legacy_tables as _runtime

# Monkey-patch: make the "close prior picks" step a no-op
def _no_op(*args, **kwargs):
    print("[sync-legacy-fixed] close_prior_picks SKIPPED (handled by market_screen_runner)")
    return 0

# Find the close function inside runtime module
# The runtime script has it as: cur.execute("UPDATE market_screen_picks SET status='closed' WHERE status='active'")
# We can't easily intercept that, so we run the script with a wrapper.
# Simpler approach: just import and run, but skip the market_screen step entirely.

# Actually, since the runtime's main() does everything in sequence, the
# cleanest approach is to NOT call its main() but replicate the 4-table
# sync logic and skip step 5 entirely.
# But to avoid duplicating, we just exec the runtime script with
# patched 'main' that skips step 5.

# Simpler: override the function that's used.
# After import, _runtime.main is the main function. We replace it
# with a wrapper that calls the original but skips step 5.

import logging
log = logging.getLogger("sync-legacy-fixed")

# Approach: just call the runtime's main with a global flag the runtime
# doesn't know about, so we need to replicate the flow.
# BUT: we can monkey-patch the function in the runtime module that
# closes picks. Looking at the code, it does cur.execute inline. So
# the simplest is to skip the whole step 5 by truncating main's logic.

# Cleanest: load and exec the runtime script, intercept at the
# right point. Since the runtime is just a script (not a module with
# exposed functions), let's just exec it line-by-line with a guard.

# Actually, the runtime's main() doesn't take args. Let's just call
# it but wrap the database cursor.execute to skip the close.

# Simplest robust approach: replicate the 4-table sync by exec'ing
# the runtime file with a patch to the SQL.

_orig_main = _runtime.main

def _patched_main():
    """Same as runtime.main but skip the close-picks step.

    We do this by intercepting pymysql connection's cursor.execute
    and rewriting the close SQL to a no-op.
    """
    import pymysql
    _orig_execute = pymysql.cursors.Cursor.execute

    CLOSE_PICKS_SQL = "UPDATE market_screen_picks SET status = 'closed' WHERE status = 'active'"

    def _intercepted_execute(self, query, args=None):
        # Detect the close-picks SQL and skip it
        if isinstance(query, str) and "UPDATE market_screen_picks SET status = 'closed'" in query:
            log.info(f"[sync-legacy-fixed] SKIPPED close-picks SQL (handled by market_screen_runner)")
            # Return a fake result so .rowcount etc. don't blow up
            return 0
        return _orig_execute(self, query, args)

    pymysql.cursors.Cursor.execute = _intercepted_execute
    try:
        return _orig_main()
    finally:
        pymysql.cursors.Cursor.execute = _orig_execute

if __name__ == "__main__":
    _patched_main()
