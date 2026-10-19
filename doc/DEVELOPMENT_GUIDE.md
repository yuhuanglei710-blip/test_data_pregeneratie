# 零基础开发说明书

这份文档只解决一件事：让第一次接触本项目的人知道代码放在哪里、一次请求怎样流动、修改功能时应该按什么顺序做。

如果只记住一条规则，请记住：

> 界面只负责收集输入和展示结果；真正的业务逻辑放在 `base/` 或 `api/`；耗时操作必须通过 `gui_workers.py` 放到后台线程；每次修改都要跑测试。

## 1. 五分钟启动

项目是 Python + PySide6 桌面工具。推荐 Python 3.10，并优先在 Windows 上开发，因为 Android、iOS 和字体相关功能都包含 Windows 适配。

在项目根目录打开 PowerShell：

```powershell
python --version
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

如果 PowerShell 不允许激活虚拟环境，可以不激活，直接使用：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

界面能打开，就说明本地 Python 和 Qt 已经正常。数据库、后台接口、ADB 和 iPhone 驱动可以按实际开发任务再配置。

## 2. 配置文件

项目根目录的 `env.json` 是统一配置入口，不再读取传统 `.env` 文件。

| 配置段 | 用途 | 常用字段 |
| --- | --- | --- |
| `environment` | 各业务环境的接口地址 | `domain`、`back_ground_url` |
| `platform` | 平台名称与协议数值 | `web`、`android`、`ios` |
| `spin` | 游戏 Token 和下注请求参数 | `spin_api`、`default_bet_cents`、`environments` |
| `local` | 本机工具数据和旧系统迁移配置 | `TOOL_DATA_DIR`、`QUICK_ACCESS_FILE`、`LEGACY_TEST_TOOL_*` |

最小业务环境配置：

```json
{
  "environment": {
    "dev": {
      "domain": "前台 API 域名",
      "back_ground_url": "后台 API 域名"
    }
  }
}
```

注意：

- 不要把真实密码、Token、私钥或个人环境配置提交到 Git。
- `cache/` 下大部分 JSON 是程序运行后生成的本机数据。
- 界面中的金额字段通常使用数据库原始单位“分”，修改前先确认单位。
- “创建账号”“加钱”“下注”“写数据库”都可能操作真实测试环境，不要把单元测试和手工联调混为一谈。

## 3. 项目地图

```text
main.py
  └─ gui.py                    主窗口、页面组装、页面事件
      ├─ gui_theme.py          字体、导航元数据、Qt 样式表
      ├─ gui_widgets.py        通用输入控件、语法高亮、表格按钮
      ├─ gui_workers.py        后台线程任务，不直接修改界面
      ├─ gui_dialogs.py        数据库、模板、场景、安装包编辑弹窗
      ├─ tool_pages.py         时间戳、SSH 主机、快捷访问页面
      ├─ api/background.py     后台管理接口
      └─ base/                 可测试的业务逻辑和本地存储
          ├─ user.py           注册、登录
          ├─ env_config.py     env.json 读取与校验
          ├─ account_batch.py  批量/自定义账号创建
          ├─ add_money.py      加钱
          ├─ spin.py           游戏 Token 和下注
          ├─ tournment_test.py 锦标赛批量流程
          ├─ fund_and_spin.py  加钱并下注的复用流程
          ├─ database_config.py SSH 隧道和数据库配置
          ├─ sql_data.py       SQL 模板
          ├─ api_request.py    API 模板
          ├─ feature_scenario.py 自动化场景
          ├─ player_tier.py    玩家分层计算与构造
          ├─ user_data.py      用户字段更新
          ├─ channel_source.py 渠道参数
          ├─ apk_manager.py    Android APK 缓存和安装
          ├─ ipa_manager.py    iOS IPA 缓存和安装
          ├─ android_log.py    Logcat 抓取
          ├─ quick_access.py   快捷访问数据
          ├─ ssh_host.py       SSH 主机数据和操作
          └─ local_tool_config.py 本机工具路径
```

`test/` 与业务模块对应，测试不应访问真实网络、真实数据库或真实设备。

## 4. 一次操作是怎样跑起来的

以“点击按钮查询用户”为例：

```text
用户点击按钮
  → gui.py 读取输入并做最基本的空值检查
  → gui.py 创建 ApkActionWorker（通用一次性任务）
  → gui_workers.py 在 QThread 中执行
  → api/background.py 请求后台接口
  → Worker 发出 succeeded 或 failed 信号
  → gui.py 回到主线程更新文字、按钮和表格
```

这套分层不是形式主义，而是为了避免两个常见问题：

1. 把网络请求写在按钮回调中，界面会直接卡死。
2. 从工作线程直接修改 Qt 控件，程序会随机崩溃。

所以：

- 纯计算、文件、网络、数据库和设备操作写在 `base/` 或 `api/`。
- Worker 只负责执行函数和传递成功/失败信号。
- 只有 `gui.py`、`tool_pages.py` 中的主线程代码可以更新控件。

## 5. 最常见的开发任务

### 5.1 修改已有业务规则

例如修改玩家分层：

1. 先找 `base/player_tier.py` 中的计算函数。
2. 在 `test/test_player_tier.py` 增加边界测试。
3. 修改业务函数，直到新旧测试都通过。
4. 如果返回值结构改变，再修改 `gui.py` 的展示代码。
5. 更新 README 中的用户规则说明。

不要先改界面。业务规则如果只能通过点界面验证，后续会很难维护。

### 5.2 新增一个 API 调用

1. 决定它属于前台业务还是后台管理：
   - 后台管理接口放 `api/background.py`。
   - 可复用的前台流程放 `base/` 对应模块。
2. 使用已有环境加载逻辑，不要把域名写死。
3. 给请求设置超时。
4. 对业务失败码抛出带上下文的异常。
5. 在测试中 mock HTTP 请求，不访问真实服务。
6. 界面通过 Worker 调用该函数。

### 5.3 新增一个页面

页面导航由 `gui.py` 中两张表共同管理：

- `SECTION_INFO`：左侧导航的分组、标题和说明。
- `SECTION_CONTENT_INDEX`：标题对应 `content_stack` 中的页面位置。

开发顺序：

1. 编写 `_build_xxx_workspace()`，只负责创建控件和连接信号。
2. 在 `WorkflowWindow.__init__` 中把页面加入 `content_stack`。
3. 在 `SECTION_INFO` 增加导航项。
4. 在 `SECTION_CONTENT_INDEX` 声明页面索引。
5. 如果进入页面时要刷新数据，在 `_switch_section()` 中按页面标题触发。
6. 给导航映射和关键交互补测试。

不要在新代码中使用 `index == 7` 这类魔法数字。使用：

```python
SECTION_INDEX["Android 安装"]
```

### 5.4 新增一个后台任务

一次性任务通常不需要新 Worker 类：

```python
worker = ApkActionWorker(lambda: do_slow_work(value))
worker.succeeded.connect(self._on_work_succeeded)
worker.failed.connect(self._on_work_failed)
```

`ApkActionWorker` 是兼容现有代码的名称，本质上使用 `gui_workers.ActionWorker`。只有信号结构或停止方式明显不同，才新建专用 Worker。

长时间持续任务参考 `AndroidLogWorker`；可停止的批量任务参考 `WorkflowWorker`。

### 5.5 新增本地 JSON 配置

参考 `base/quick_access.py`：

1. 用 dataclass 表示单条数据。
2. 读取时兼容文件不存在、空文件和无效记录。
3. 写入前创建父目录。
4. 先写临时文件，再替换正式文件，避免程序中断留下半个 JSON。
5. 给保存、读取、重复项和非法输入写测试。
6. 把生成文件加入 `.gitignore`。

## 6. 测试：每次修改后只做这三步

第一步，快速检查语法：

```powershell
python -m compileall -q api base tools gui.py gui_dialogs.py gui_theme.py gui_widgets.py gui_workers.py tool_pages.py
```

第二步，运行全部单元测试：

```powershell
python -m unittest discover -s test -v
```

第三步，启动界面做一次与本次改动相关的手工检查：

```powershell
python main.py
```

当前测试使用 Python 标准库 `unittest`，不要求安装 `pytest`。终端出现部分中文乱码通常是 Windows 控制台编码显示问题；只要测试结果是 `OK`，不代表业务失败。

只运行一个测试文件：

```powershell
python -m unittest test.test_player_tier -v
```

只运行一个测试：

```powershell
python -m unittest test.test_player_tier.PlayerTierCalculationTests.test_zero_charge_is_not_classified -v
```

## 7. 代码应该怎么写

### 7.1 函数职责

一个函数尽量只做一件事：

- `load_...`：读取并转换数据。
- `save_...`：验证并持久化数据。
- `build_...`：创建值或界面，不执行网络请求。
- `fetch_...` / `query_...`：读取远端数据。
- `update_...`：修改远端或本地数据。
- `_on_...`：处理 Qt 信号。
- `_refresh_...`：刷新已有界面内容。

如果一个函数同时“读取输入、请求接口、写数据库、弹框、刷新表格”，就应该拆分。

### 7.2 类型和数据

- 金额优先使用 `Decimal` 或数据库整数，不使用二进制浮点数做精确金额判断。
- 外部 JSON 先验证类型和必填字段，再创建 dataclass。
- SQL 值使用参数化执行；不要拼接用户输入。
- 路径使用 `pathlib.Path`。
- 环境名只接受 `base.user.SUPPORTED_ENVIRONMENTS` 中的值。

### 7.3 异常和日志

- 底层函数遇到失败应抛出异常，不要静默返回 `None`。
- 异常信息要说明“做什么失败”和关键对象，但不要打印密码、Token 或私钥。
- 界面层捕获异常后恢复按钮状态，并给用户显示可操作的信息。
- 批量流程日志要短，详细响应只在诊断模式输出。

### 7.4 Qt 线程

- 不在主线程执行网络、数据库、ADB、tidevice 或长循环。
- 不在 Worker 中操作 `QWidget`。
- 线程结束时清理 worker/thread 引用。
- 关闭窗口前确认运行中的任务已停止。

## 8. 常见问题

### 界面打不开，提示缺少 PySide6

确认当前命令使用的是安装依赖的 Python：

```powershell
python -c "import sys, PySide6; print(sys.executable, PySide6.__version__)"
```

### 点击接口功能后提示环境未配置

检查根目录 `env.json` 的 `environment.<环境>`，前台接口使用 `domain`，后台接口使用
`back_ground_url`；下注特有参数在 `spin` 配置段。

### 数据库连接失败

依次检查：

1. 环境与参数页是否保存了当前环境的数据库配置。
2. SSH 私钥是否仍存在。
3. SSH 主机、端口和用户名是否正确。
4. SSH 服务器是否能访问目标 MySQL。
5. 数据库名是否填对。

### Android 设备找不到

```powershell
adb devices -l
```

如果系统找不到 `adb`，设置 `ADB_PATH` 为 adb.exe 的完整路径；如果状态是 `unauthorized`，在手机上重新确认 USB 调试授权。

### iPhone 安装或 Safari 归因失败

先完成 README 的 iOS 独立运行环境配置，再检查 Apple Mobile Device 服务、设备信任、解锁状态和 Safari Web 检查器。

### 测试通过但界面卡住

通常是新代码把耗时操作直接写进了按钮回调。把耗时函数放进 `ActionWorker` 或专用 Worker。

## 9. 提交前检查清单

- [ ] 业务逻辑不依赖 Qt 控件。
- [ ] 没有新增硬编码域名、密码、Token、私钥和绝对路径。
- [ ] 没有用页面数字代替 `SECTION_INDEX` 或标题映射。
- [ ] 网络请求有超时。
- [ ] 数据库使用参数化 SQL。
- [ ] 新规则有正常、边界和失败测试。
- [ ] 全部单元测试通过。
- [ ] 手工打开并检查了受影响页面。
- [ ] README 或本说明书已同步更新。

## 10. 不知道从哪里改时

按下面顺序搜索：

1. 在 README 找到功能名称。
2. 在 `gui.py` 搜索页面标题或按钮文字，找到事件入口。
3. 顺着事件调用找到 `base/` 或 `api/` 中的业务函数。
4. 在 `test/` 搜索函数名，先读已有测试。
5. 先补测试，再改业务函数，最后改界面。

例如：

```powershell
rg -n "玩家分层|construct_player_tier" gui.py base test
```

这样查比从 `gui.py` 第一行开始阅读快得多，也更不容易误改无关代码。
