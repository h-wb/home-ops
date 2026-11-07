"""API naming must stay inside managed edition folders and preserve reading state."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "kubernetes/apps/main/media/komf/app/scripts/komga_titles.py"
spec = importlib.util.spec_from_file_location("komga_titles", SCRIPT)
names = importlib.util.module_from_spec(spec)
spec.loader.exec_module(names)


class KomgaTitles(unittest.TestCase):
    def setUp(self):
        self.library = {"id": "library", "name": "Volumes", "root": "/data/Manga/Volumes"}
        self.series = {"id": "series", "libraryId": "library", "url": self.library["root"] + "/ONE PIECE [mangabaka-377]/Standard Edition [en]", "metadata": {}}
        self.book = {"id": "book", "seriesId": "series", "url": self.series["url"] + "/file.cbz", "metadata": {"number": "04"}, "readProgress": {"page": 12}}

    def test_standard_and_editions(self):
        self.assertEqual(names.series_title(self.series, self.library), "ONE PIECE")
        self.series["url"] += " (Colored)"
        self.assertEqual(names.series_title(self.series, self.library), "ONE PIECE (Colored)")
        self.series["url"] = self.series["url"].replace("Standard Edition [en] (Colored)", "Collection Edition [en]")
        self.assertEqual(names.series_title(self.series, self.library), "ONE PIECE · Collection Edition")

    def test_chapters_and_decimal_numbers(self):
        self.library["name"] = "Chapters"
        self.series["url"] = self.series["url"].replace("Standard Edition", "Chapters")
        self.book["url"] = self.series["url"] + "/file.cbz"
        self.book["metadata"]["number"] = "01190.5"
        self.assertEqual(names.series_title(self.series, self.library), "ONE PIECE")
        self.assertEqual(names.book_title(self.book, self.series, self.library), "Ch. 1190.5")

    def test_excluded_and_sibling_paths(self):
        for path in ["/data/Manga/Volumes-old/ONE PIECE [mangabaka-377]/Standard Edition [en]", self.series["url"] + "/review", self.series["url"].replace("Standard Edition [en]", "review"), self.series["url"].replace("Standard Edition [en]", ".sento-trash/Standard Edition [en]"), self.series["url"] + "/../Standard Edition [en]"]:
            with self.subTest(path=path):
                self.assertIsNone(names.series_title(self.series | {"url": path}, self.library))
        self.book["url"] = self.series["url"] + "/.sento-stage/file.cbz"
        self.assertIsNone(names.book_title(self.book, self.series, self.library))

    def test_collected_ranges_and_unknown_numbers(self):
        self.book["metadata"]["number"] = "001-002"
        self.assertEqual(names.book_title(self.book, self.series, self.library), "Vol. 1-2")
        self.book["metadata"]["number"] = "Special"
        self.assertIsNone(names.book_title(self.book, self.series, self.library))

    def test_title_only_patches_and_idempotence(self):
        changes = names.plan([self.library], [self.series], [self.book])
        self.assertEqual(len(changes), 2)
        for path, patch in changes:
            self.assertTrue(path.endswith("/metadata"))
            self.assertLessEqual(set(patch), {"title", "titleLock", "titleSort", "titleSortLock"})
            target = self.series if "/series/" in path else self.book
            target["metadata"].update(patch)
        self.assertEqual(names.plan([self.library], [self.series], [self.book]), [])
        self.assertEqual(self.book["readProgress"], {"page": 12})
        self.assertEqual(self.book["metadata"]["number"], "04")

    def test_unmanaged_and_deleted_entries(self):
        self.assertEqual(names.plan([self.library | {"name": "Other"}], [self.series], [self.book]), [])
        self.assertEqual(names.plan([self.library], [self.series | {"deleted": True}], [self.book]), [])


if __name__ == "__main__":
    unittest.main()
