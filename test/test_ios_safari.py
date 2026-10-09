"""Protocol boundary tests; no phone or pymobiledevice3 installation required."""

import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tools import ios_safari


class SafariTabTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_navigates_safari_and_waits_for_new_document(self):
        kinds = SimpleNamespace(WEB="web", WEB_PAGE="web-page")
        api = SimpleNamespace(SAFARI="com.apple.mobilesafari", WirTypes=kinds)
        safari = SimpleNamespace(id_="safari", bundle=api.SAFARI, host="")
        page = SimpleNamespace(id_=1, type_=kinds.WEB, web_connection_id="", web_url="https://example.test")
        other_app = SimpleNamespace(id_="other", bundle="com.other.app", host="")
        other_page = SimpleNamespace(id_=999, type_=kinds.WEB, web_connection_id="", web_url="about:blank")
        session = SimpleNamespace(runtime_evaluate=AsyncMock(side_effect=[
            True, None,
            json.dumps({"old": True, "ready": "complete", "href": "https://old.test"}),
            json.dumps({"old": False, "ready": "complete", "href": "https://landing.test"}),
        ]))
        inspector = SimpleNamespace(
            get_open_application_pages=AsyncMock(return_value=[
                SimpleNamespace(application=other_app, page=other_page),
                SimpleNamespace(application=safari, page=page),
            ]),
            inspector_session=AsyncMock(return_value=session),
        )
        url = 'https://example.test/track?a="value"&b=\\test'
        with patch.dict(sys.modules, {"pymobiledevice3.services.webinspector": api}), patch.object(
            ios_safari.asyncio, "sleep", new_callable=AsyncMock
        ) as pause:
            await ios_safari.navigate_safari_tab(inspector, safari, url)
        inspector.inspector_session.assert_awaited_once_with(safari, page)
        self.assertEqual(session.runtime_evaluate.call_args_list[1].args[0], f"window.location.assign({json.dumps(url)})")
        pause.assert_awaited_once_with(0.5)

    async def test_fallback_requires_a_safari_page(self):
        api = SimpleNamespace(SAFARI="com.apple.mobilesafari", WirTypes=SimpleNamespace(WEB="web", WEB_PAGE="web-page"))
        inspector = SimpleNamespace(get_open_application_pages=AsyncMock(return_value=[]))
        with patch.dict(sys.modules, {"pymobiledevice3.services.webinspector": api}):
            with self.assertRaisesRegex(RuntimeError, "打开一个普通网页"):
                await ios_safari.navigate_safari_tab(inspector, SimpleNamespace(id_="safari"), "https://example.test")

    def test_disabled_inspector_has_actionable_error(self):
        error = type("WebInspectorNotEnabledError", (Exception,), {})()
        self.assertIn("开启 Web 检查器", ios_safari.describe_error(error))


if __name__ == "__main__":
    unittest.main()
