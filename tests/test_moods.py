"""Fast mood + model routing. Restores prior mood afterwards."""
import unittest

import moods
from moods.router import FAST_MODEL, pick_model
from moods.models import featured_models


class MoodTest(unittest.TestCase):
    def setUp(self):
        self._prev = moods.current_name()

    def tearDown(self):
        moods.set_mood(self._prev)

    def test_fast_mood_exists_and_pins(self):
        m = moods.set_mood("fast")
        self.assertIsNotNone(m)
        self.assertTrue(m.prefer_fastest)
        self.assertLessEqual(m.max_tokens, 100)

    def test_other_moods_unaffected(self):
        self.assertFalse(moods.MOODS["thinking"].prefer_fastest)

    def test_routing_auto_pins_fastest(self):
        self.assertEqual(
            pick_model("hello", mood_fastest=True), FAST_MODEL)

    def test_routing_manual_wins(self):
        self.assertEqual(
            pick_model("hello", manual_override="model-x",
                       mood_fastest=True), "model-x")

    def test_featured_has_fastest_tag(self):
        tags = {m["id"]: m.get("tag") for m in featured_models()}
        self.assertEqual(tags.get(FAST_MODEL), "fastest")

    def test_preset_params_are_provider_safe(self):
        from moods.presets import MOODS
        for name, m in MOODS.items():
            self.assertIsInstance(m.temperature, (int, float), name)
            self.assertGreaterEqual(m.temperature, 0, name)
            self.assertLessEqual(m.temperature, 2, name)
            self.assertIsInstance(m.max_tokens, int, name)
            self.assertGreater(m.max_tokens, 0, name)
            self.assertIsInstance(m.voice_rate, str, name)
            self.assertIsInstance(m.voice_pitch, str, name)


if __name__ == "__main__":
    unittest.main()
