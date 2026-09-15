# 知乎 OAuth 适配服务

本目录为 LUCIDREAM 的私有登录适配服务，使用 Node.js 22+，无需额外 npm 依赖。主产品经 FastAPI 调用此服务，不直接向浏览器开放内部接口。

## 配置

`hackathon.config.json` 中只保存非秘密的应用编号、回调地址、稳定身份字段和本地凭据引用，当前配置对应项目演示环境。部署自己的副本时，必须替换为自己的应用信息，不能沿用本项目回调地址。

1. 配置自己的 `oauth.appId` 与 HTTPS `oauth.redirectUri`，路径使用 `/auth/callback`
2. 在知乎后台登记完全一致的回调地址，登记完成后才设置 `callbackRegistered: true`
3. 服务器通过 Secret 环境变量注入 `ZHIHU_OAUTH_APP_KEY`，或使用配置对应的 macOS 钥匙串条目
4. 当前用户接口使用稳定字段 `uid`，不要用昵称替代身份，也不要移除 state 校验

主产品 OAuth 登录只需要 OAuth app_key，不需要开发者 Access Secret。`lib/oauth.mjs` 与 `public/` 中还保留初始化阶段的独立接口演示，可能需要 `ZHIHU_ACCESS_SECRET`；它们不是主产品登录或分享的必需条件。

## 启动和验证

在本目录执行：

```bash
npm test
npm run check
PORT=4173 npm start
```

服务只监听 `127.0.0.1:4173`。FastAPI 需要与其处于同一主机或网络命名空间。公网只开放主产品的 `/api/v1/*` 与 `/auth/callback`，不要开放这里的 `/api/login/*`、`/api/oauth/*` 或示例页面。

本地使用体验码即可验证主流程，不必启动本服务。真实 OAuth 验证需在登记的公网域名进行，并由用户亲自完成授权；测试程序只验证模拟的协议与安全边界。

## 安全与当前能力

- app_key、授权码交换和用户令牌仅在服务器使用，不写入前端或源码
- 后端使用经验证的用户身份建立账号，仅向前端提供必要昵称、头像等展示信息
- OAuth 临时流程与令牌在进程内存中，重启不保留；禁止记录回调查询串及令牌
- 分享仍为用户下载、复制后自行在知乎发布；OAuth 登录成功不等于拥有个人内容发布权限
- 本地官方 CLI Skill 和凭据缓存不随仓库分发，也不是启动主产品的运行依赖

历史审计见 [2026-09-15-OAUTH-REVIEW.md](2026-09-15-OAUTH-REVIEW.md)，其中阶段待办应结合最新记录阅读。
