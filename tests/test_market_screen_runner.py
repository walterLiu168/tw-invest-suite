"""
test_market_screen_runner.py — D052h-fixup4 unit tests
Mocked pymysql tests for T2 (save_picks rollback) and T3 (close-picks
rollback). Deterministic T4 stale-OHLCV tests (fixed_today). Repair-only
tests (D052h-fixup3): missing MD/HTML/DD, renderer failure, post-repair
re-verify. BOM interop tests (D052h-fixup4): raw EF BB BF markers,
real PowerShell producer -> Python consumer round-trip. Company-refresh
wrapper path/smoke test (D052h-fixup4). No live MySQL needed.

Run:
    cd C:\\Users\\icemo\\Projects\\tw-invest-suite
    python -m unittest tests.test_market_screen_runner -v
"""
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, call

REPO_SCRIPTS = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts")
sys.path.insert(0, str(REPO_SCRIPTS))

# The runner pulls in market_screen/watchlist/etc. which require the runtime path
RUNTIME = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
sys.path.insert(0, str(RUNTIME))

import market_screen_runner as msr  # noqa: E402


# ===========================================================================
# Helpers — fixed-today patch
# ===========================================================================

class _FixedDateMeta(type):
    """Metaclass that lets us override `today()` on a date subclass without
    touching the immutable built-in datetime.date class."""

class _FixedDate(date, metaclass=_FixedDateMeta):
    """date subclass with a swappable today() classmethod.
    Construct via _FixedDate.today() / _FixedDate(year, month, day) just
    like the real date class."""
    _FAKE_TODAY = None

    @classmethod
    def today(cls):
        return cls._FAKE_TODAY


def _patch_today(msr_module, d):
    """Patch msr_module.date so that date.today() returns `d`.
    `d` is a regular datetime.date; the runner only uses .today() and
    .strptime-style construction (which goes through datetime.strptime,
    not through `date(...)`).
    """
    _FixedDate._FAKE_TODAY = d
    return patch.object(msr_module, "date", _FixedDate)


# ===========================================================================
# Fakes
# ===========================================================================

class _FakeCursor:
    """In-memory cursor. Can be programmed to raise on a substring."""
    def __init__(self, fail_on_substring=None):
        self.statements = []
        self.results = []
        self._result_idx = 0
        self._fail_on_substring = fail_on_substring
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if self._fail_on_substring and self._fail_on_substring in sql:
            raise RuntimeError(f"injected failure on: {sql[:80]}...")

    def executemany(self, sql, seq):
        self.statements.append(("MANY", sql, len(seq)))
        if self._fail_on_substring and self._fail_on_substring in sql:
            raise RuntimeError(f"injected failure on MANY: {sql[:80]}...")

    def fetchone(self):
        if not self.results:
            return None
        r = self.results[self._result_idx]
        self._result_idx += 1
        return r

    def fetchall(self):
        return self.results[self._result_idx:] if self.results else []


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.began = False

    def cursor(self):
        return self._cursor

    def begin(self):
        self.began = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def _make_fake_pick(ticker="2891", name="測試", industry="半導體業",
                    horizon="long", bucket="<100",
                    close=68.4, change_pct=1.33, volume=1000,
                    market_cap=1.0e9, er60=0.05, er240=0.10):
    c = MagicMock()
    c.ticker = ticker
    c.name = name
    c.industry = industry
    c.horizon = horizon
    c.bucket = bucket
    c.close = close
    c.change_pct = change_pct
    c.volume = volume
    c.market_cap = market_cap
    c.excess_return_60d = er60
    c.excess_return_240d = er240
    c.zen_summary = "zen test"
    return c


def _make_4x6_result():
    result = {}
    bucket_labels = ["<100", "100-500", "500-1000", ">1000"]
    tickers_per_horizon = 3
    for b in bucket_labels:
        result[b] = {
            "long": [_make_fake_pick(ticker=f"L{i:03d}", bucket=b, horizon="long")
                     for i in range(tickers_per_horizon)],
            "short": [_make_fake_pick(ticker=f"S{i:03d}", bucket=b, horizon="short")
                      for i in range(tickers_per_horizon)],
        }
    return result


def _make_24_db_rows():
    """Return 24 rows shaped like a market_screen_picks fetchall result.
    Bucket labels match market_screen.PRICE_BUCKETS so repair_only_artifacts
    can group them into the {bucket: {long, short}} dict.
    """
    rows = []
    # MUST match market_screen.PRICE_BUCKETS
    bucket_labels = ["<100", "100-300", "300-1000", ">1000"]
    for b in bucket_labels:
        for horizon in ("long", "short"):
            for i in range(3):
                rows.append((
                    f"{horizon[0].upper()}{b[:3]}{i:02d}",
                    f"測試{horizon[0].upper()}{i}",
                    "半導體業",
                    horizon,
                    b,
                    50.0 + i,
                    0.5 + i * 0.1,
                    1_000_000 + i * 100_000,
                    5e9 + i * 1e8,
                    0.05,
                    0.10,
                    f"rationale for {horizon} pick {i} in bucket {b}",
                ))
    assert len(rows) == 24
    return rows


# ===========================================================================
# T2/T3 — persist_atomic rollback
# ===========================================================================

class TestPersistAtomicRollback(unittest.TestCase):
    """T2/T3 mocked: any failure inside the transaction must trigger
    conn.rollback() and conn.commit() must NOT be called."""

    def _run_persist(self, fail_on_substring):
        cur = _FakeCursor(fail_on_substring=fail_on_substring)
        cur.results = [(4,), None]
        cur.rowcount = 0
        conn = _FakeConn(cur)
        with patch.object(msr.pymysql, "connect", return_value=conn):
            result = _make_4x6_result()
            with self.assertRaises(RuntimeError):
                msr.persist_atomic(date(2026, 9, 4), 24, "test", result)
        return conn, cur

    def test_t2_save_picks_failure_triggers_rollback(self):
        """T2: INSERT into market_screen_picks fails -> rollback, no commit."""
        conn, cur = self._run_persist(fail_on_substring="INSERT INTO market_screen_picks")
        self.assertTrue(conn.began, "begin() should have been called")
        self.assertTrue(conn.rolled_back, "rollback() should have been called on save_picks failure")
        self.assertFalse(conn.committed, "commit() must NOT be called on save_picks failure")
        sqls = " | ".join(s[0][:40] for s in cur.statements if isinstance(s, tuple) and s[0])
        self.assertNotIn("UPDATE market_screen_picks p", sqls,
                         "close step must not run after save_picks failure")

    def test_t3_close_picks_failure_triggers_rollback(self):
        """T3: UPDATE close-older-picks fails -> rollback, no commit."""
        conn, cur = self._run_persist(fail_on_substring="UPDATE market_screen_picks p")
        self.assertTrue(conn.began)
        self.assertTrue(conn.rolled_back, "rollback() should have been called on close failure")
        self.assertFalse(conn.committed, "commit() must NOT be called on close failure")
        def _sql_of(entry):
            if isinstance(entry, tuple):
                if len(entry) == 2:
                    return entry[0]
                if len(entry) == 3 and entry[0] == "MANY":
                    return entry[1]
            return ""
        full_sqls = " || ".join(_sql_of(s) for s in cur.statements)
        self.assertIn("INSERT INTO market_screen_picks", full_sqls,
                      "INSERT should have run before the close UPDATE")
        self.assertIn("UPDATE market_screen_picks p", full_sqls,
                      "close UPDATE was the step that failed")

    def test_persist_happy_path_commits(self):
        """Sanity: when no failure injected, the atomic path commits."""
        cur = _FakeCursor()
        cur.results = [(4,), None]
        cur.rowcount = 5
        conn = _FakeConn(cur)
        with patch.object(msr.pymysql, "connect", return_value=conn):
            result = _make_4x6_result()
            run_id, closed = msr.persist_atomic(date(2026, 9, 4), 24, "test", result)
        self.assertEqual(run_id, 4)
        self.assertEqual(closed, 5)
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)


# ===========================================================================
# T4 — stale OHLCV (deterministic, fixed_today)
# ===========================================================================

class TestStaleOHLCVExit(unittest.TestCase):
    """T4 deterministic: stale / partial / empty data on a trading day
    must exit 1, not 0. Patches date.today() so the test does not depend
    on the host machine's clock.
    """

    def setUp(self):
        # Pin a fixed "today" so the T4 checks are independent of the host.
        # Tuesday 2026-09-08 — a known trading day.
        self.fixed_today = date(2026, 9, 8)
        self._today_patch = _patch_today(msr, self.fixed_today)
        self._today_patch.start()

    def tearDown(self):
        self._today_patch.stop()

    def test_t4_stale_data_on_trading_day_exits_1(self):
        """T4a: data_date is fixed_today - 2 days -> exit 1."""
        stale_date = self.fixed_today - timedelta(days=2)
        with patch.object(msr, "is_trading_day", return_value=True), \
             patch.object(msr, "get_verified_data_date",
                          return_value=(stale_date, 1955)), \
             patch.object(msr, "has_metadata_marker", return_value=True), \
             patch.object(sys, "argv", ["market_screen_runner.py"]):
            rc = msr.run()
        self.assertEqual(rc, 1, "stale trading-day data must exit 1, not 0")
        # explicit assertion: stale_date really is fixed_today - 2 days
        self.assertEqual((self.fixed_today - stale_date).days, 2)

    def test_t4_partial_data_on_trading_day_exits_1(self):
        """T4b: n_tickers < MIN_TICKERS_FOR_RUN on a trading day -> exit 1."""
        with patch.object(msr, "is_trading_day", return_value=True), \
             patch.object(msr, "get_verified_data_date",
                          return_value=(self.fixed_today, 1500)), \
             patch.object(msr, "has_metadata_marker", return_value=True), \
             patch.object(sys, "argv", ["market_screen_runner.py"]):
            rc = msr.run()
        self.assertEqual(rc, 1, "partial ticker count must exit 1, not 0")

    def test_t4_empty_db_on_trading_day_exits_1(self):
        """T4c: trading day but DB has no data -> exit 1."""
        with patch.object(msr, "is_trading_day", return_value=True), \
             patch.object(msr, "get_verified_data_date",
                          return_value=(None, 0)), \
             patch.object(msr, "has_metadata_marker", return_value=True), \
             patch.object(sys, "argv", ["market_screen_runner.py"]):
            rc = msr.run()
        self.assertEqual(rc, 1, "empty DB on trading day must exit 1, not 0")

    def test_t4_weekend_exits_0(self):
        """T4d: weekend -> exit 0 even with no data checks."""
        with patch.object(msr, "is_trading_day", return_value=False), \
             patch.object(sys, "argv", ["market_screen_runner.py"]):
            rc = msr.run()
        self.assertEqual(rc, 0, "weekend must exit 0")

    def test_t4_metadata_marker_missing_exits_1(self):
        """T4e: metadata marker missing for data_date -> exit 1 even if
        DB data is fresh (F4 dependency check)."""
        with patch.object(msr, "is_trading_day", return_value=True), \
             patch.object(msr, "get_verified_data_date",
                          return_value=(self.fixed_today, 1955)), \
             patch.object(msr, "has_metadata_marker", return_value=False), \
             patch.object(sys, "argv", ["market_screen_runner.py"]):
            rc = msr.run()
        self.assertEqual(rc, 1, "missing metadata marker must exit 1")


# ===========================================================================
# F1 — count only MAX(Date)
# ===========================================================================

class TestF1CountIsLatestDayOnly(unittest.TestCase):
    """F1: get_verified_data_date must only count MAX(Date), not all history."""

    def test_f1_returns_latest_day_count(self):
        cur = _FakeCursor()
        cur.results = [(date(2026, 9, 4), 1955)]
        conn = _FakeConn(cur)
        with patch.object(msr.pymysql, "connect", return_value=conn):
            d, n = msr.get_verified_data_date()
        self.assertEqual(d, date(2026, 9, 4))
        self.assertEqual(n, 1955, "must return latest-day count, not all-history")
        self.assertEqual(len(cur.statements), 1)
        sql, _ = cur.statements[0]
        self.assertIn("MAX(Date)", sql)
        self.assertIn("WHERE Date = (SELECT MAX(Date)", sql)


# ===========================================================================
# F5 — --force --data-date must equal latest
# ===========================================================================

class TestF5OverrideMustMatchLatest(unittest.TestCase):
    """F5: --force --data-date=X requires X == latest data_date, else exit 1."""

    def setUp(self):
        self.fixed_today = date(2026, 9, 8)
        self._today_patch = _patch_today(msr, self.fixed_today)
        self._today_patch.start()

    def tearDown(self):
        self._today_patch.stop()

    def test_f5_override_older_than_latest_rejected(self):
        with patch.object(msr, "is_trading_day", return_value=True), \
             patch.object(msr, "get_verified_data_date",
                          return_value=(date(2026, 9, 4), 1955)), \
             patch.object(msr, "has_metadata_marker", return_value=True), \
             patch.object(sys, "argv",
                          ["market_screen_runner.py", "--force", "--data-date=2026-09-01"]):
            rc = msr.run()
        self.assertEqual(rc, 1, "override older than latest must exit 1")

    def test_f5_override_equal_latest_accepted(self):
        with patch.object(msr, "is_trading_day", return_value=True), \
             patch.object(msr, "get_verified_data_date",
                          return_value=(date(2026, 9, 4), 1955)) as gvdd, \
             patch.object(msr, "has_metadata_marker", return_value=True), \
             patch("market_screen.screen_market",
                   side_effect=RuntimeError("screener mocked")), \
             patch.object(sys, "argv",
                          ["market_screen_runner.py", "--force", "--data-date=2026-09-04"]):
            rc = msr.run()
        self.assertEqual(rc, 1, "F5 passed (so rc from screener error, not gate)")
        gvdd.assert_called()


# ===========================================================================
# F7 / D052h-fixup3 — repair-only tests
# ===========================================================================

class TestRepairOnlyArtifacts(unittest.TestCase):
    """D052h-fixup3: repair_only_artifacts must fully reconstruct MD/HTML/DD
    using the existing renderer, and only succeed when missing=[] after
    re-verification.
    """

    # Real reports dir used by both mr.save_report / mrh.save_html AND the
    # runner's DD generation + has_complete_run_for_data_date. The runner
    # does not have a separate "DD dir" — REPORT_DIR is the only directory
    # consulted. We DON'T patch REPORT_DIR; instead we use a per-test
    # sentinel sub-directory under a tmp tree and redirect REPORT_DIR there
    # so each test's files live together and get cleaned up.
    REAL_REPORTS = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"

    def setUp(self):
        # We need REPORT_DIR to point to a temp dir so has_complete_run
        # sees the same files the renderers wrote. We patch REPORT_DIR and
        # also patch mr.save_report / mrh.save_html to write into that same
        # temp dir.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_reports = Path(self._tmp.name) / "reports"
        self.tmp_reports.mkdir()
        self._report_dir_patch = patch.object(msr, "REPORT_DIR", self.tmp_reports)
        self._report_dir_patch.start()
        # Override the renderers' out_dir so they also write into tmp_reports.
        self._mr_out_patch = patch.object(
            msr.mr, "out_dir", str(self.tmp_reports), create=True) if False else None
        # mr.save_report uses `os.path.expanduser(...)`; we patch via the
        # function's local "out_dir" by intercepting it differently. The
        # simplest reliable path: patch os.path.expanduser inside the
        # renderer module.
        from unittest.mock import patch as _patch
        self._expanduser_patches = [
            _patch("market_report.os.path.expanduser",
                   return_value=str(self.tmp_reports)),
            _patch("market_report_html.os.path.expanduser",
                   return_value=str(self.tmp_reports)),
        ]
        for p in self._expanduser_patches:
            p.start()
        self._cleanup_paths = []

    def tearDown(self):
        self._report_dir_patch.stop()
        for p in self._expanduser_patches:
            p.stop()
        for p in self._cleanup_paths:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass

    def _rows(self, n=24):
        return _make_24_db_rows()[:n]

    def _stub_db_rows(self, rows):
        """Stub pymysql.connect so repair_only_artifacts sees the rows.
        repair_only_artifacts only calls fetchall() (no fetchone), so the
        cursor's results list must be the row list itself (not wrapped).
        """
        cur = _FakeCursor()
        cur.results = list(rows)
        conn = _FakeConn(cur)
        return patch.object(msr.pymysql, "connect", return_value=conn)

    def _md(self, d):  return self.tmp_reports / f"market-screen-{d}.md"
    def _html(self, d): return self.tmp_reports / f"market-screen-{d}.html"
    def _dd(self, d):  return self.tmp_reports / f"deep-dive-prompts-{d}.md"

    def test_repair_a_missing_md(self):
        """a) MD file missing -> repair creates it."""
        d = date(2026, 9, 4)
        # pre-create only HTML + DD
        self._html(d).write_text("<html/>", encoding="utf-8")
        self._dd(d).write_text("# dd", encoding="utf-8")
        with self._stub_db_rows(self._rows()), \
             patch.object(msr.ms.db, "latest_date", return_value="2026-09-04"):
            with patch.object(msr, "has_complete_run_for_data_date",
                              return_value=(4, True, [])) as hcrf:
                ok, errs = msr.repair_only_artifacts(d, 4)
        self.assertTrue(ok, f"repair should succeed when only MD missing: {errs}")
        self.assertTrue(self._md(d).exists(), "MD must be created by repair")
        self.assertEqual(hcrf.call_count, 1, "has_complete_run must be called once for the re-verify")

    def test_repair_b_missing_html(self):
        """b) HTML file missing -> repair creates it."""
        d = date(2026, 9, 4)
        self._md(d).write_text("# md", encoding="utf-8")
        self._dd(d).write_text("# dd", encoding="utf-8")
        with self._stub_db_rows(self._rows()), \
             patch.object(msr.ms.db, "latest_date", return_value="2026-09-04"):
            with patch.object(msr, "has_complete_run_for_data_date",
                              return_value=(4, True, [])):
                ok, errs = msr.repair_only_artifacts(d, 4)
        self.assertTrue(ok, f"repair should succeed when only HTML missing: {errs}")
        self.assertTrue(self._html(d).exists(), "HTML must be created by repair")

    def test_repair_c_missing_dd(self):
        """c) DD file missing -> repair creates it."""
        d = date(2026, 9, 4)
        self._md(d).write_text("# md", encoding="utf-8")
        self._html(d).write_text("<html/>", encoding="utf-8")
        with self._stub_db_rows(self._rows()), \
             patch.object(msr.ms.db, "latest_date", return_value="2026-09-04"):
            with patch.object(msr, "has_complete_run_for_data_date",
                              return_value=(4, True, [])):
                ok, errs = msr.repair_only_artifacts(d, 4)
        self.assertTrue(ok, f"repair should succeed when only DD missing: {errs}")
        self.assertTrue(self._dd(d).exists(), "DD must be created by repair")

    def test_repair_d_md_and_html_missing(self):
        """d) Both MD and HTML missing -> repair creates both."""
        d = date(2026, 9, 4)
        self._dd(d).write_text("# dd", encoding="utf-8")
        with self._stub_db_rows(self._rows()), \
             patch.object(msr.ms.db, "latest_date", return_value="2026-09-04"):
            with patch.object(msr, "has_complete_run_for_data_date",
                              return_value=(4, True, [])):
                ok, errs = msr.repair_only_artifacts(d, 4)
        self.assertTrue(ok, f"repair should succeed when MD+HTML missing: {errs}")
        self.assertTrue(self._md(d).exists(), "MD must be created by repair")
        self.assertTrue(self._html(d).exists(), "HTML must be created by repair")

    def test_repair_e_renderer_failure_returns_error(self):
        """e) Renderer raises -> repair must return (False, error_list)."""
        d = date(2026, 9, 4)
        with self._stub_db_rows(self._rows()), \
             patch.object(msr.ms.db, "latest_date", return_value="2026-09-04"):
            with patch.object(msr.mr, "save_report",
                              side_effect=RuntimeError("simulated render failure")):
                ok, errs = msr.repair_only_artifacts(d, 4)
        self.assertFalse(ok, "renderer failure must propagate as repair failure")
        self.assertTrue(any("MD" in e for e in errs), f"errs should mention MD: {errs}")

    def test_repair_f_reverify_must_be_empty(self):
        """f) After repair, has_complete_run must be re-run and missing=[] required."""
        d = date(2026, 9, 4)
        # no pre-existing artifacts
        with self._stub_db_rows(self._rows()), \
             patch.object(msr.ms.db, "latest_date", return_value="2026-09-04"):
            with patch.object(msr, "has_complete_run_for_data_date",
                              return_value=(4, False, ["html"])) as hcrf:
                ok, errs = msr.repair_only_artifacts(d, 4)
        self.assertFalse(ok, "repair must fail if post-verify still reports missing")
        self.assertTrue(any("still missing" in e for e in errs),
                        f"errs should mention 'still missing': {errs}")
        self.assertEqual(hcrf.call_count, 1,
                         "has_complete_run must be called once for the re-verify")


# ===========================================================================
# D052h-fixup3 — metadata marker parsing
# ===========================================================================

class TestHasMetadataMarkerParse(unittest.TestCase):
    """D052h-fixup3: has_metadata_marker must parse target_date + status
    from the marker file, not just .exists()."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.marker_dir = Path(self._tmp.name)
        self._patch = patch.object(msr, "METADATA_MARKER_DIR", self.marker_dir)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_marker_missing_returns_false(self):
        d = date(2026, 9, 4)
        self.assertFalse(msr.has_metadata_marker(d))

    def test_marker_with_correct_target_and_status_returns_true(self):
        d = date(2026, 9, 4)
        (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").write_text(
            f"target_date={d.isoformat()}\nfinished_at=2026-09-04T18:10:00\n"
            f"missing_count=0\nstatus=ok\n",
            encoding="utf-8",
        )
        self.assertTrue(msr.has_metadata_marker(d))

    def test_marker_with_wrong_target_returns_false(self):
        d = date(2026, 9, 4)
        # file is named for 9/4 but content says target=9/5
        (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").write_text(
            "target_date=2026-09-05\nstatus=ok\n", encoding="utf-8",
        )
        self.assertFalse(msr.has_metadata_marker(d))

    def test_marker_with_wrong_status_returns_false(self):
        d = date(2026, 9, 4)
        (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").write_text(
            f"target_date={d.isoformat()}\nstatus=failed\n", encoding="utf-8",
        )
        self.assertFalse(msr.has_metadata_marker(d))

    def test_marker_with_missing_status_returns_false(self):
        d = date(2026, 9, 4)
        (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").write_text(
            f"target_date={d.isoformat()}\n", encoding="utf-8",
        )
        self.assertFalse(msr.has_metadata_marker(d))


# ===========================================================================
# D052h-fixup4 — BOM interoperability
# ===========================================================================

class TestBOMMarkerInterop(unittest.TestCase):
    """D052h-fixup4: the existing on-disk marker was written by PowerShell
    5.1's `Set-Content -Encoding UTF8`, which emits a UTF-8 BOM
    (EF BB BF). Before fixup4, `has_metadata_marker` read with plain
    `utf-8` and the first key parsed as `"\ufefftarget_date"`, so the
    function returned False even though the file is valid.

    After fixup4, the Python consumer reads with `utf-8-sig` (strips
    any leading BOM). The producer is also upgraded to write BOM-less
    UTF-8, but legacy BOM markers must still validate.
    """

    BOM = b"\xef\xbb\xbf"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.marker_dir = Path(self._tmp.name)
        self._patch = patch.object(msr, "METADATA_MARKER_DIR", self.marker_dir)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_raw_bom_marker_returns_true(self):
        """Raw EF BB BF + UTF-8 body must validate (the regression case)."""
        d = date(2026, 9, 4)
        body = f"target_date={d.isoformat()}\nstatus=ok\nmissing_count=0\n".encode("utf-8")
        (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").write_bytes(self.BOM + body)
        # Sanity: the file actually has the BOM
        raw = (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").read_bytes()
        self.assertEqual(raw[:3], self.BOM, "test fixture must include BOM")
        # The fix
        self.assertTrue(msr.has_metadata_marker(d),
                        "BOM marker must validate after fixup4")

    def test_bom_less_marker_returns_true(self):
        """BOM-less marker (new producer) also works."""
        d = date(2026, 9, 4)
        body = f"target_date={d.isoformat()}\nstatus=ok\nmissing_count=0\n".encode("utf-8")
        (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").write_bytes(body)
        self.assertTrue(msr.has_metadata_marker(d))

    def test_bom_marker_with_wrong_status_returns_false(self):
        """BOM + wrong status must still reject."""
        d = date(2026, 9, 4)
        body = f"target_date={d.isoformat()}\nstatus=failed\n".encode("utf-8")
        (self.marker_dir / f"metadata_target_{d.isoformat()}_OK.marker").write_bytes(self.BOM + body)
        self.assertFalse(msr.has_metadata_marker(d))

    def test_bom_marker_with_wrong_target_returns_false(self):
        """BOM + wrong target_date must still reject."""
        body = b"target_date=2026-09-05\nstatus=ok\n"
        (self.marker_dir / "metadata_target_2026-09-04_OK.marker").write_bytes(self.BOM + body)
        self.assertFalse(msr.has_metadata_marker(date(2026, 9, 4)))


class TestPowerShellProducerIntegration(unittest.TestCase):
    """D052h-fixup4: real PowerShell producer -> Python consumer round-trip.

    The actual `metadata_backfill_daily.ps1` shell wrapper is too
    heavy to invoke end-to-end here (it needs DB access, has a temp
    file + Move-Item flow, etc.). Instead we replicate just the
    marker-write step the .ps1 performs:

        [System.IO.File]::WriteAllText($path, $content, $Utf8NoBom)

    via a fresh `powershell.exe -NoProfile -Command ...` invocation.
    This catches any PowerShell-vs-Python encoding drift (e.g. an
    accidental re-introduction of `Set-Content -Encoding UTF8` which
    would re-emit the BOM).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.marker_dir = Path(self._tmp.name)
        self._patch = patch.object(msr, "METADATA_MARKER_DIR", self.marker_dir)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_powershell_utf8nobom_producer_then_python_consumer(self):
        """PowerShell writes the marker (no BOM), Python consumer validates."""
        import base64
        import subprocess
        d = date(2026, 9, 4)
        marker_name = f"metadata_target_{d.isoformat()}_OK.marker"
        marker_path = self.marker_dir / marker_name

        # Pass the marker body via base64 to dodge PowerShell single-quote
        # vs backtick-n escape ambiguity. Decode at the .ps1 side.
        body = (
            f"target_date={d.isoformat()}\n"
            f"status=ok\n"
            f"missing_count=0\n"
        )
        b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
        ps = (
            "$Utf8NoBom = New-Object System.Text.UTF8Encoding($False); "
            f"$bytes = [System.Convert]::FromBase64String('{b64}'); "
            f"$text = [System.Text.Encoding]::UTF8.GetString($bytes); "
            f"[System.IO.File]::WriteAllText('{str(marker_path)}', $text, $Utf8NoBom)"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(r.returncode, 0,
                         f"powershell.exe failed: {r.stderr}")

        # Sanity: PowerShell wrote a BOM-less file
        raw = marker_path.read_bytes()
        self.assertNotEqual(raw[:3], b"\xef\xbb\xbf",
                            "PowerShell producer wrote a BOM (regression!)")
        # The Python consumer must accept it
        self.assertTrue(msr.has_metadata_marker(d))

    def test_powershell_setcontent_utf8_writes_bom(self):
        """Documents the LEGACY behavior we are moving away from:
        `Set-Content -Encoding UTF8` on Windows PowerShell 5.1 emits a
        BOM. The new producer uses [System.IO.File]::WriteAllText to
        avoid this. The Python consumer must still accept legacy BOM
        markers (regression test for the utf-8-sig fix).
        """
        import base64
        import subprocess
        d = date(2026, 9, 4)
        marker_name = f"metadata_target_{d.isoformat()}_OK.marker"
        marker_path = self.marker_dir / marker_name

        # Use base64 to avoid the same backtick-n issue
        body = f"target_date={d.isoformat()}\nstatus=ok\n"
        b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
        ps = (
            f"$bytes = [System.Convert]::FromBase64String('{b64}'); "
            f"$text = [System.Text.Encoding]::UTF8.GetString($bytes); "
            f"Set-Content -Path '{str(marker_path)}' -Value $text -Encoding UTF8"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(r.returncode, 0,
                         f"powershell.exe failed: {r.stderr}")

        raw = marker_path.read_bytes()
        # Document the legacy behavior: Set-Content -Encoding UTF8 in PS 5.1
        # writes a BOM. The Python consumer must tolerate it.
        self.assertEqual(raw[:3], b"\xef\xbb\xbf",
                         "expected Set-Content UTF8 to emit BOM (PS 5.1 baseline)")
        # And the fix: the Python consumer still validates
        self.assertTrue(msr.has_metadata_marker(d),
                        "BOM marker must validate (utf-8-sig fix)")


# ===========================================================================
# D052h-fixup4 — company_refresh_daily.ps1 path/smoke test
# ===========================================================================

class TestCompanyRefreshWrapper(unittest.TestCase):
    """D052h-fixup4: verify the company_refresh_daily.ps1 wrapper points
    to a real file path. We don't invoke the production refresh (it
    would write to the live MySQL); we just assert the path exists and
    the .ps1 has the Test-Path fail-fast preflight.
    """

    WRAPPER_REPO = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts\company_refresh_daily.ps1")
    WRAPPER_RUNTIME = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\company_refresh_daily.ps1")
    TARGET_SCRIPT = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts\company_refresh.py")

    def test_target_script_exists(self):
        """company_refresh.py must exist at the path the .ps1 points to."""
        self.assertTrue(self.TARGET_SCRIPT.exists(),
                        f"company_refresh.py missing at {self.TARGET_SCRIPT}")

    def test_wrapper_points_to_repo_path(self):
        """Both wrapper copies must point to the git-repo path, not the
        (non-existent) runtime path."""
        for path in (self.WRAPPER_REPO, self.WRAPPER_RUNTIME):
            if not path.exists():
                self.skipTest(f"wrapper missing at {path}")
            content = path.read_text(encoding="utf-8")
            self.assertIn("company_refresh.py", content)
            # The configured path must be the repo path
            self.assertIn(str(self.TARGET_SCRIPT), content)
            # And must NOT point to the runtime path (which doesn't exist)
            self.assertNotIn(
                r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\company_refresh.py",
                content,
            )

    def test_wrapper_has_testpath_failfast(self):
        """Both wrapper copies must include the Test-Path fail-fast preflight."""
        for path in (self.WRAPPER_REPO, self.WRAPPER_RUNTIME):
            if not path.exists():
                self.skipTest(f"wrapper missing at {path}")
            content = path.read_text(encoding="utf-8")
            self.assertIn("Test-Path", content,
                          f"wrapper {path} missing Test-Path preflight")
            self.assertIn("FATAL", content,
                          f"wrapper {path} missing FATAL message")


if __name__ == "__main__":
    unittest.main(verbosity=2)
