# IDP 适配指南

本参考文档介绍如何将登录脚本适配到不同高校的 IDP 系统。

## 支持的 IDP 模式

脚本针对中国高等教育中常见的特定 CAS/IDP 流程：

```
浏览器 → CAS 入口 → IDP 门户（Vue SPA）→ API 调用（lck、authChainCode、publicKey）
  → RSA 加密认证 → loginToken（JWT）→ authnEngine 重定向 → SP 回调 → 会话建立
```

关键特征：
- IDP 使用基于哈希路由的 Vue.js SPA（路径 `/ac/`）
- 通过 REST API 查询认证方式（`/idp/authn/queryAuthMethods`）
- 密码在客户端使用服务器提供的 RSA 公钥加密（`/idp/authn/getJsPublicKey`）
- 登录 Token 提交至 authnEngine，由其执行浏览器重定向至 SP
- SP 消费 CAS Ticket 并建立会话 Cookie

## 逐步适配流程

### 第一步：确认 IDP URL 模式

访问 Canvas 实例的登录 URL，常见模式如下：

| 高校 | 入口 URL | IDP 基础地址 | 备注 |
|---|---|---|---|
| 复旦大学 | `https://elearning.fudan.edu.cn/login/cas` | `https://id.fudan.edu.cn` | 默认配置 |
| 其他 Canvas+CAS | `https://canvas.example.edu/login/cas` | 各不相同 | 需追踪重定向链 |

使用 `curl -vL <入口URL>` 追踪重定向链，找到 IDP 基础地址。

### 第二步：测试基本连通性

```bash
ELEARNING_ENTRY_URL=https://your-canvas.example.edu/login/cas \
ELEARNING_IDP_BASE_URL=https://your-idp.example.edu \
ELEARNING_ENTITY_ID=https://your-canvas.example.edu \
python elearning_login.py --dry-run --debug
```

检查 `debug_output/`：
- `entry_response.html` —— 应包含 `lck` 值（格式：`context_CAS_...`）
- `query_auth_methods.json` —— 应列出 `userAndPwd` 认证模块

### 第三步：处理差异

**认证模块名称不同**：如果 IDP 使用的名称不是 `userAndPwd`：
```python
# 在 auth_session.py → pick_auth_chain_code() 中修改
if module_code == "your_auth_module_name" and chain_code:
    return chain_code
```

**公钥格式不同**：脚本已支持 PEM、Base64-DER 和 modulus+exponent（十六进制）格式。如 IDP 使用其他格式，请扩展 `parse_public_key_payload()`。

**登录 Token 位置不同**：如 JWT 位于不同的 JSON 路径，请扩展 `extract_login_token()`。

**重定向机制不同**：如 `authnEngine` 使用不同的重定向模式，请更新 `parse_authn_engine_handoff()`。

### 第四步：设置 Token Purpose 约定

在 `.env` 中设置有意义的 Token purpose：
```
ELEARNING_TOKEN_PURPOSE="My Agent Auto Refresh"
```

这样可以安全地清理旧 Token —— 相同 purpose 的旧 Token 会被删除，而手动创建的 Token 则得以保留。

### 第五步：端到端验证

```bash
python elearning_login.py --cleanup-old-tokens --debug
```

预期结果：标准输出打印 `NEW_TOKEN=<值>`，所有调试产物保存至 `debug_output/`。

## 常见 IDP 变体

### SAML 2.0（非 CAS）

如果所在高校使用 SAML 2.0 而非 CAS，流程将完全不同（涉及 SAMLRequest/SAMLResponse XML 交换）。本脚本**不直接支持** SAML 2.0。

### OAuth 2.0 / OIDC

如果登录基于 OAuth（重定向至授权端点），可以直接使用 OAuth 流程代替浏览器自动化 —— 更简单、更可靠。

### 自定义验证码

部分 IDP 在登录表单中嵌入了验证码。基于 `requests` 的方式无法处理此类情况，需要：
1. 改用浏览器自动化工具（Playwright/Selenium）
2. 或通过手动登录获取长期有效的会话 Token
