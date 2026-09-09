import tempfile
import unittest
import zipfile
from pathlib import Path
from datetime import date

from build_acled_map import rows, windows


class AcledImportTests(unittest.TestCase):
    def test_incorrect_dimensions_do_not_truncate_rows_or_blank_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'export.xlsx'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('xl/worksheets/sheet1.xml', '''
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:A1"/><sheetData>
<row r="1"><c r="A1" t="inlineStr"><is><t>COUNTRY</t></is></c><c r="C1" t="inlineStr"><is><t>EVENTS</t></is></c></row>
<row r="2"><c r="A2" t="inlineStr"><is><t>Example</t></is></c><c r="C2"><v>12</v></c></row>
</sheetData></worksheet>''')
            self.assertEqual(list(rows(path)), [{'A': 'COUNTRY', 'C': 'EVENTS'}, {'A': 'Example', 'C': '12'}])

    def test_calendar_windows_clamp_month_ends_and_leap_years(self):
        self.assertEqual(windows(date(2026, 3, 31))['1m'], date(2026, 2, 28))
        self.assertEqual(windows(date(2024, 2, 29))['12m'], date(2023, 2, 28))
        self.assertEqual(windows(date(2026, 8, 15))['7d'], date(2026, 8, 8))


if __name__ == '__main__':
    unittest.main()
