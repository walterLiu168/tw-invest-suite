"""Incomplete or shifted derived cohorts must fail before certification."""
from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_legacy_tables as sync


class DerivedSyncTests(unittest.TestCase):
    def test_partial_cohort_is_rejected(self):
        for values in ([1958]*4, [1958,1957,1958,1958]):
            cursor = MagicMock()
            cursor.fetchone.side_effect = [(n,) for n in values]
            if min(values) == 1958:
                sync.verify_cohort(cursor, '2026-09-17', 1958)
                self.assertEqual(cursor.execute.call_count, 4)
                for call in cursor.execute.call_args_list:
                    self.assertEqual(call.args[1], ('2026-09-17',))
            else:
                with self.assertRaisesRegex(RuntimeError,'Incomplete current sync'):
                    sync.verify_cohort(cursor, '2026-09-17', 1958)

    def test_date_shift_is_rejected_before_any_mutation(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.return_value = (date(2026,9,18),)
        with patch.object(sync.pymysql, 'connect', return_value=connection), \
             patch.dict(sync.os.environ, {'TW_DATA_DATE':'2026-09-17'}), \
             patch.object(sync.traceback,'print_exc'):
            self.assertEqual(sync.main(), 1)
        cursor.execute.assert_called_once_with('SELECT MAX(Date) FROM daily_data2_full')
        connection.commit.assert_not_called()
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
