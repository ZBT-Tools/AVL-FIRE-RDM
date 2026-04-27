import sys
import unittest
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from asix_parser import parse_asix
from firem_name_parser_integration import build_domain_lookup_from_asix


class AsixParserTests(unittest.TestCase):
    def test_attributes_are_kept_under_attrs_and_children_sort_by_index(self):
        xml = """<root><item index=\"2\" name=\"two\"/><item index=\"1\" name=\"one\"/></root>"""

        parsed = parse_asix(StringIO(xml))
        items = parsed["root"]["item"]

        self.assertEqual([item["_attrs"]["name"] for item in items], ["one", "two"])
        self.assertEqual([item["_attrs"]["index"] for item in items], ["1", "2"])

    def test_domain_lookup_reads_name_from_attrs_bucket(self):
        xml = """<root><domain name=\"Cathode\" component=\"electrode\" domain=\"porous\"/></root>"""

        parsed = parse_asix(StringIO(xml))
        lookup = build_domain_lookup_from_asix(parsed)

        self.assertEqual(
            lookup["Cathode"],
            {"component": "electrode", "domain": "porous"},
        )


if __name__ == "__main__":
    unittest.main()
