# 标书小助手（AI Coding 版）

> 上传招标文件 → 要点提取 → 风险扫描 → 标书提纲，全流程人工可编辑，支持导出 Word。

## 在线体验

<!-- 部署到 Streamlit Cloud 后，把下面的链接替换为你的应用地址 -->

**在线访问**：[TODO: 替换为 Streamlit Cloud 部署地址](https://share.streamlit.io)

> 公网部署版使用**演示资质数据**（不含真实编号），仅供功能体验。
> 如需用于正式投标，请在本地部署并替换为真实资质档案。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置 API Key

```bash
export DEEPSEEK_API_KEY="你的API Key"
```

也可在应用启动后，于左侧侧边栏输入。

### 3. 启动

```bash
streamlit run app.py
```

浏览器打开 http://localhost:8501

## 使用流程

```
上传招标文件 → 提取要点 → 人工确认（可编辑）
    → 风险扫描 → 人工确认（可编辑）
    → 生成标书提纲 → 导出 Word
```

## 项目结构

```
bid-agent/
├── app.py                        # Streamlit 主程序
├── requirements.txt              # 依赖
├── .gitignore                    # 忽略敏感/临时文件
├── config/
│   ├── qualifications.py         # 资质档案（有Excel就加载真实，否则用演示）
│   ├── qualifications_demo.py    # 演示资质数据（公网部署用，无真实编号）
│   └── rules.py                  # 废标规则库（有JSON就加载，否则用内置）
├── prompts/
│   ├── extract.py                # 要点提取 Prompt
│   ├── risk.py                   # 风险扫描 Prompt
│   └── outline.py                # 标书提纲 Prompt
└── core/
    ├── llm.py                     # DeepSeek API 调用
    ├── parser.py                  # PDF/Word 解析
    └── exporter.py                # Markdown → Word 导出
```

## 本地使用真实数据（可选）

本地如需加载真实资质档案，将以下文件放入 `config/` 目录即可（已被
`.gitignore` 忽略，不会上传）：

- `config/产业互联网资质清单.xlsx` — 真实资质/版权/专利清单
- `config/废标规则30条.json` — 真实废标规则

程序会自动检测：有真实文件就加载，没有就用演示数据。

## 部署到 Streamlit Cloud

1. 将本仓库推送到 GitHub（敏感文件已被 `.gitignore` 排除）
2. 前往 [share.streamlit.io](https://share.streamlit.io) 创建应用
3. 选择仓库、主文件填 `app.py`
4. 在 Secrets 中配置 `DEEPSEEK_API_KEY`
5. 部署后把访问链接填回本 README 顶部

## 对比 Dify 版新增功能

| 功能 | Dify 版 | Coding 版 |
|---|---|---|
| 人工确认要点 | ❌ | ✅ 可编辑 |
| 人工确认风险 | ❌ | ✅ 可编辑 |
| 导出 Word | ❌ | ✅ 一键导出 |
| 导出风险清单 | ❌ | ✅ 一键导出 |
| 历史记录 | ❌ | （后续加） |
| 知识库 | 空知识库 | （后续加） |
