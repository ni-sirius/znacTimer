import sqlite3
import unittest

from znactime.storage.errors import ClosedPeriodError, StorageValidationError
from znactime.storage.sqlite.connection import translate_error


def _raised_trigger_error(message):
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute(
            f"""
            CREATE TRIGGER reject_sample
            BEFORE INSERT ON sample
            BEGIN SELECT RAISE(ABORT, '{message}'); END
            """
        )
        try:
            connection.execute("INSERT INTO sample(value) VALUES (1)")
        except sqlite3.IntegrityError as error:
            return error
        raise AssertionError("The test trigger did not reject the insert.")
    finally:
        connection.close()


class SQLiteErrorTranslationTest(unittest.TestCase):
    def test_closed_period_trigger_code_maps_to_stable_user_message(self):
        translated = translate_error(
            _raised_trigger_error("ZT:CLOSED_PERIOD:MONTH_IMMUTABLE")
        )

        self.assertIsInstance(translated, ClosedPeriodError)
        self.assertEqual(str(translated), "A closed month cannot be changed or deleted.")
        self.assertNotIn("ZT:", str(translated))

    def test_validation_trigger_code_maps_to_stable_user_message(self):
        translated = translate_error(
            _raised_trigger_error("ZT:VALIDATION:SCHEDULE_OVERLAP")
        )

        self.assertIsInstance(translated, StorageValidationError)
        self.assertEqual(str(translated), "Work-schedule periods cannot overlap.")

    def test_unknown_english_trigger_text_is_not_classified_by_keywords(self):
        translated = translate_error(
            _raised_trigger_error("closed month immutable overlap")
        )

        self.assertIsInstance(translated, StorageValidationError)
        self.assertNotIsInstance(translated, ClosedPeriodError)
        self.assertEqual(
            str(translated),
            "The database rejected an invalid value or relationship.",
        )


if __name__ == "__main__":
    unittest.main()
