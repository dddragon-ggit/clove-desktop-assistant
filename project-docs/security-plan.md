# 安全方案重构：共享令牌 + 去掉 device_id 过滤

## Context

当前问题：Edge Function 按 device_id 过滤数据，导致手机端只能看到自己创建的待办，无法与桌面端同步。需要找到既安全又不影响同步的方案。

## 当前架构分析

```
桌面端 → 直接连 Supabase（service_role key，读写所有数据）
PWA    → Edge Function → Supabase（service_role key，按 device_id 过滤）
```

问题：桌面端读所有数据，PWA 只读自己的数据，不同步。

## 推荐方案：共享令牌认证

核心思路：用一个共享密钥（token）代替 device_id 做身份验证。知道 token 的人（你）能访问所有数据，不知道的人（陌生人）什么都拿不到。

### 架构变更后：

```
桌面端 → Supabase 直连（service_role key + RLS allow_all）
PWA    → Edge Function（验证 token）→ Supabase（读写所有数据）
```

- 所有合法用户看到相同的数据，同步正常
- 陌生人没有 token，Edge Function 拒绝请求
- 数据库凭证不暴露在前端代码中

### 具体改动

**1. Edge Function（`supabase/functions/todos-api/index.ts`）**
- 去掉所有 device_id 过滤
- 读取 Supabase 环境变量 `API_TOKEN` 作为共享密钥
- 验证请求头 `X-API-Token` 是否匹配，不匹配返回 401
- 四个操作（select/insert/update/delete）改为无过滤

**2. Supabase 环境变量**
- 在 Supabase Dashboard 设置 `API_TOKEN` 环境变量
- 值为一个随机生成的强密码

**3. PWA 前端（`docs/app.js` + `mobile/app.js`）**
- 首次访问时弹出令牌输入界面
- 令牌保存到 localStorage，后续自动使用
- 所有 API 请求带 `X-API-Token` 头
- Realtime 保持不变（用 anon key 订阅）

**4. RLS 策略**
- 改为 allow_all（因为安全由 Edge Function 的 token 保证）
- 或者直接禁用 RLS（桌面端用 service_role 绕过 RLS，PWA 通过 Edge Function 也绕过）

**5. 桌面端**
- 保持不变，继续直连 Supabase

## 验证步骤

1. 手机输入正确 token → 能看到所有待办（包括桌面端创建的）
2. 手机输入错误 token → 请求被拒绝
3. 手机添加待办 → 桌面端同步显示
4. 桌面端添加待办 → 手机端实时/刷新后显示
5. 运行 `python -m unittest tests.test_pwa_structure -v` 确认测试通过
