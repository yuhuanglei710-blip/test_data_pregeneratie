# test_data_pregeneratie

通过前台接口、后台接口和测试工具预生成测试数据，用于简化复杂功能的测试准备工作。

## 目录结构

- `api/`：后台等通用 API 客户端。
- `base/`：用户注册、加钱、下注及批量账号工作流。
- `tools/`：时间戳等无业务依赖的工具。
- `test/`：不访问网络的单元测试。
- `cache/`：token 等临时缓存。
- `*.env`：不同运行环境的本地配置，不提交到 Git。

## 安装

建议使用虚拟环境，并安装项目依赖：

```shell
pip install -r requirements.txt
```

复制 `.env_example` 或新建对应环境文件，例如 `dev.env`：

```dotenv
domain="前台接口域名，例如 hdapi.ushdev.top"
background_domain="后台接口域名，例如 hdadmin.ushdev.top"
```

## 使用

启动图形界面：

```shell
python main.py
```

界面在“数据准备”分组下提供账号生成、锦标赛造数和玩家分层三个功能页。“账号生成”可选择按原逻辑批量注册随机邮箱账号，或使用
自定义邮箱定制创建一个指定账号；两种方式都会导出账号信息。创建账号时不再手动填写
Channel Code，而是选择是否进入 B 面及是否启用新手套路：不进入 B 面固定使用 `Organic`，
进入 B 面时根据日志库 `log_user_source` 的 `enter_pkg` 与 `cfg_channel_group` 自动匹配渠道源。
生产环境 `prod` 保留从已维护列表中手动选择 Channel Code，不读取日志库自动匹配。
“更新参数”会从 `ush_log_<环境>` 刷新渠道参数并缓存到本机
`cache/channel_sources.json`。“锦标赛造数”会注册
账号、加钱并完成固定或随机次数的下注。账号处理和下注都能分别选择串行或并行；串行
模式会固定使用一个执行线程，并禁用对应的并发数。界面会实时显示运行日志及完成进度，
注册平台可选择 Android 或 iOS。左侧导航按“数据准备、接口与流程、设备工具、系统”分组，
可在账号生成、锦标赛造数、玩家分层、SQL 数据模板、API 请求模板、自动化场景、Android 安装、
iOS 安装、Android 日志和环境与参数之间切换；环境与参数页维护的 Channel Code 作为两个账号任务页的渠道匹配优先级，页面也可
维护 SSH 数据库连接。两类配置都按运行环境
隔离，切换环境时会自动加载对应参数。数据库连接通过 SSH 隧道访问 MySQL，SSH 只允许
使用界面导入的私钥文件，不使用密码、SSH Agent 或自动密钥搜索，并可在界面中测试连接。
环境与参数页的环境选择框旁会以红色或绿色呼吸状态显示数据库是否已配置，点击状态入口
可配置或编辑当前环境的连接参数。SSH 私钥在环境与参数页的私钥库中单独导入和维护，各环境连接
只需选择已导入的私钥；仍被环境引用的私钥不能删除。
每个环境可分别设置业务库和日志库名称，更新渠道参数时会读取当前环境配置的日志库。
连接信息保存在本机 `cache/database_connections.json`（已排除版本控制），数据库密码不会
输出到运行日志。
批量任务只维持当前并发数的待执行账号，不会一次性创建全部任务。点击“停止”后会立即
停止派发新账号并取消尚未开始的任务；当前正在进行的网络请求使用 10 秒超时，退出后
界面恢复操作。进度仅统计实际执行完成的账号，不把取消任务显示成完成。绑定 SQL 或
包含 SQL 的自动化场景会复用同一环境的 SSH 隧道，并限制并发数据库连接，避免批量任务
为每个账号同时建立 SSH 握手。

## 玩家分层

“玩家分层”页支持按环境和 UID 读取 `user.charge_total`（累计充值）、
`user.withdraw_total`（累计提现）与 `user.money`（当前余额），金额均使用数据库原值“分”。
净利润与利润率按以下公式计算：

```text
净利润 = 累计充值 - 累计提现 - 0.07 × 累计充值 - 0.035 × 累计提现 - 当前余额
利润率 = 净利润 ÷ 累计充值
```

累计充值为 0 时显示“未分层”；否则按利润率分为套利用户（小于 -1%）、普通用户
（大于等于 -1% 且小于 10%）、核心玩家（大于等于 10% 且小于 20%）和顶级玩家
（大于等于 20%）。“一键构造目标分层”使用固定的 `10000` 分累计充值，累计提现设为
`0`，并调整当前余额以命中目标利润率，避免为迁就原余额而生成特别大的充值金额。该操作会
更新 `charge_total`、`withdraw_total` 和 `money`，并在写库前要求确认。右侧“手动输入预览”
仅在本地计算，不连接或修改数据库。

## Android 设备安装

“Android 安装”页会在进入页面时检测 Android 设备，之后只在点击“刷新”时再次检测，不会定时
刷新整个页面；同时支持选择 APK 建立本地缓存。安装包按
MD5 去重，缓存文件和元数据分别保存在 `cache/apks/` 与
`cache/apk_packages.json`。每个缓存项可维护显示名称、归因链接和备注，并可单独执行安装、
打开归因链接或“归因+安装”。归因链接使用不限制文本长度的多行输入，并通过 ADB 标准输入
发送，避免受到 Windows 命令行长度限制。ADB 默认从系统 `PATH` 查找，也可通过 `ADB_PATH` 环境变量
指定完整路径。

安装默认使用 `adb install -r -d`，允许覆盖和降级。如果设备上存在同包名但签名不一致的
旧应用，界面会显示旧包名，并在卸载前询问是否替换；只有确认后才会卸载旧应用并安装新包，
同时明确提示卸载会清空该应用的本地数据。

## iOS 设备安装

“iOS 安装”页支持选择本地 IPA，或从 `http://` / `https://` 地址下载 IPA。下载内容先写入
临时文件，读取包信息后按 MD5 写入 `cache/ipas/`，元数据保存在
`cache/ipa_packages.json`。缓存和安装流程仅读取 IPA 的 Bundle ID 及可选的描述文件信息，
不进行本地签名、证书期限或设备白名单校验，是否允许安装由 iOS 在安装阶段判断。

iOS 真机连接和 IPA 安装使用 `tidevice`；Safari 打开链接使用 `pymobiledevice3` 的
Web Inspector 接口，避免新版 iOS 上旧 `tidevice launch` 下载开发者镜像失败。
Windows 上需安装可用的
Apple Mobile Device 驱动/服务，并在已解锁的 iPhone 上信任当前电脑。每个缓存项都可以
单独安装、打开归因链接，或执行“归因+安装”；组合操作的顺序为读取包信息、Safari
打开归因链接、安装 IPA。安装失败时显示 tidevice 返回的错误。

首次配置 Safari 控制环境（Windows，Python 3.10 及以上）：

```powershell
python -m venv cache/ios-runtime
cache/ios-runtime/Scripts/python.exe -m pip install -r requirements-ios.txt
```

程序优先使用这个独立环境，不改动主程序的 Python 依赖；其他系统的虚拟环境解释器为
`cache/ios-runtime/bin/python`。也可以在主程序环境安装 `requirements-ios.txt`。
在 iPhone「设置 → App → Safari → 高级」中开启「Web 检查器」，
并保持设备解锁、信任此电脑。旧 iOS 的 Safari 设置直接位于「设置 → Safari」。
如支持「远程自动化」，可以开启后使用自动化会话；未开启或没有此开关时，程序自动
使用普通 Safari 网页标签页（优先空白页，否则最新的可控制页面），在该页导航到归因链接。
首次使用时请在 Safari 打开一个普通网页；如没有可控制页面，程序会明确提示。
链接通过标准输入传递，不放入命令行；只有 Safari 确认导航完成后才继续安装。
Web 检查器未开启、导航失败或超时时会停止组合流程并提示原因，不会跳过归因直接安装。

## Android 应用日志

“Android 日志”页通过 ADB 实时读取 Android `logcat`。进入页面时会检测设备；选择设备后可读取
第三方应用包名，也可手动输入包名。留空应用会读取整机日志，选择应用时会先获取当前主进程
PID，再使用 `logcat --pid` 过滤，因此应用必须已经启动；应用重启导致 PID 变化后需要重新开始
抓取。最低日志级别支持 Verbose、Debug、Info、Warning、Error 和 Fatal，关键字过滤不区分
大小写。

“清空显示”只清空界面，不会删除手机日志。只有主动勾选“开始前清空手机 Logcat 缓冲区”时
才会执行一次 `adb logcat -c`，开始后该选项会自动复位。默认不清空时，会先读取符合条件的
现有 Logcat 缓冲，再继续实时输出。界面最多保留最近 20,000 行；如需长时间抓取，可在开始前选择
`.log` 输出文件，符合设备、应用和级别条件的完整输出会实时写入该文件，界面关键字过滤不会
删减文件内容；重复使用已有文件时会先确认是否覆盖。也可以随时将界面当前显示的日志另行导出。

注册单个开发环境用户：

```shell
python -m base.user
```

批量注册、加钱并下注：

```shell
python -m base.tournment_test
```

批量脚本会真实调用开发环境接口，并将成功创建的账号写入项目根目录下的
`accounts.txt`。运行前请确认环境文件和脚本顶部的数量、金额、下注次数符合预期。

注册默认使用精简日志；每次下注会输出一行紧凑的 JSON 结果。需要查看接口状态与完整
响应时，可在代码调用中传入 `verbose=True`。失败响应会保留状态码和截断后的响应内容。
批量流程会复用未过期的游戏 token。串行下注会将每次响应中的 `session_id` 传给下一次
下注；并行下注会复用 token，但每次请求使用独立 session。账号并发和单账号下注并发
可以分别设置，默认都是 5。
选择 `huidu` 灰度环境时，游戏 token 会从灰度 `self_game_url` 获取，网页 Origin、token
缓存和游戏 session 也会按环境隔离，不会与测试环境混用。
选择 `yy` 环境时，游戏 token 使用
`https://yyapi.ushdev.top/v1/gamehall/self_game_url`，请求 Origin 和退出/收银地址使用
`https://yyres.ushdev.top`，不会回退到个人服接口。
默认单次下注金额为 `1000` 美分，可通过 `bet_amount` 参数调整。

## SQL 数据模板

“SQL 数据模板”页可新增、编辑和删除命名 SQL 模板。模板需要用
`@userid=xxx;` 声明 User ID，执行时会自动转换为 MySQL `SET` 语句，后续语句可直接使用
`@userid`，例如：

```sql
@userid=xxx;
UPDATE user_other SET some_flag=1 WHERE user_id=@userid;
```

独立执行时，界面中填写的 User ID 会替换 `xxx`；在“账号生成”或
“锦标赛造数”页绑定 SQL 模板时，会自动使用新账号 UID。多条 DML 语句在同一数据库
事务中执行（DDL 遵循 MySQL 自动提交规则），模板保存在本机
`cache/sql_templates.json`（已排除版本控制）。
SQL 模板选择框支持按标题模糊检索；执行日志只输出模板名、UID 和成功状态。
“SQL 数据模板”页以标题列表管理模板，右侧为独立执行参数，底部仅保留紧凑日志栏。

## API 请求模板

“API 请求模板”页可按标题保存、检索、编辑和删除 HTTP 请求模板。模板支持
`GET`、`POST`、`PUT`、`PATCH` 和 `DELETE`，可配置接口路径、JSON 格式的 Headers、
Body 与请求超时时间。模板保存在本机 `cache/api_templates.json`（已排除版本控制）。
发送页选择 `dev`、`huidu`、`prod`、`yy` 或 `individual` 后，会读取对应 `.env` 文件中的
`domain` 并自动拼接以 `/` 开头的接口路径；例如 `yy` 会使用 `https://yyapi.ushdev.top`。
模板也可保存以 `http://` 或 `https://` 开头的完整 URL，此时域名固定，不随环境切换。

URL、Headers 和 Body 均支持 `{{参数名}}` 占位符，例如：

```text
/v1/user/{{userid}}
```

发送前在右侧运行参数中填写 JSON 对象：

```json
{"userid": 123, "token": "example-token"}
```

界面会提示当前模板需要的参数；发送操作在后台线程中执行，底部响应日志显示状态码、
耗时和响应正文。超长响应会自动截断，避免日志区域持续膨胀。

API 响应按 `{code, data, msg}` 协议处理。字符串类型的 `data` 和 `msg` 会自动进行
Base64 解码；`data` 解码后若为 JSON，会继续解析成对象。独立请求日志显示解码后的响应，
自动化场景可直接断言 `response.code`、`response.data.xxx` 和 `response.msg`。

## 自动化场景

“自动化场景”页将已有 SQL 和 API 模板编排为有序步骤，支持以下步骤类型：

- SQL：修改或查询数据，最后一个查询结果可通过 `sql`（首行）和 `sql_rows`（全部行）读取。
- API：发送请求，响应写入 `response`，并提供 `http_status`、`elapsed_ms` 等字段。
- 提取变量：例如将 `response.data.order_id` 保存为 `order_id`，供后续 `{{order_id}}` 使用。
- 断言：支持等于、不等于、存在、不存在、包含、大于和小于。

步骤可标记为清理步骤，主流程失败或停止后仍会尝试执行。场景独立运行时可填写初始变量；
绑定到“账号生成”或“锦标赛造数”后，会自动提供 `userid`、`token`、`email`、`platform`
和 `channel_code`。场景保存在本机 `cache/feature_scenarios.json`，引用中的模板使用固定 ID，
被场景引用的 SQL/API 模板不能直接删除。

## 测试

```shell
python -m unittest discover -s test -v
```
