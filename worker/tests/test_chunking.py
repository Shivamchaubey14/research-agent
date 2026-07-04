"""Tests for text extraction and overlapping chunking (worker/rag/chunking.py)."""
import os
import tempfile
import unittest

from worker.rag.chunking import chunk_text, extract_text


class ChunkTextTests(unittest.TestCase):
    def test_empty_and_whitespace_yield_no_chunks(self):
        self.assertEqual(chunk_text("", 100, 10), [])
        self.assertEqual(chunk_text("   \n\t  ", 100, 10), [])

    def test_whitespace_is_collapsed(self):
        chunks = chunk_text("a\n\n b\t c   d", 100, 10)
        self.assertEqual(chunks, ["a b c d"])

    def test_short_text_is_a_single_chunk(self):
        text = "one small paragraph"
        self.assertEqual(chunk_text(text, 900, 150), [text])

    def test_long_text_is_split_into_multiple_chunks(self):
        text = "x" * 2500
        chunks = chunk_text(text, 900, 150)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 900 for c in chunks))

    def test_consecutive_chunks_overlap_by_the_given_amount(self):
        text = "".join(str(i % 10) for i in range(2000))
        size, overlap = 500, 100
        chunks = chunk_text(text, size, overlap)
        for prev, nxt in zip(chunks, chunks[1:]):
            self.assertEqual(prev[-overlap:], nxt[:overlap])

    def test_every_character_is_covered_so_a_boundary_claim_survives(self):
        # A claim straddling a boundary must appear whole in at least one chunk;
        # verify the union of chunks reconstructs the (normalised) text in order.
        text = "word " * 400
        normalised = " ".join(text.split())
        size, overlap = 300, 60
        chunks = chunk_text(text, size, overlap)
        rebuilt = chunks[0]
        for nxt in chunks[1:]:
            rebuilt += nxt[overlap:]
        self.assertEqual(rebuilt, normalised)

    def test_overlap_not_smaller_than_size_falls_back(self):
        # overlap >= size would never advance; the function clamps it to size//4.
        chunks = chunk_text("y" * 40, 10, 10)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c for c in chunks))


class ExtractTextTests(unittest.TestCase):
    def _write(self, name, data):
        fd, path = tempfile.mkstemp(suffix=name)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        self.addCleanup(os.remove, path)
        return path

    def test_reads_plain_text(self):
        path = self._write(".txt", b"hello world")
        self.assertEqual(extract_text(path, "text/plain", "notes.txt"), "hello world")

    def test_markdown_is_read_as_text(self):
        path = self._write(".md", b"# Title\n\nbody")
        self.assertEqual(extract_text(path, "", "notes.md"), "# Title\n\nbody")

    def test_invalid_utf8_is_tolerated(self):
        path = self._write(".txt", b"ok \xff\xfe done")
        # errors="ignore" means it decodes without raising.
        self.assertIn("ok", extract_text(path, "text/plain", "x.txt"))


if __name__ == "__main__":
    unittest.main()
