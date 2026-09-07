# role-crew

多角色：**先执行、用同一份 JSON 信封交接、自己验证过再往下传**。

## 三个角色

| 角色 | 能做什么 |
|---|---|
| `dispatcher` | `list_roles` 弄清职责，再 `call_role` 交给别人 |
| `fixer` | 只在 `workspace/` 写 `.txt`，写完必须再读 |
| `verifier` | 再读一遍，内容对才 `verified` |

## 不调模型

```powershell
cd C:\Users\wenjin\Desktop\wwjfiles\role-crew
.\.venv\Scripts\role-crew.exe demo
.\.venv\Scripts\python.exe -m pytest
```

## 接 API（Token Plan / 百炼兼容）

`.env` 已按 Token Plan 预留：`sk-sp-` + `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` + `glm-5-2`。

```powershell
copy .env.example .env
# 填 LLM_API_KEY
.\.venv\Scripts\role-crew.exe run --task "在 workspace 创建 hello.txt，内容为 OK，确认后再结束。"
```

`run` 会让模型选白名单工具，把 stdout 回执再喂回去，直到 `verified` 或步数用尽。全程写入 `traces/`。
