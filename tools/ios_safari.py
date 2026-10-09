"""Open a URL through Safari Web Inspector, without developer disk images.

Runs in the isolated iOS runtime. Input and output are JSON over stdio so URLs
are never interpolated into a shell command. Exit zero requires actual navigation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from urllib.parse import urlparse


def describe_error(error: Exception) -> str:
    name = type(error).__name__
    if name == "WebInspectorNotEnabledError":
        return "请在 iPhone 设置 → App → Safari → 高级中开启 Web 检查器，并保持手机解锁。"
    if name == "RemoteAutomationNotEnabledError":
        return "请在 iPhone 设置 → App → Safari → 高级中开启远程自动化，并保持手机解锁。"
    if name in {"LaunchingApplicationError", "DeviceLockedError", "PasswordRequiredError"}:
        return "无法启动 Safari。请解锁 iPhone，确认已信任此电脑，并开启 Safari 的 Web 检查器和远程自动化。"
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return "Safari 打开链接超时。请检查手机网络、解锁状态，以及 Safari 的 Web 检查器和远程自动化设置。"
    if isinstance(error, ImportError):
        return "iOS 控制依赖未安装完整，请按 README 的 iOS 运行环境步骤安装 requirements-ios.txt。"
    return f"{name}: {error}"


async def open_url(udid: str, url: str) -> dict:
    from pymobiledevice3.exceptions import RemoteAutomationNotEnabledError
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.web_protocol.driver import WebDriver
    from pymobiledevice3.services.webinspector import SAFARI, WebinspectorService

    async with await create_using_usbmux(serial=udid, pair_timeout=15) as lockdown:
        inspector = WebinspectorService(lockdown=lockdown)
        try:
            await inspector.connect()
            safari = await inspector.open_app(SAFARI, timeout=10)
            try:
                session = await inspector.automation_session(safari)
            except RemoteAutomationNotEnabledError:
                await navigate_safari_tab(inspector, safari, url)
                return {"status": "opened", "udid": udid, "mode": "safari-tab"}
            session.page_load_timeout = 45000
            driver = WebDriver(session)
            try:
                await driver.start_session()
                await driver.get(url)
                await session.wait_for_navigation_to_complete()
                return {"status": "opened", "udid": udid}
            finally:
                # Only close our automation contexts, never the user's Safari tabs.
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(session.stop_session(), timeout=5)
        finally:
            await inspector.close()


async def navigate_safari_tab(inspector, safari, url: str) -> None:
    """Use a normal Safari page when WebDriver automation is unavailable."""
    from pymobiledevice3.services.webinspector import SAFARI, WirTypes

    pages = await inspector.get_open_application_pages(timeout=2)
    candidates = [
        item for item in pages
        if (item.application.bundle == SAFARI or item.application.host == safari.id_)
        and item.page.type_ in {WirTypes.WEB, WirTypes.WEB_PAGE}
        and not item.page.web_connection_id
    ]
    if not candidates:
        raise RuntimeError(
            "远程自动化不可用，且 Safari 没有可控制的网页。请在手机 Safari 打开一个普通网页"
            "（例如 https://example.com），保持该标签页在前台后重试。"
        )
    # Prefer a blank page, otherwise the newest available Safari tab.
    selected = max(candidates, key=lambda item: (item.page.web_url in {"", "about:blank"}, item.page.id_))
    session = await inspector.inspector_session(selected.application, selected.page)
    marker = "__ios_attribution_navigation_" + str(id(session))
    await session.runtime_evaluate(f"window[{json.dumps(marker)}] = true")
    # iOS WebKit does not expose CDP's Page.navigate. Use its inspector runtime
    # with JSON escaping so URL quotes and backslashes remain literal data.
    await session.runtime_evaluate(f"window.location.assign({json.dumps(url)})")
    # A marker disappearing proves that the new document loaded; a completed old
    # page must never be mistaken for successful navigation.
    for _ in range(90):
        state = await session.runtime_evaluate(
            f"JSON.stringify({{old: !!window[{json.dumps(marker)}], ready: document.readyState, href: location.href}})"
        )
        state = json.loads(state)
        if not state["old"] and state["ready"] == "complete" and state["href"].startswith(("https://", "http://")):
            return
        await asyncio.sleep(0.5)
    raise asyncio.TimeoutError()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        udid = str(payload.get("udid") or "").strip()
        url = str(payload.get("url") or "").strip()
        parsed = urlparse(url)
        if not udid or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("需要有效设备 UDID 和 http(s) 归因链接")
        result = asyncio.run(asyncio.wait_for(open_url(udid, url), timeout=75))
    except Exception as error:
        print(json.dumps({"status": "error", "message": describe_error(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
