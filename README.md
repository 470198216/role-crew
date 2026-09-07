# role-crew

多角色：**先执行、用同一份 JSON 信封交接、自己验证过再往下传**。

第一版只有信封 + 白名单执行器 + 三个演示角色。**不调模型**。`role-crew run` 是下一版入口。

## 三个角色

| 角色 | 能做什么 |
|---|---|
| `dispatcher` | `list_roles`：弄清谁负责什么，再交给 fixer |
| `fixer` | 只在 `workspace/` 写 `.txt`，写完必须再读 |
| `verifier` | 再读一遍，内容对才 `verified` |

工具定义在 `configs/tools.yaml`，角色能用哪些写在 `roles/*.yaml`。模型以后也不能发明新命令。

## 第一次跑

```powershell
cd C:\Users\wenjin\Desktop\wwjfiles\role-crew
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\role-crew.exe demo
.\.venv\Scripts\python.exe -m pytest
```

成功时 `workspace/hello.txt` 内容为 `OK`，stdout 里三步信封都是 `status: verified`。

单工具（不走演示管线）：

```powershell
.\.venv\Scripts\role-crew.exe roles
.\.venv\Scripts\role-crew.exe tool --role fixer --name write_text --arg path=hello.txt --arg text=OK
.\.venv\Scripts\role-crew.exe tool --role verifier --name read_file --arg path=hello.txt
```

## 下一版（API Key）

复制 `.env.example` 为 `.env`，填百炼/DeepSeek **通用** `sk-` 密钥（不要 `sk-sp-`）。然后实现 `role-crew run --task "..."`：每个角色用 `Actor` 循环选工具，`call_role` 才打开。

## 信封

所有角色输出同一形状，见 `src/role_crew/envelope.py`。`verified` 必须带至少一条成功 `evidence`，代码会拦。
