"""GUI regression tests for mobile-device workflows."""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QMimeData, QThread, QTimer, QUrl
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from base.apk_manager import ApkInstallResult, CachedApk
from base.api_request import ApiTemplate
from base.player_tier import (
    PLAYER_CHANNEL_FB,
    PLAYER_CHANNEL_GENERAL,
    REGISTRATION_AGE_OVER_7_DAYS,
    TARGET_NET_PROFIT_TOP,
)
from base.sql_data import SqlTemplate
from gui import QueueWriter, WorkflowWindow, configure_application_fonts


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

    def test_apk_drop_zone_accepts_one_local_apk_and_selects_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            apk_path = Path(directory) / "demo.APK"
            apk_path.touch()
            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(str(apk_path))])

            extracted = self.window.apk_drop_zone.apk_path_from_mime_data(
                mime_data
            )
            self.assertEqual(Path(extracted), apk_path)

            self.window.apk_drop_zone.fileDropped.emit(extracted)
            self.app.processEvents()
            self.assertEqual(self.window.apk_source_path.text(), str(apk_path))
            self.assertIn("demo.APK", self.window.apk_drop_zone.hint.text())
            self.assertIn("[drag] 已选择：demo.APK", self.window.apk_log.toPlainText())

    def test_apk_drop_zone_rejects_non_apk_and_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            apk_path = Path(directory) / "demo.apk"
            text_path = Path(directory) / "notes.txt"
            apk_path.touch()
            text_path.touch()

            non_apk = QMimeData()
            non_apk.setUrls([QUrl.fromLocalFile(str(text_path))])
            self.assertEqual(
                self.window.apk_drop_zone.apk_path_from_mime_data(non_apk), ""
            )

            multiple = QMimeData()
            multiple.setUrls(
                [
                    QUrl.fromLocalFile(str(apk_path)),
                    QUrl.fromLocalFile(str(text_path)),
                ]
            )
            self.assertEqual(
                self.window.apk_drop_zone.apk_path_from_mime_data(multiple), ""
            )

    def test_player_tier_manual_preview_and_navigation(self) -> None:
        self.window._switch_section(2)
        self.window.player_preview_charge.setText("10000")
        self.window.player_preview_withdraw.setText("0")
        self.window.player_preview_balance.setText("8000")
        self.window.player_preview_bonus.setText("300")
        self.app.processEvents()

        self.assertEqual(self.window.page_title.text(), "玩家分层")
        self.assertEqual(self.window.content_stack.currentIndex(), 8)
        self.assertEqual(self.window.player_preview_tier.text(), "核心玩家")
        self.assertIn("10.00%", self.window.player_preview_result.text())
        self.assertIn("money  8,000 分", self.window.player_preview_result.text())
        self.assertIn("bonus  300 分", self.window.player_preview_result.text())
        self.assertIn("当前余额  8,300 分", self.window.player_preview_result.text())
        self.assertIn("user_segment", self.window.player_preview_result.text())
        self.assertEqual(len(self.window.player_preview_result.text().splitlines()), 5)
        self.assertEqual(
            self.window.player_tier_registration_age.currentData(),
            REGISTRATION_AGE_OVER_7_DAYS,
        )
        self.assertEqual(
            self.window.player_tier_channel.currentData(),
            PLAYER_CHANNEL_GENERAL,
        )
        self.assertEqual(self.window.player_tier_vip_level.currentData(), 4)
        fb_channel_index = self.window.player_tier_channel.findData(
            PLAYER_CHANNEL_FB
        )
        self.assertGreaterEqual(fb_channel_index, 0)
        self.assertIn(
            "FB 玩家",
            self.window.player_tier_channel.itemText(fb_channel_index),
        )
        net_profit_top_index = self.window.player_tier_target.findData(
            TARGET_NET_PROFIT_TOP
        )
        self.assertGreaterEqual(net_profit_top_index, 0)
        self.assertIn(
            "净利润顶级玩家",
            self.window.player_tier_target.itemText(net_profit_top_index),
        )

    def test_sql_template_selection_builds_runtime_parameter_inputs(self) -> None:
        template = SqlTemplate(
            "sql-parameters",
            "修改 VIP 等级",
            (
                "@userid=xxx;\n"
                "@viplevel=xxx;\n"
                "UPDATE user SET vip_level=@viplevel WHERE id=@userid;"
            ),
        )
        self.window.sql_templates = [template]
        self.window._refresh_sql_template_combos(template.template_id)
        self.app.processEvents()

        self.assertEqual(
            list(self.window.feature_sql_parameter_inputs),
            ["userid", "viplevel"],
        )
        self.window.feature_sql_parameter_inputs["userid"].setText("607166")
        self.window.feature_sql_parameter_inputs["viplevel"].setText("4")

        self.assertEqual(
            self.window._feature_sql_runtime_parameters(),
            {"userid": 607166, "viplevel": 4},
        )

    def test_account_bound_sql_only_asks_for_non_uid_parameters(self) -> None:
        template = SqlTemplate(
            "account-sql-parameters",
            "创建 VIP 账号",
            (
                "@uid=xxx;\n"
                "@viplevel=xxx;\n"
                "@nickname=xxx;\n"
                "UPDATE user SET vip_level=@viplevel, nickname=@nickname "
                "WHERE id=@uid;"
            ),
        )
        self.window.sql_templates = [template]
        self.window._refresh_sql_template_combos()
        self.window.account_sql_template.setCurrentIndex(
            self.window.account_sql_template.findData(template.template_id)
        )
        self.app.processEvents()

        self.assertFalse(self.window.bound_sql_parameter_panel.isHidden())
        self.assertEqual(
            list(self.window.bound_sql_parameter_inputs),
            ["viplevel", "nickname"],
        )
        self.window.bound_sql_parameter_inputs["viplevel"].setText("4")
        self.window.bound_sql_parameter_inputs["nickname"].setText("tester")

        self.assertEqual(
            self.window._bound_sql_runtime_parameters("account", template),
            {"viplevel": 4, "nickname": "tester"},
        )

    def test_application_uses_high_quality_scalable_font(self) -> None:
        ui_family, _monospace_family = configure_application_fonts(self.app)
        font = self.app.font()

        self.assertEqual(font.family(), ui_family)
        self.assertEqual(font.pointSizeF(), 10.0)
        self.assertEqual(
            font.hintingPreference(),
            QFont.HintingPreference.PreferFullHinting,
        )

    def test_api_selection_scaffolds_parameters_and_previews_request(self) -> None:
        template = ApiTemplate(
            "api-preview",
            "查询用户",
            "POST",
            "https://example.test/users/{{userid}}",
            '{"Authorization":"Bearer {{token}}"}',
            '{"user_id":{{userid}}}',
            12,
        )
        self.window.api_templates = [template]
        self.window.api_parameters.setPlainText("{}")
        self.window._refresh_api_templates(template.template_id)
        self.app.processEvents()

        parameters = self.window.api_parameters.toPlainText()
        self.assertIn('"userid"', parameters)
        self.assertIn('"token"', parameters)
        self.assertIn("需要参数：userid, token", self.window.api_parameter_hint.text())
        self.assertFalse(self.window.api_send_button.isEnabled())

        self.window.api_parameters.setPlainText(
            '{"userid":42,"token":"secret"}'
        )
        self.app.processEvents()

        self.assertIn(
            "POST https://example.test/users/42",
            self.window.api_request_preview.toPlainText(),
        )
        self.assertTrue(self.window.api_send_button.isEnabled())

    def test_api_invalid_json_disables_send_with_inline_error(self) -> None:
        template = ApiTemplate(
            "api-invalid",
            "查询用户",
            "GET",
            "https://example.test/users",
        )
        self.window.api_templates = [template]
        self.window._refresh_api_templates(template.template_id)
        self.window.api_parameters.setPlainText("{")
        self.app.processEvents()

        self.assertFalse(self.window.api_send_button.isEnabled())
        self.assertIn("请修正", self.window.api_validation_hint.text())

    def test_queue_writer_keeps_parallel_log_lines_atomic(self) -> None:
        output: list[str] = []
        writer = QueueWriter(output.append)
        barrier = threading.Barrier(2)

        def write_line(value: str) -> None:
            writer.write(value)
            barrier.wait()
            writer.write("\n")

        threads = [
            threading.Thread(target=write_line, args=(value,))
            for value in ("[1/2] SQL OK", "[2/2] SQL OK")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertCountEqual(
            output,
            ["[1/2] SQL OK\n", "[2/2] SQL OK\n"],
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
