"""GUI regression tests for mobile-device workflows."""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QEventLoop,
    QMimeData,
    QPoint,
    QPointF,
    QThread,
    QTimer,
    Qt,
    QUrl,
)
from PySide6.QtGui import QFont, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from base.apk_manager import ApkInstallResult, CachedApk
from base.api_request import ApiTemplate
from base.player_tier import (
    PLAYER_CHANNEL_FB,
    PLAYER_CHANNEL_GENERAL,
    REGISTRATION_AGE_OVER_7_DAYS,
    TARGET_NET_PROFIT_TOP,
)
from base.sql_data import SqlTemplate
from base.quick_access import QuickAccessField, QuickAccessLink
from base.ssh_host import SshHostConfig, SshHostTime
from gui import (
    QueueWriter,
    SECTION_CONTENT_INDEX,
    SECTION_INDEX,
    WorkflowWindow,
    configure_application_fonts,
)
from gui_widgets import ACTION_TABLE_ROW_HEIGHT


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

    def test_mouse_wheel_does_not_change_combo_or_numeric_values(self) -> None:
        combo = QComboBox()
        combo.addItems(["a", "b", "web"])
        combo.setCurrentIndex(1)
        number = QSpinBox()
        number.setRange(0, 10)
        number.setValue(5)

        for widget in (combo, number):
            widget.show()
            widget.setFocus()
            self.app.processEvents()
            event = QWheelEvent(
                QPointF(5, 5),
                QPointF(5, 5),
                QPoint(),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            )
            QApplication.sendEvent(widget, event)

        self.assertEqual(combo.currentIndex(), 1)
        self.assertEqual(number.value(), 5)

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

    def test_user_lookup_navigation_and_result_rendering(self) -> None:
        self.window._switch_section(3)
        self.window.user_lookup_search.setText("13425")
        self.window._on_user_lookup_succeeded(
            [{
                "id": 13425,
                "nickname": "Player_113425",
                "username": "user@example.com",
                "email": "user@example.com",
                "money": 100,
                "bonus": 20,
                "vip_level": 0,
                "charge_total": 0,
                "withdraw_total": 30,
                "charge_times": 4,
                "withdraw_times": 2,
                "distribution_channel": "gpa17drop",
                "login_distribution_channel": "login-drop",
                "channel_code": "Applovin-iOS",
                "advertising_id": "advertising-123",
                "platform": 3,
                "pkg_name": "web",
                "user_segment": 2,
            }]
        )

        self.assertEqual(self.window.page_title.text(), "用户查询")
        self.assertEqual(self.window.content_stack.currentIndex(), 9)
        self.assertFalse(self.window.user_lookup_result_scroll.isHidden())
        self.assertEqual(
            self.window.user_lookup_field_values["advertising_id"].text(),
            "advertising-123",
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["pkg_name"].currentData(),
            "web",
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["platform"].currentData(),
            3,
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["user_segment"].text(),
            "2",
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["money"].text(),
            "100",
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["bonus"].text(),
            "20",
        )

        self.window._on_user_database_updated(
            {
                "vip_level": 5,
                "charge_total": 250000,
                "money": 88000,
                "bonus": 12000,
                "withdraw_total": 32000,
                "charge_times": 9,
                "withdraw_times": 3,
                "pkg_name": "a",
                "platform": 2,
                "user_segment": 3,
            }
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["vip_level"].text(),
            "5",
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["pkg_name"].currentData(),
            "a",
        )

    def test_fuzzy_user_lookup_can_switch_between_matches(self) -> None:
        first = {
            "id": 10,
            "email": "alex.one@example.com",
            "pkg_name": "a",
            "platform": 1,
            "user_segment": 1,
        }
        second = {
            "id": 20,
            "email": "alex.two@example.com",
            "pkg_name": "b",
            "platform": 2,
            "user_segment": 3,
        }

        self.window.user_lookup_search.setText("alex")
        self.window._on_user_lookup_succeeded([first, second])
        self.window.user_lookup_match_selector.setCurrentIndex(1)

        self.assertFalse(self.window.user_lookup_match_selector.isHidden())
        self.assertEqual(self.window.user_lookup_match_selector.count(), 2)
        self.assertEqual(self.window.user_lookup_loaded_id, 20)
        self.assertEqual(
            self.window.user_lookup_database_inputs["pkg_name"].currentData(),
            "b",
        )
        self.assertEqual(
            self.window.user_lookup_database_inputs["platform"].currentData(),
            2,
        )

    def test_current_user_can_execute_uid_bound_sql_template(self) -> None:
        template = SqlTemplate(
            "user-sql",
            "修改当前用户 VIP",
            "@userid=xxx;\n@viplevel=xxx;\n"
            "UPDATE `user` SET vip_level=@viplevel WHERE id=@userid;",
        )
        unrelated = SqlTemplate(
            "global-sql",
            "全局 SQL",
            "@value=xxx;\nUPDATE `settings` SET value=@value;",
        )
        self.window.sql_templates = [template, unrelated]
        self.window._refresh_sql_template_combos(template.template_id)
        self.window.user_lookup_loaded_id = 13425
        self.window.user_lookup_loaded_environment = "dev"
        combo = self.window.user_lookup_sql_template
        combo.setCurrentIndex(combo.findData(template.template_id))
        self.window._refresh_user_lookup_sql_parameter_inputs()

        self.assertGreaterEqual(combo.findData(template.template_id), 0)
        self.assertEqual(combo.findData(unrelated.template_id), -1)
        self.assertEqual(
            list(self.window.user_lookup_sql_parameter_inputs),
            ["viplevel"],
        )
        self.window.user_lookup_sql_parameter_inputs["viplevel"].setText("5")

        with (
            patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch.object(self.window, "_run_user_lookup_action") as run_action,
        ):
            self.window._execute_user_lookup_sql()

        run_action.assert_called_once()
        self.assertEqual(run_action.call_args.args[2], "sql")

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

    def test_device_refresh_guards_follow_navigation_sections(self) -> None:
        cases = (
            ("Android 安装", "_run_apk_action", "_refresh_android_devices"),
            ("iOS 安装", "_run_ios_action", "_refresh_ios_devices"),
            ("Android 日志", "_run_app_log_query", "_refresh_app_log_devices"),
        )
        for title, runner, refresh in cases:
            with self.subTest(title=title), patch.object(self.window, runner) as run:
                self.window.current_section = SECTION_INDEX[title]
                getattr(self.window, refresh)()
                run.assert_called_once()

    def test_every_navigation_item_opens_its_declared_page(self) -> None:
        with (
            patch.object(self.window, "_refresh_android_devices"),
            patch.object(self.window, "_refresh_ios_devices"),
            patch.object(self.window, "_refresh_app_log_devices"),
        ):
            for title, page_index in SECTION_CONTENT_INDEX.items():
                with self.subTest(title=title):
                    self.window._switch_section(SECTION_INDEX[title])
                    self.assertEqual(
                        self.window.content_stack.currentIndex(), page_index
                    )

    def test_ssh_action_table_leaves_full_height_for_buttons(self) -> None:
        ssh_workspace = self.window.ssh_host_workspace
        ssh_workspace.hosts = [
            SshHostConfig(name="开发机", host="127.0.0.1", username="root")
        ]
        with patch("tool_pages.load_ssh_private_keys", return_value={}):
            ssh_workspace._refresh_hosts()

        self.app.processEvents()

        self.assertGreaterEqual(
            ssh_workspace.table.rowHeight(0), ACTION_TABLE_ROW_HEIGHT
        )
        action_cell = ssh_workspace.table.cellWidget(0, 5)
        self.assertIsNotNone(action_cell)
        self.assertEqual(len(action_cell.findChildren(QPushButton)), 4)

    def test_quick_access_selection_shows_copyable_details(self) -> None:
        workspace = self.window.quick_access_workspace
        workspace.links = [
            QuickAccessLink(
                name="测试后台",
                url="https://example.test",
                category="测试环境",
                remark="日常回归",
                fields=[
                    QuickAccessField("username", "tester"),
                    QuickAccessField("password", "secret"),
                ],
            )
        ]
        workspace._refresh()
        self.app.processEvents()

        self.assertEqual(workspace.table.columnCount(), 3)
        self.assertEqual(workspace.detail_title.text(), "测试后台")
        self.assertEqual(workspace.detail_url.text(), "https://example.test")
        self.assertIn("测试环境", workspace.detail_meta.text())
        self.assertEqual(workspace.field_layout.count(), 2)
        password_row = workspace.field_layout.itemAt(1).widget()
        password_value = password_row.findChild(QLineEdit)
        self.assertEqual(password_value.echoMode(), QLineEdit.EchoMode.Password)

        with patch("tool_pages._copy_text") as copy_text:
            copy_buttons = [
                button
                for button in password_row.findChildren(QPushButton)
                if button.text() == "复制"
            ]
            self.assertEqual(len(copy_buttons), 1)
            copy_buttons[0].click()
        copy_text.assert_called_once_with(workspace, "secret")

    def test_ssh_time_page_keeps_full_timestamp_tool(self) -> None:
        workspace = self.window.ssh_host_workspace
        host = SshHostConfig(
            name="开发机",
            host="127.0.0.1",
            username="root",
        )
        workspace.hosts = [host]
        with patch("tool_pages.load_ssh_private_keys", return_value={}):
            workspace._refresh_hosts()
        workspace.time_host_combo.setCurrentIndex(
            workspace.time_host_combo.findData(host.host_id)
        )

        first = SshHostTime("2024-01-01 00:00:00", 1704067200, 1704067200123)
        workspace._show_remote_time(first)
        panel = workspace.remote_timestamp_panel

        self.assertEqual(workspace.tabs.count(), 3)
        self.assertEqual(panel.result.epoch_seconds, 1704067200)
        self.assertEqual(workspace.remote_epoch_seconds.text(), "1704067200")
        self.assertEqual(
            workspace.remote_epoch_milliseconds.text(),
            "1704067200123",
        )
        self.assertEqual(
            set(panel.offset_values),
            {
                "local_time",
                "utc_plus_8",
                "epoch_milliseconds",
                "epoch_seconds",
            },
        )

        panel.set_input("1704060000")
        refreshed = SshHostTime("2024-01-01 00:00:03", 1704067203, 1704067203000)
        workspace._show_remote_time(refreshed)
        self.assertEqual(panel.result.epoch_seconds, 1704060000)

    def test_ssh_time_auto_refresh_does_not_overlap_actions(self) -> None:
        workspace = self.window.ssh_host_workspace
        host = SshHostConfig(
            name="开发机",
            host="127.0.0.1",
            username="root",
        )
        workspace.hosts = [host]
        with patch("tool_pages.load_ssh_private_keys", return_value={}):
            workspace._refresh_hosts()
        workspace.tabs.setCurrentIndex(2)

        with (
            patch.object(workspace, "_load_remote_time") as load_time,
            patch.object(workspace, "is_busy", return_value=False),
        ):
            workspace._auto_refresh_remote_time()
            load_time.assert_called_once_with()

        with (
            patch.object(workspace, "_load_remote_time") as load_time,
            patch.object(workspace, "is_busy", return_value=True),
        ):
            workspace._auto_refresh_remote_time()
            load_time.assert_not_called()

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
