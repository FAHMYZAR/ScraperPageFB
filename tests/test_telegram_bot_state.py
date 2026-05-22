import unittest

from telegram_bot_state import UserFlowState


class UserFlowStateTests(unittest.TestCase):
    def test_state_defaults(self) -> None:
        state = UserFlowState()
        self.assertIsNone(state.awaiting)
        self.assertEqual(state.scan_draft, {})
        self.assertEqual(state.last_scan_results, [])
        self.assertEqual(state.last_detail, {})
        self.assertEqual(state.media_options, [])
        self.assertIsNone(state.control_chat_id)
        self.assertIsNone(state.control_message_id)
        self.assertEqual(state.control_message_kind, "text")
        self.assertEqual(state.last_scan_target, "")

    def test_reset_scan_draft(self) -> None:
        state = UserFlowState(scan_draft={"target": "x", "order": "popular"})
        state.reset_scan_draft()
        self.assertEqual(state.scan_draft, {})


if __name__ == "__main__":
    unittest.main()
