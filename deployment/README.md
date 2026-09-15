# 上线适配状态 · 2026-09-15

这是部署准备，不代表已经部署或具备正式开放条件。

**最新范围变更**：用户选择先做不接 TOS 的临时演示，保留知乎登录与临时体验码，详见 [DEMO.md](DEMO.md)。下文持久化阻塞项仍用于正式版本，不把临时演示误报为正式上线。

## 本轮完成

- 后端总额度默认 8 次，`DREAMCARD_IMAGE_QUOTA_TOTAL` 可配置；已有消耗不清零，不改账号与历史归属
- 第 9 次新生图任务返回 `image_quota_exhausted` / `额度不足`，不提交模型；同任务重试不重复扣额，删除不返还次数
- 环境只接受 `development / test / production`，防止误填 `prod` 导致 Secure Cookie 未开启
- 正式环境不公开 API 文档；请求返回 `X-Request-ID`，记录状态、耗时和路由模板，不记录请求正文、查询串、Cookie 或异常原文
- SQLite 一致性快照、完整性检查、恢复到新路径；备份权限 0600，不覆盖现有文件
- 恢复保留历史、图片和已用额度，但撤销备份中的登录会话，要求重新登录
- 新增部署前只读检查与上传排除规则；还需实际检查最终上传包，不能仅靠忽略文件宣称密钥已安全

## 本地验证

在项目根目录执行：

```sh
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
PYTHONPATH=backend .venv/bin/python backend/scripts/check_release.py
```

检查脚本不加载本地 `.env`，只读取当前进程的环境配置；只输出项目名称和通过状态，不输出密钥值。不满足上线条件会退出 1，这是预期拦截，不是脚本故障。

### 备份 / 恢复

显式提供真实的绝对路径；以下是占位示例，不应原样执行：

```sh
PYTHONPATH=backend .venv/bin/python backend/scripts/database_snapshot.py backup --source /absolute/private/dreamcard.db --destination /absolute/private/backups/snapshot.db
PYTHONPATH=backend .venv/bin/python backend/scripts/database_snapshot.py restore --source /absolute/private/backups/snapshot.db --destination /absolute/private/restored/dreamcard.db
```

备份包含用户隐私，不可放进 public、静态资源目录、代码包或公开存储桶。在线备份使用 SQLite backup API，不直接复制正在写入的数据库文件。恢复必须选择不存在的新路径；验证后停服切换数据库路径，不能对运行中的数据库原地覆盖。

**本地快照不是异地备份。当前未接入定时云备份、启动自动恢复或对象存储。** 极端故障的恢复点取决于最近一次成功备份，不能承诺零丢失。恢复旧快照可能使备份后的记录、删除操作、额度变动回退，需要上线前明确可接受恢复点和删除保留规则。

## 实际运行结构

- 前端是 React/Vite，`pnpm build` 生成 `dist`，不是 Next.js
- FastAPI 入口 `app.main:app`，从根目录运行需设置 `PYTHONPATH=backend`
- 知乎 Node 适配器在 `integrations/zhihu-login/server.mjs`，仅监听回环地址；FastAPI 固定访问 `127.0.0.1:4173`
- 最终部署必须保证两服务同机 / 同网络命名空间，或者先设计经过认证的私有服务连接；不能把两个独立函数按现状直接拆开
- Node 当前读取 `PORT` 作为端口，部署编排时必须明确设置为 4173，不能继承公共服务端口
- 对外仅提供前端静态资源、`/api/v1/*` 与 `/auth/callback`，不能将 Node 示例 `/api/oauth/*` 或私有 `/api/login/*` 暴露公网
- 公网代理也必须禁用授权回调查询串、Cookie 和响应 Cookie 日志；应用自身的脱敏日志不能代替代理配置
- 正式环境变量名称见 `production.env.example`；不得直接套用通用手册的 `ENV=prod` 或 `DATABASE_URL`

## 仍阻塞正式开放

1. **持久化方案未接入**：当前 SQLite 及图片 BLOB 均在本地。先确认云资源、预算与运行模式，再接数据持久化、图片对象存储和异地恢复。不要仅把 SQLite 放到临时目录并增加常驻实例；多实例和滚动发布也必须处理一致性
2. **知乎真实登录未通过**：回调地址、`identityPath` 尚空；不能猜字段或取消 state 校验来绕过。需要平台注册回调和用户亲自完成真实授权
3. **云端完整流程未验收**：登录、账号隔离、8 次额度、生成、下载、重启与跨设备历史必须在测试域名验证
4. **运维未完成**：进程管理、HTTPS/代理、告警通知、回滚、实际发布包审计尚待部署阶段完成
5. **外部配置待确认**：内容安全配置及知识库生产准入仍需按既有项目要求核对；不能把 mock 或关闭审核视为正式验收通过

暂未修改模型提示词、生图风格、页面布局或执行任何云端发布。不要因自动测试全通过而跳过上述门槛。
