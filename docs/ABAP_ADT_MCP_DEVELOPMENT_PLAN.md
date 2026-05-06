# ABAP ADT MCP Server 開發規格與執行計畫

## 1. 開發目標

建立一個 `abap-adt-mcp-server`，讓支援 MCP 的 AI coding client，例如 Codex、Claude Code，可以透過 MCP tools 操作 SAP ABAP backend 的 ADT 功能。

第一版目標是完成一個可控、可測、可上線的 MVP，支援 ABAP Program / Report 的基本開發流程：

1. 連線 ABAP backend。
2. 搜尋 ABAP repository object。
3. 讀取 ABAP source。
4. 建立 ABAP report/program。
5. 修改 ABAP source。
6. 執行 syntax check。
7. 啟用 object。
8. 回傳 activation / syntax error 訊息。
9. 限制 AI 只能操作允許的 package 與 object name。
10. 完整記錄 audit log。

MVP 先支援 `PROG` object type。ABAP Class、Interface、CDS、RAP、ATC、ABAP Unit 放到後續版本。

## 2. 系統架構

```text
+-------------------+        MCP stdio / HTTP        +----------------------+
| Codex             | -----------------------------> | abap-adt-mcp-server |
| Claude Code       |                                |                      |
+-------------------+                                +----------+-----------+
                                                               |
                                                               | HTTPS / ADT
                                                               v
                                                    +----------------------+
                                                    | SAP ABAP Backend     |
                                                    | /sap/bc/adt          |
                                                    +----------------------+
```

MCP Server 不直接讓模型接觸 SAP 密碼。所有 SAP credentials、package allowlist、object allowlist、transport policy 都由 server 本機設定管理。

## 3. 技術選型

建議使用 TypeScript / Node.js。

選型理由：

- MCP TypeScript SDK 是官方 Tier 1 SDK。
- Claude Code / Codex 掛本機 MCP server 時，`stdio` transport 最容易部署。
- MCP SDK 原生支援 tools、resources、prompts、JSON Schema、stdio、Streamable HTTP。

建議套件：

```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "latest",
    "zod": "latest",
    "undici": "latest",
    "dotenv": "latest",
    "pino": "latest",
    "fast-xml-parser": "latest"
  },
  "devDependencies": {
    "typescript": "latest",
    "tsx": "latest",
    "vitest": "latest",
    "@types/node": "latest"
  }
}
```

## 4. 專案結構

```text
abap-adt-mcp-server/
  package.json
  tsconfig.json
  README.md
  .env.example

  src/
    index.ts
    server/
      mcpServer.ts
      toolRegistry.ts
      resourceRegistry.ts
      promptRegistry.ts

    config/
      config.ts
      schema.ts

    adt/
      AdtClient.ts
      AdtSession.ts
      AdtErrors.ts
      csrf.ts
      cookies.ts
      xml.ts
      endpoints.ts

    abap/
      objectTypes.ts
      objectUri.ts
      sourceNormalizer.ts
      validation.ts
      diff.ts

    tools/
      pingSystem.ts
      searchObjects.ts
      getObjectSource.ts
      createProgram.ts
      updateProgramSource.ts
      syntaxCheck.ts
      activateObject.ts
      getObjectMetadata.ts
      getChangePreview.ts

    security/
      policy.ts
      authorizer.ts
      auditLog.ts
      secretRedaction.ts

    transport/
      stdio.ts
      http.ts

    errors/
      mcpError.ts
      errorMapping.ts

  test/
    unit/
    integration/
    fixtures/
```

## 5. 設定檔規格

`.env` 只放敏感資訊。

```env
SAP_BASE_URL=https://sap.example.com:443
SAP_CLIENT=100
SAP_USERNAME=DEVELOPER01
SAP_PASSWORD=xxxx
SAP_LANGUAGE=EN
SAP_VERIFY_TLS=true

MCP_TRANSPORT=stdio
LOG_LEVEL=info
AUDIT_LOG_PATH=./logs/audit.jsonl
```

非敏感 policy 建議放 `config.json`。

```json
{
  "server": {
    "name": "abap-adt-mcp-server",
    "version": "0.1.0"
  },
  "sap": {
    "systemId": "DEV",
    "defaultPackage": "ZAI_MCP_SANDBOX",
    "defaultTransport": null
  },
  "policy": {
    "readOnly": false,
    "allowedPackages": ["ZAI_MCP_SANDBOX", "$TMP"],
    "allowedObjectPrefixes": ["ZAI_", "ZMCP_", "YAI_"],
    "allowedObjectTypes": ["PROG"],
    "requirePreviewBeforeWrite": true,
    "allowDelete": false,
    "allowActivation": true,
    "maxSourceBytes": 500000
  }
}
```

## 6. ADT Client 規格

`AdtClient` 負責所有 SAP ADT HTTP 細節。MCP tools 不應直接組 ADT URL。

核心介面：

```ts
interface AdtClient {
  ping(): Promise<SystemInfo>;

  searchObjects(input: SearchObjectsInput): Promise<RepositoryObject[]>;

  getObjectSource(input: ObjectRef): Promise<SourceDocument>;

  createProgram(input: CreateProgramInput): Promise<CreateObjectResult>;

  updateSource(input: UpdateSourceInput): Promise<UpdateSourceResult>;

  syntaxCheck(input: SyntaxCheckInput): Promise<SyntaxCheckResult>;

  activateObject(input: ActivateObjectInput): Promise<ActivationResult>;

  getMetadata(input: ObjectRef): Promise<ObjectMetadata>;

  lockObject(input: ObjectRef): Promise<LockHandle>;

  unlockObject(input: ObjectRef, lock: LockHandle): Promise<void>;
}
```

重要實作要求：

1. 所有 request 都走同一個 HTTP wrapper。
2. 自動管理 cookie。
3. 自動取得與刷新 CSRF token。
4. 支援 Basic Auth；後續可擴充 SSO / OAuth。
5. 支援 stateful session，因為 lock / update / activation 流程可能需要同一 session。
6. 所有 ADT XML response 都 parse 成 typed object。
7. 所有 SAP error response 都轉成一致的 MCP error。

## 7. ADT Endpoint Discovery 工作

這一段必須實做，不能靠猜。ADT REST endpoint 有版本差異，SAP 官方文件主要描述 ADT 架構與後端設定，實際 endpoint 細節通常要用 ADT Communication Log 或測試系統驗證。

要產出一份 `docs/adt-endpoints.md`，內容至少包含：

```text
Operation: discovery
Method:
URL:
Headers:
Request body:
Response body:
Verified SAP release:
Verified ADT client version:
Notes:

Operation: read program source
Method:
URL:
Headers:
Request body:
Response body:
Verified SAP release:
Verified ADT client version:
Notes:

Operation: lock object
...

Operation: update source
...

Operation: syntax check
...

Operation: activate object
...
```

第一版最少驗證以下 ADT 操作：

1. `GET /sap/bc/adt/discovery`
2. Repository search。
3. Program source read。
4. Program object create。
5. Program lock。
6. Program source update。
7. Program syntax check。
8. Program activation。
9. Program unlock。

驗收條件：

- 在 SAP DEV sandbox 可手動呼叫每個 endpoint。
- 每個 endpoint 都有 fixture。
- 每個 response parser 都有單元測試。

## 8. MCP Tools 規格

### 8.1 `abap_ping_system`

用途：確認 MCP server 可以登入 SAP 並存取 ADT。

Input：

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

Output：

```json
{
  "ok": true,
  "systemId": "DEV",
  "client": "100",
  "user": "DEVELOPER01",
  "adtReachable": true
}
```

失敗時要回傳：

```json
{
  "ok": false,
  "errorCode": "AUTH_FAILED | ADT_UNAVAILABLE | TLS_ERROR | NETWORK_ERROR",
  "message": "..."
}
```

### 8.2 `abap_search_objects`

用途：搜尋 ABAP object。

Input：

```json
{
  "type": "object",
  "required": ["query"],
  "properties": {
    "query": { "type": "string" },
    "objectType": {
      "type": "string",
      "enum": ["PROG", "CLAS", "INTF", "DDLS"]
    },
    "packageName": { "type": "string" },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 50,
      "default": 20
    }
  },
  "additionalProperties": false
}
```

Output：

```json
{
  "objects": [
    {
      "name": "ZMCP_HELLO",
      "type": "PROG",
      "packageName": "ZAI_MCP_SANDBOX",
      "description": "Hello from MCP",
      "uri": "abap://DEV/100/PROG/ZMCP_HELLO"
    }
  ]
}
```

Policy：

- `limit` 預設 20，最大 50。
- 不允許全系統大範圍 dump。
- 若 query 太短，例如少於 3 字元，拒絕。

### 8.3 `abap_get_object_source`

用途：讀取 source。

Input：

```json
{
  "type": "object",
  "required": ["objectType", "objectName"],
  "properties": {
    "objectType": {
      "type": "string",
      "enum": ["PROG"]
    },
    "objectName": { "type": "string" }
  },
  "additionalProperties": false
}
```

Output：

```json
{
  "object": {
    "name": "ZMCP_HELLO",
    "type": "PROG",
    "packageName": "ZAI_MCP_SANDBOX"
  },
  "source": "REPORT zmcp_hello.\nWRITE: / 'Hello'.",
  "etag": "..."
}
```

Policy：

- 只允許讀取 allowlist 範圍內 object，除非設定 `readPolicy: unrestricted`。
- source 超過 `maxSourceBytes` 時，回傳錯誤或 resource link，不直接塞滿 MCP result。

### 8.4 `abap_get_change_preview`

用途：讓模型先看 diff，不直接寫入。

Input：

```json
{
  "type": "object",
  "required": ["objectType", "objectName", "newSource"],
  "properties": {
    "objectType": { "type": "string", "enum": ["PROG"] },
    "objectName": { "type": "string" },
    "newSource": { "type": "string" }
  },
  "additionalProperties": false
}
```

Output：

```json
{
  "objectName": "ZMCP_HELLO",
  "diff": "--- old\n+++ new\n...",
  "allowed": true,
  "policyWarnings": []
}
```

Policy：

- 寫入前建議強制先跑這個 tool。
- 若 `requirePreviewBeforeWrite=true`，server 要記錄 preview hash，後續 update 必須帶同一 hash。

### 8.5 `abap_create_program`

用途：建立 ABAP report/program。

Input：

```json
{
  "type": "object",
  "required": ["programName", "packageName", "description", "source"],
  "properties": {
    "programName": { "type": "string" },
    "packageName": { "type": "string" },
    "description": { "type": "string" },
    "source": { "type": "string" },
    "transportRequest": { "type": ["string", "null"] },
    "activate": { "type": "boolean", "default": false }
  },
  "additionalProperties": false
}
```

Validation：

- `programName` 必須符合 `^[ZY][A-Z0-9_]{2,30}$`。
- `packageName` 必須在 allowlist。
- `$TMP` 時 `transportRequest` 必須是 null。
- 非 `$TMP` 時，依 policy 決定 transport 是否必填。
- source 第一行建議包含 `REPORT <name>.`，不自動偷偷改，可回 warning。

Output：

```json
{
  "created": true,
  "object": {
    "type": "PROG",
    "name": "ZMCP_HELLO",
    "packageName": "ZAI_MCP_SANDBOX"
  },
  "activated": false,
  "messages": []
}
```

### 8.6 `abap_update_program_source`

用途：修改既有 program source。

Input：

```json
{
  "type": "object",
  "required": ["programName", "source"],
  "properties": {
    "programName": { "type": "string" },
    "source": { "type": "string" },
    "previewHash": { "type": "string" },
    "transportRequest": { "type": ["string", "null"] },
    "syntaxCheck": { "type": "boolean", "default": true },
    "activate": { "type": "boolean", "default": false }
  },
  "additionalProperties": false
}
```

流程：

1. 驗證 object name。
2. 讀取 metadata。
3. 檢查 package allowlist。
4. 若 policy 要求 preview，驗證 `previewHash`。
5. lock object。
6. update source。
7. syntax check。
8. 若 `activate=true` 且 syntax pass，activate。
9. unlock object。
10. 寫 audit log。

Output：

```json
{
  "updated": true,
  "syntaxCheck": {
    "passed": true,
    "messages": []
  },
  "activation": {
    "requested": true,
    "activated": true,
    "messages": []
  },
  "auditId": "20260506-DEV-000001"
}
```

錯誤時：

- 一定要嘗試 unlock。
- 回傳 lock/update/syntax/activation 哪一步失敗。
- source 不要回傳完整密碼或敏感內容。

### 8.7 `abap_syntax_check`

用途：檢查 source 或 repository object。

Input：

```json
{
  "type": "object",
  "required": ["programName"],
  "properties": {
    "programName": { "type": "string" },
    "source": { "type": "string" }
  },
  "additionalProperties": false
}
```

行為：

- 若有 `source`，檢查傳入 source。
- 若沒有 `source`，檢查 repository 中的目前版本。

Output：

```json
{
  "passed": false,
  "messages": [
    {
      "severity": "error",
      "line": 3,
      "column": 10,
      "message": "Field XYZ is unknown.",
      "code": "..."
    }
  ]
}
```

### 8.8 `abap_activate_object`

用途：啟用 object。

Input：

```json
{
  "type": "object",
  "required": ["objectType", "objectName"],
  "properties": {
    "objectType": { "type": "string", "enum": ["PROG"] },
    "objectName": { "type": "string" }
  },
  "additionalProperties": false
}
```

Output：

```json
{
  "activated": true,
  "messages": []
}
```

Policy：

- 若 `allowActivation=false`，拒絕。
- 僅允許 allowlist package。
- 啟用前建議自動跑 syntax check。

## 9. MCP Resources 規格

除了 tools，MCP server 也要暴露 read-only resources，讓 Claude Code / Codex 可以用 resource reference 取得上下文。

Resource URI 設計：

```text
abap://{systemId}/{client}/objects/{objectType}/{objectName}/source
abap://{systemId}/{client}/objects/{objectType}/{objectName}/metadata
abap://{systemId}/{client}/packages/{packageName}/objects
```

例：

```text
abap://DEV/100/objects/PROG/ZMCP_HELLO/source
```

第一版 resources：

1. `abap_object_source`
2. `abap_object_metadata`
3. `abap_package_objects`

Resource 規則：

- resources 只能讀，不做 side effect。
- 大型 source 可分頁或限制大小。
- resource read 也要經過 policy。

## 10. MCP Prompts 規格

提供 prompt templates，讓 AI client 產生一致流程。

### 10.1 `abap_fix_syntax_error`

Input：

```json
{
  "objectType": "PROG",
  "objectName": "ZMCP_HELLO"
}
```

Prompt 行為：

1. 讀取 source。
2. 跑 syntax check。
3. 根據錯誤產生 patch。
4. 先 preview。
5. 等使用者同意後 update。

### 10.2 `abap_create_report`

Input：

```json
{
  "programName": "ZMCP_HELLO",
  "packageName": "ZAI_MCP_SANDBOX",
  "description": "Hello report"
}
```

Prompt 行為：

1. 產生 ABAP report source。
2. 建立 program。
3. syntax check。
4. activate。

## 11. 安全規格

這個專案最重要的是安全邊界。

必做：

1. SAP 密碼不得出現在 MCP tool input/output。
2. 所有 write tools 都要檢查 package allowlist。
3. 所有 write tools 都要檢查 object name prefix。
4. 禁止 delete object。
5. 預設禁止改 SAP standard object。
6. 預設禁止操作非 Z/Y object。
7. audit log 必須記錄每次寫入與啟用。
8. source diff 必須記錄，但要有 secret redaction。
9. 可設定 read-only mode。
10. 所有 dangerous tool description 要清楚標示會修改 SAP repository。

Audit log 格式：

```json
{
  "auditId": "20260506-DEV-000001",
  "timestamp": "2026-05-06T10:00:00+08:00",
  "sapSystem": "DEV",
  "client": "100",
  "sapUser": "DEVELOPER01",
  "tool": "abap_update_program_source",
  "objectType": "PROG",
  "objectName": "ZMCP_HELLO",
  "packageName": "ZAI_MCP_SANDBOX",
  "transportRequest": null,
  "diffSha256": "...",
  "result": "success"
}
```

## 12. 錯誤碼規格

所有 tools 失敗時都要回傳一致錯誤碼。

```ts
type ErrorCode =
  | "CONFIG_INVALID"
  | "AUTH_FAILED"
  | "ADT_UNAVAILABLE"
  | "CSRF_FAILED"
  | "TLS_ERROR"
  | "NETWORK_ERROR"
  | "OBJECT_NOT_FOUND"
  | "OBJECT_LOCKED"
  | "OBJECT_ALREADY_EXISTS"
  | "PACKAGE_NOT_ALLOWED"
  | "OBJECT_NAME_NOT_ALLOWED"
  | "OBJECT_TYPE_NOT_SUPPORTED"
  | "TRANSPORT_REQUIRED"
  | "SYNTAX_ERROR"
  | "ACTIVATION_FAILED"
  | "ADT_RESPONSE_PARSE_FAILED"
  | "POLICY_DENIED";
```

錯誤 response：

```json
{
  "ok": false,
  "errorCode": "OBJECT_LOCKED",
  "message": "Object ZMCP_HELLO is locked by another user.",
  "details": {
    "objectName": "ZMCP_HELLO",
    "lockOwner": "USER02"
  }
}
```

## 13. 開發任務拆解

### Phase 0：準備

交付物：

- 建立 repo。
- 建立 TypeScript 專案。
- 建立 `.env.example`。
- 建立 `config.json` schema。
- 建立 CI：lint、typecheck、unit test。

驗收：

```bash
npm install
npm run typecheck
npm test
```

全部成功。

### Phase 1：ADT 連線 PoC

交付物：

- `AdtSession`
- `AdtClient.ping`
- cookie jar
- CSRF token handling
- TLS config
- SAP auth config

驗收：

```bash
npm run adt:ping
```

可登入 SAP DEV，並確認 `/sap/bc/adt` 可存取。

### Phase 2：Endpoint Catalog

交付物：

- `docs/adt-endpoints.md`
- `src/adt/endpoints.ts`
- fixtures：
  - discovery response
  - search response
  - read source response
  - syntax response
  - activation response
  - error response

驗收：

- 所有 MVP endpoint 均已在實際 DEV 系統驗證。
- parser 單元測試覆蓋成功與失敗 response。

### Phase 3：Read-only MCP

交付物：

- MCP stdio server。
- tools：
  - `abap_ping_system`
  - `abap_search_objects`
  - `abap_get_object_source`
  - `abap_get_object_metadata`
- resources：
  - object source
  - object metadata
  - package object list

驗收：

- Claude Code 可掛載 MCP server。
- Codex 可掛載 MCP server。
- AI client 可以搜尋並讀取 `ZMCP_*` program source。

### Phase 4：Write Flow

交付物：

- `abap_get_change_preview`
- `abap_create_program`
- `abap_update_program_source`
- object lock/unlock
- audit log
- policy enforcement

驗收：

- 可以建立 `ZMCP_HELLO`。
- 可以修改 `ZMCP_HELLO`。
- 不允許建立 `SAPM*`。
- 不允許修改非 allowlist package。
- 每次寫入都有 audit log。

### Phase 5：Syntax / Activation

交付物：

- `abap_syntax_check`
- `abap_activate_object`
- activation result parser
- syntax message mapper

驗收：

- 語法正確 program 可啟用。
- 語法錯誤 program 會回傳 line/column/message。
- activation 失敗時回傳完整可讀訊息。
- update + syntax + activate 可一條流程完成。

### Phase 6：Client Integration 文件

交付物：

- `docs/claude-code.md`
- `docs/codex.md`
- `README.md`

Claude Code 範例設定：

```json
{
  "mcpServers": {
    "abap-adt": {
      "command": "node",
      "args": ["dist/index.js"],
      "env": {
        "SAP_BASE_URL": "https://sap.example.com",
        "SAP_CLIENT": "100"
      }
    }
  }
}
```

文件必須包含：

- 安裝方式。
- 設定方式。
- SAP 權限需求。
- 安全限制。
- sandbox 測試流程。
- 常見錯誤排查。

## 14. 測試矩陣

| 類別 | 測試 |
| --- | --- |
| Auth | 密碼錯誤 |
| Auth | ADT service 未啟用 |
| TLS | certificate invalid |
| Search | query 太短被拒絕 |
| Read | object 不存在 |
| Read | source 過大 |
| Create | 建立 `$TMP` program |
| Create | 建立 package program 但缺 transport |
| Create | object 已存在 |
| Policy | package 不在 allowlist |
| Policy | object name 非 Z/Y |
| Update | object 被別人 lock |
| Update | preview hash 缺失 |
| Syntax | 語法錯誤 |
| Activation | 啟用成功 |
| Activation | 啟用失敗 |
| Audit | 寫入後有 audit log |
| Recovery | update 失敗後 unlock |

## 15. MVP 完成定義

MVP 完成時，使用者可以在 Codex / Claude Code 下這類指令：

```text
請透過 ABAP MCP 在 ZAI_MCP_SANDBOX 建立一支 ZMCP_HELLO report，
內容輸出 Hello MCP，做 syntax check，成功後 activate。
```

系統應完成：

1. 呼叫 `abap_create_program`。
2. 呼叫 `abap_syntax_check`。
3. 呼叫 `abap_activate_object`。
4. 回報成功或具體錯誤。
5. 寫入 audit log。

## 16. 後續擴充路線

MVP 後再做：

1. ABAP Class / Interface。
2. CDS source。
3. Transport request 查詢與選擇。
4. ATC check。
5. ABAP Unit。
6. Where-used list。
7. Package dependency graph。
8. RAP object scaffolding。
9. OAuth / SSO。
10. Remote Streamable HTTP MCP server。

## 17. 主要設計決策

- MCP tools 負責 AI 可理解的動作。
- ADT adapter 負責 SAP endpoint 細節。
- Policy layer 負責阻擋危險操作。
- Audit layer 負責追蹤所有修改。
- 第一版只支援 `PROG`，不要一開始就吃下全部 ABAP object type。

這樣做的好處是第一版可控、可測、可上線。等 Program workflow 穩定後，Class、CDS、ATC 都是擴充 adapter 與 tool schema，而不是重寫整個 MCP server。

## 18. 參考資料

- [Model Context Protocol SDKs](https://modelcontextprotocol.io/docs/sdk)
- [MCP TypeScript SDK](https://ts.sdk.modelcontextprotocol.io/)
- [MCP TypeScript SDK Server Docs](https://ts.sdk.modelcontextprotocol.io/documents/server.html)
- [MCP Specification](https://modelcontextprotocol.io/specification/2024-11-05/index)
- [MCP Tools Specification](https://modelcontextprotocol.io/specification/draft/server/tools)
- [Claude Code MCP Docs](https://code.claude.com/docs/en/mcp)
- [SAP ADT Backend Configuration](https://help.sap.com/doc/2e65ad9a26c84878b1413009f8ac07c3/7.51/en-US/config_guide_system_backend_abap_development_tools.pdf)
