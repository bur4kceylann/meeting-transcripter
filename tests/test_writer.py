"""writer.py birim testleri: `python -m unittest tests.test_writer`"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.output.writer import format_srt_timestamp, write_srt, write_txt
from src.transcribe.whisper_engine import Segment, TranscriptResult


def _sample_result() -> TranscriptResult:
    return TranscriptResult(
        segments=[
            Segment(start=0.0, end=2.5, text=" Merhaba dünya."),
            Segment(start=2.5, end=5.0, text=" İkinci cümle burada."),
        ],
        language="tr",
        language_probability=0.99,
    )


class FormatSrtTimestampTests(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_srt_timestamp(0.0), "00:00:00,000")

    def test_milliseconds_rounding(self):
        self.assertEqual(format_srt_timestamp(1.2345), "00:00:01,234")
        self.assertEqual(format_srt_timestamp(1.2346), "00:00:01,235")

    def test_hours_minutes(self):
        self.assertEqual(format_srt_timestamp(3661.5), "01:01:01,500")

    def test_negative_clamped(self):
        self.assertEqual(format_srt_timestamp(-1.0), "00:00:00,000")


class WriterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_txt(self):
        path = write_txt(_sample_result(), self.dir / "out.txt")
        content = path.read_text(encoding="utf-8")
        self.assertEqual(content, "Merhaba dünya.\nİkinci cümle burada.\n")

    def test_write_srt(self):
        path = write_srt(_sample_result(), self.dir / "out.srt")
        content = path.read_text(encoding="utf-8")
        expected = (
            "1\n"
            "00:00:00,000 --> 00:00:02,500\n"
            "Merhaba dünya.\n"
            "\n"
            "2\n"
            "00:00:02,500 --> 00:00:05,000\n"
            "İkinci cümle burada.\n"
        )
        self.assertEqual(content, expected)

    def test_write_srt_empty(self):
        result = TranscriptResult(segments=[], language="tr", language_probability=0.0)
        path = write_srt(result, self.dir / "empty.srt")
        self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_creates_missing_directories(self):
        path = write_txt(_sample_result(), self.dir / "a" / "b" / "out.txt")
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
