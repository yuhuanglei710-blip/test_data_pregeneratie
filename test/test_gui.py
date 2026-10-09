"""GUI regression tests for mobile-device workflows."""

import os
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QThread, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from base.apk_manager import ApkInstallResult, CachedApk
from gui import WorkflowWindow, configure_application_fonts


class ApkConflictPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        configure_application_fonts(cls.app)

    def setUp(self) -> None:
        self.window = WorkflowWindow()
        self.package = CachedApk(
            package_id="package-id",
            name="current.apk",
            path="C:/cache/current.apk",
            md5="abc123",
        )

    def tearDown(self) -> None:
        prompt = self.window.apk_conflict_prompt
        if prompt is not None:
            prompt.done(QMessageBox.StandardButton.No.value)
        self.window.close()
        self.app.processEvents()

    def test_signature_conflict_uses_non_blocking_prompt(self) -> None:
        with patch.object(
            QMessageBox,
            "question",
            side_effect=AssertionError("blocking prompt must not be used"),
        ):
            self.window._on_apk_install_result(
                ApkInstallResult("signature-conflict", "com.example.old"),
                self.package,
                "device-1",
            )

        prompt = self.window.apk_conflict_prompt
        self.assertIsNotNone(prompt)
        assert prompt is not None
        self.assertTrue(prompt.isVisible())
        prompt.done(QMessageBox.StandardButton.No.value)
        self.app.processEvents()
        self.assertIsNone(self.window.apk_conflict_prompt)
        self.assertIn("已取消替换", self.window.apk_log.toPlainText())

    def test_confirmed_replacement_starts_after_prompt_closes(self) -> None:
        with patch.object(self.window, "_run_apk_action") as run_action:
            self.window._on_apk_install_result(
                ApkInstallResult("signature-conflict", "com.example.old"),
                self.package,
                "device-1",
            )
            prompt = self.window.apk_conflict_prompt
            assert prompt is not None
            prompt.done(QMessageBox.StandardButton.Yes.value)
            self.app.processEvents()

        run_action.assert_called_once()

    def test_confirmed_replacement_waits_for_previous_thread_cleanup(self) -> None:
        self.window.apk_action_thread = object()
        self.window.apk_action_quiet = False
        with patch.object(self.window, "_run_apk_action") as run_action:
            self.window._on_apk_install_result(
                ApkInstallResult("signature-conflict", "com.example.old"),
                self.package,
                "device-1",
            )
            prompt = self.window.apk_conflict_prompt
            assert prompt is not None
            prompt.done(QMessageBox.StandardButton.Yes.value)
            self.app.processEvents()

            run_action.assert_not_called()
            self.assertIsNotNone(self.window.pending_apk_action)
            self.window._on_apk_action_finished()
            self.app.processEvents()

        run_action.assert_called_once()

    def test_player_tier_manual_preview_and_navigation(self) -> None:
        self.window._switch_section(2)
        self.window.player_preview_charge.setText("10000")
        self.window.player_preview_withdraw.setText("0")
        self.window.player_preview_balance.setText("8300")
        self.app.processEvents()

        self.assertEqual(self.window.page_title.text(), "玩家分层")
        self.assertEqual(self.window.content_stack.currentIndex(), 8)
        self.assertEqual(self.window.player_preview_tier.text(), "核心玩家")
        self.assertIn("10.00%", self.window.player_preview_result.text())

    def test_application_uses_high_quality_scalable_font(self) -> None:
        ui_family, _monospace_family = configure_application_fonts(self.app)
        font = self.app.font()

        self.assertEqual(font.family(), ui_family)
        self.assertEqual(font.pointSizeF(), 10.0)
        self.assertEqual(
            font.hintingPreference(),
            QFont.HintingPreference.PreferFullHinting,
        )

    def test_apk_worker_result_is_dispatched_on_the_ui_thread(self) -> None:
        callback_threads = []
        loop = QEventLoop()

        def capture_thread(_value: object) -> None:
            callback_threads.append(QThread.currentThread())

        def wait_for_finish() -> None:
            if self.window.apk_action_thread is None:
                loop.quit()
            else:
                QTimer.singleShot(10, wait_for_finish)

        self.window._run_apk_action("thread probe", lambda: object(), capture_thread)
        QTimer.singleShot(10, wait_for_finish)
        QTimer.singleShot(2_000, loop.quit)
        loop.exec()

        self.assertEqual(len(callback_threads), 1)
        self.assertIs(callback_threads[0], self.app.thread())


if __name__ == "__main__":
    unittest.main()
