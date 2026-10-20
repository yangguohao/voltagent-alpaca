# OpenRouter hello world

1. 将 OpenRouter API key 写入 `tmp/.env`：

   ```env
   OPENROUTER_API_KEY=sk-or-v1-...
   OPENROUTER_MODEL=openrouter/free
   ```

2. 从仓库根目录运行：

   ```bash
   python tmp/openrouter_hello.py
   ```

脚本调用 OpenRouter 的 `POST /api/v1/chat/completions`，并要求模型返回简短的
`Hello, world!`。`.env` 已被仓库的 `.gitignore` 排除，不会提交密钥。

## Groq

在同一个 `tmp/.env` 中配置：

```env
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant
```

然后运行：

```bash
python tmp/groq_hello.py
```
