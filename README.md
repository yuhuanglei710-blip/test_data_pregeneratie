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
domain="前台接口域名"
background_domain="后台接口域名"
```

## 使用

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

注册和下注默认使用精简日志；需要查看接口状态与完整响应时，可在代码调用中传入
`verbose=True`。失败响应即使在精简模式下也会保留状态码和截断后的响应内容。
同一进程内会复用尚未到期的游戏 token，仅根据 JWT 的 `exp` 字段判断有效期；
token 缺失或过期时才会重新请求。
批量下注默认使用 3 个工作线程；可通过 `spin_concurrency` 参数调整，但不建议在未确认
服务端限流和钱包并发策略前继续提高。

## 测试

```shell
python -m unittest discover -s test -v
```
