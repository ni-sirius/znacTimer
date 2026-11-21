"""Bounded retention and immutable reuse for the public interruption parser."""
from dataclasses import FrozenInstanceError
import unittest

from znactime.core.time_utils import _cached_parse_interruption_text, parse_interruption_input


class InterruptionCacheTest(unittest.TestCase):
    def setUp(self):
        _cached_parse_interruption_text.cache_clear()
        self.addCleanup(_cached_parse_interruption_text.cache_clear)

    def test_equivalent_inputs_reuse_an_immutable_result(self):
        first = parse_interruption_input("12:00-12:30")
        self.assertIs(parse_interruption_input(" 12:00-12:30 "), first)
        self.assertEqual(_cached_parse_interruption_text.cache_info().hits, 1)
        with self.assertRaises(FrozenInstanceError):
            first.hours = 99
        self.assertEqual(parse_interruption_input("12:00-12:30").hours, 0.5)
        self.assertIs(parse_interruption_input(""), parse_interruption_input("00:00"))

    def test_typed_inputs_are_converted_on_every_call(self):
        class TypedInput:
            calls = 0

            def __str__(self):
                self.calls += 1
                return "0030"

        value = TypedInput()
        first = parse_interruption_input(value)
        self.assertIs(parse_interruption_input(value), first)
        self.assertEqual(value.calls, 2)
        self.assertEqual(first.normalized, "00:30")
        self.assertIsNone(parse_interruption_input([]))
        self.assertIsNone(parse_interruption_input({}))
        self.assertIsNone(parse_interruption_input(None))

    def test_invalid_results_preserve_none_and_can_be_reused(self):
        self.assertIsNone(parse_interruption_input("invalid"))
        self.assertIsNone(parse_interruption_input("invalid"))
        self.assertEqual(_cached_parse_interruption_text.cache_info().hits, 1)

    def test_cache_is_bounded_and_evicts_the_oldest_result(self):
        first = parse_interruption_input("00:00")
        for minute in range(1, 513):
            latest = parse_interruption_input(f"{minute // 60:02d}:{minute % 60:02d}")
        info = _cached_parse_interruption_text.cache_info()
        self.assertEqual((info.maxsize, info.currsize), (512, 512))
        self.assertIsNot(parse_interruption_input("00:00"), first)
        self.assertIs(parse_interruption_input("08:32"), latest)

    def test_key_length_boundary_and_long_input_bypass(self):
        boundary = "12:00-" + " " * 1013 + "12:30"
        self.assertEqual(len(boundary), 1024)
        first = parse_interruption_input(boundary)
        self.assertIs(parse_interruption_input(boundary), first)
        before = _cached_parse_interruption_text.cache_info()
        longer = boundary.replace("-", "- ")
        second = parse_interruption_input(longer)
        self.assertEqual(second, first)
        self.assertIsNot(parse_interruption_input(longer), second)
        self.assertIsNone(parse_interruption_input("x" * 100000))
        self.assertEqual(_cached_parse_interruption_text.cache_info(), before)
        # Only the short stripped key is retained for large outer whitespace.
        self.assertEqual(parse_interruption_input(" " * 100000 + "00:30").normalized, "00:30")
        self.assertEqual(_cached_parse_interruption_text.cache_info().currsize, 2)

    def test_changed_input_does_not_reuse_stale_open_period_data(self):
        opened = parse_interruption_input("12:00-...")
        completed = parse_interruption_input("12:00-12:30")
        self.assertTrue(opened.has_incomplete)
        self.assertEqual(opened.hours, 0)
        self.assertFalse(completed.has_incomplete)
        self.assertEqual(completed.hours, 0.5)
        self.assertIs(parse_interruption_input("12:00-..."), opened)
