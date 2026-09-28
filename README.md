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

界面提供两个可切换的任务页：“创建账号”可选择按原逻辑批量注册随机邮箱账号，或使用
自定义邮箱定制创建一个指定账号；两种方式都会导出账号信息。创建账号时不再手动填写
Channel Code，而是选择是否进入 B 面及是否启用新手套路：不进入 B 面固定使用 `Organic`，
进入 B 面时根据日志库 `log_user_source` 的 `enter_pkg` 与 `cfg_channel_group` 自动匹配渠道源。
生产环境 `prod` 保留从已维护列表中手动选择 Channel Code，不读取日志库自动匹配。
“更新参数”会从 `ush_log_<环境>` 刷新渠道参数并缓存到本机
`cache/channel_sources.json`。“锦标赛数据”会注册
账号、加钱并完成固定或随机次数的下注。账号处理和下注都能分别选择串行或并行；串行
模式会固定使用一个执行线程，并禁用对应的并发数。界面会实时显示运行日志及完成进度，
注册平台可选择 Android 或 iOS。左侧导航可在创建账号、锦标赛数据、功能数据、API 请求
和参数配置之间切换；参数配置页维护的 Channel Code 作为两个账号任务页的渠道匹配优先级，页面也可
维护 SSH 数据库连接。两类配置都按运行环境
隔离，切换环境时会自动加载对应参数。数据库连接通过 SSH 隧道访问 MySQL，SSH 只允许
使用界面导入的私钥文件，不使用密码、SSH Agent 或自动密钥搜索，并可在界面中测试连接。
参数配置页的环境选择框旁会以红色或绿色呼吸状态显示数据库是否已配置，点击状态入口
可配置或编辑当前环境的连接参数。SSH 私钥在参数配置页的私钥库中单独导入和维护，各环境连接
只需选择已导入的私钥；仍被环境引用的私钥不能删除。
每个环境可分别设置业务库和日志库名称，更新渠道参数时会读取当前环境配置的日志库。
连接信息保存在本机 `cache/database_connections.json`（已排除版本控制），数据库密码不会
输出到运行日志。
点击“停止”后会在当前网络请求结束时安全停止。

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
默认单次下注金额为 `1000` 美分，可通过 `bet_amount` 参数调整。

## 功能数据 SQL

“功能数据”页可新增、编辑和删除命名 SQL 模板。模板需要用
`@userid=xxx;` 声明 User ID，执行时会自动转换为 MySQL `SET` 语句，后续语句可直接使用
`@userid`，例如：

```sql
@userid=xxx;
UPDATE user_other SET some_flag=1 WHERE user_id=@userid;
```

独立执行时，界面中填写的 User ID 会替换 `xxx`；在“创建账号”或
“锦标赛数据”页绑定 SQL 模板时，会自动使用新账号 UID。多条 DML 语句在同一数据库
事务中执行（DDL 遵循 MySQL 自动提交规则），模板保存在本机
`cache/sql_templates.json`（已排除版本控制）。
SQL 模板选择框支持按标题模糊检索；执行日志只输出模板名、UID 和成功状态。
“功能数据”页以标题列表管理模板，右侧为独立执行参数，底部仅保留紧凑日志栏。

## API 请求模板

“API 请求”页可按标题保存、检索、编辑和删除 HTTP 请求模板。模板支持
`GET`、`POST`、`PUT`、`PATCH` 和 `DELETE`，可配置完整 URL、JSON 格式的 Headers、
Body 与请求超时时间。模板保存在本机 `cache/api_templates.json`（已排除版本控制）。

URL、Headers 和 Body 均支持 `{{参数名}}` 占位符，例如：

```text
https://example.test/v1/user/{{userid}}
```

发送前在右侧运行参数中填写 JSON 对象：

```json
{"userid": 123, "token": "example-token"}
```

界面会提示当前模板需要的参数；发送操作在后台线程中执行，底部响应日志显示状态码、
耗时和响应正文。超长响应会自动截断，避免日志区域持续膨胀。

## 测试

```shell
python -m unittest discover -s test -v
```
