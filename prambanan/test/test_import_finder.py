import unittest
from prambanan.__prambanan__ import MainPrambananProvider
from prambanan.compiler.import_finder import ImportFinder

class TestImportFinder(unittest.TestCase):

    def test_datetime(self):
        provider = MainPrambananProvider("prambanan")
        dt = provider.get_modules()["datetime"]
        imps = ImportFinder.find_imports(dt.path, dt.namespace)
        print imps