from pathlib import Path
from xml.etree import ElementTree

from ac_trace.test_runner import _selector_from_testcase


def test_selector_from_testcase_matches_prefixed_classname():
    testcase = ElementTree.fromstring(
        '<testcase classname="demo.tests.test_pricing" name="test_standard_shipping_fee" />'
    )
    expected = {
        ("tests.test_pricing", "test_standard_shipping_fee"): (
            "tests/test_pricing.py::test_standard_shipping_fee"
        )
    }

    selector = _selector_from_testcase(Path("/tmp/project/demo"), testcase, expected)

    assert selector == "tests/test_pricing.py::test_standard_shipping_fee"
