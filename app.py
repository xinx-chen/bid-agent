"""
标书小助手 - Streamlit 主程序
运行方式：streamlit run app.py
"""

import os
import streamlit as st

# ========== 页面配置 ==========
st.set_page_config(
    page_title="标书小助手",
    page_icon="📋",
    layout="wide",
)

# ========== 全局样式：撑满全宽 ==========
st.markdown("""
<style>
    /* 让主内容区撑满浏览器，不再有 max-width 限制 */
    .block-container {
        max-width: none !important;
        padding-top: 1.5rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    /* 让 col2 的 text_area / code 占满列宽 */
    .stTextArea > div > div > textarea,
    .stCodeBlock > div {
        width: 100% !important;
    }
</style>
""", unsafe_allow_html=True)

# ========== 侧边栏：API Key 设置 ==========
with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input(
        "DeepSeek API Key",
        type="password",
        value=os.getenv("DEEPSEEK_API_KEY", ""),
        help="从 platform.deepseek.com 获取",
    )
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key

    st.divider()
    st.markdown("""
    **使用流程：**
    1. 上传招标文件
    2. 提取要点 → 人工确认
    3. 风险扫描 → 人工确认
    4. 生成标书提纲
    5. 导出 Word
    """)

# ========== 主界面 ==========
st.title("📋 标书小助手")
st.caption("联通数科投标智能助手 | 上传招标文件 → 要点提取 → 风险扫描 → 标书提纲")

# 初始化 session_state
if "file_text" not in st.session_state:
    st.session_state.file_text = ""
if "file_scanned" not in st.session_state:
    st.session_state.file_scanned = False
if "file_meta" not in st.session_state:
    st.session_state.file_meta = ""
if "bid_points" not in st.session_state:
    st.session_state.bid_points = ""
if "risk_report" not in st.session_state:
    st.session_state.risk_report = ""
if "bid_outline" not in st.session_state:
    st.session_state.bid_outline = ""

# ========== Step 1: 上传文件 ==========
st.header("1️⃣ 上传招标文件")
uploaded_file = st.file_uploader(
    "选择 PDF / DOCX / TXT 文件",
    type=["pdf", "docx", "txt"],
    help="支持 PDF、Word、纯文本格式",
)

if uploaded_file and not st.session_state.file_text:
    from core.parser import parse_uploaded_file
    with st.spinner("正在解析文件..."):
        try:
            result = parse_uploaded_file(uploaded_file)
            st.session_state.file_text = result.text
            st.session_state.file_scanned = result.is_scanned
            meta_parts = [f"{len(result.text)} 字"]
            if result.page_count:
                meta_parts.append(f"{result.page_count} 页")
            st.session_state.file_meta = "，".join(meta_parts)
            st.success(f"✅ 解析成功，共 {st.session_state.file_meta}")
            if result.is_scanned:
                st.warning(
                    "⚠️ 检测到该 PDF 超过半数页面提取不到文字，**疑似扫描件/图片版**。"
                    "当前文本可能不完整，建议先用 OCR 工具识别文字后重新上传，"
                    "否则要点提取可能严重遗漏。"
                )
        except Exception as e:
            st.error(f"❌ 解析失败：{e}")

# 显示解析文本（可折叠）
if st.session_state.file_text:
    label = f"📄 文件内容预览（{st.session_state.file_meta or str(len(st.session_state.file_text)) + ' 字'}）"
    with st.expander(label, expanded=False):
        st.text(st.session_state.file_text[:3000] + ("..." if len(st.session_state.file_text) > 3000 else ""))

# ========== Step 2: 要点提取 ==========
st.header("2️⃣ 要点提取")
if st.button("🚀 提取要点", disabled=not st.session_state.file_text, type="primary"):
    from core.llm import chat_stream, LLMError
    from core.pipeline import (
        needs_chunking,
        extract_bid_points_chunked,
        finalize_points,
    )
    from prompts.extract import build_extract_prompt

    file_text = st.session_state.file_text
    st.session_state.bid_points = ""

    try:
        if needs_chunking(file_text):
            # 大文件：分块提取（非流式），带进度条
            st.info(f"文件较长（{len(file_text)} 字），自动启用分块提取，避免超过模型上下文…")
            progress_bar = st.progress(0.0)
            status_line = st.empty()

            def _on_progress(done, total, msg):
                progress_bar.progress(done / total)
                status_line.caption(msg)

            with st.spinner("分块提取中…"):
                st.session_state.bid_points = extract_bid_points_chunked(
                    file_text, progress_cb=_on_progress
                )
            progress_bar.progress(1.0)
            status_line.caption("✅ 分块提取并合并完成")
            st.success("✅ 要点提取完成（已自动标准化时间格式、补充强制性条款）")
        else:
            # 普通文件：流式提取，收尾时统一做 JSON 容错/时间标准化/条款兜底
            with st.spinner("正在提取要点..."):
                messages = build_extract_prompt(file_text)
                stream_placeholder = st.empty()
                raw = ""
                for chunk in chat_stream(messages):
                    raw += chunk
                    stream_placeholder.code(raw, language="json")
            with st.spinner("正在校验 JSON 并补充强制性条款..."):
                st.session_state.bid_points = finalize_points(raw, file_text)
            st.success("✅ 要点提取完成（已自动标准化时间格式、补充强制性条款）")
    except LLMError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ 要点提取失败：{e}")

if st.session_state.bid_points:
    st.markdown("**📝 人工核对与编辑（JSON 格式）：**")
    st.session_state.bid_points = st.text_area(
        "如有错误请直接修改，确认无误后点下一步",
        value=st.session_state.bid_points,
        height=320,
    )

# ========== Step 3: 风险扫描 ==========
st.header("3️⃣ 风险扫描")
if st.button("🔍 扫描风险", disabled=not st.session_state.bid_points, type="primary"):
    from core.llm import chat_stream, LLMError
    from prompts.risk import build_risk_prompt
    try:
        with st.spinner("正在扫描投标风险..."):
            messages = build_risk_prompt(st.session_state.bid_points)
            st.session_state.risk_report = ""
            stream_placeholder = st.empty()
            for chunk in chat_stream(messages):
                st.session_state.risk_report += chunk
                stream_placeholder.markdown(st.session_state.risk_report)
    except LLMError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ 风险扫描失败：{e}")

if st.session_state.risk_report:
    st.markdown("**📝 人工确认（可忽略误报，直接在下方修改）：**")
    st.session_state.risk_report = st.text_area(
        "如有误报可直接删除对应行",
        value=st.session_state.risk_report,
        height=420,
    )

# ========== Step 4: 标书提纲 ==========
st.header("4️⃣ 标书提纲生成")
if st.button("📝 生成标书提纲", disabled=not st.session_state.risk_report, type="primary"):
    from core.llm import chat_stream, LLMError
    from prompts.outline import build_outline_prompt
    try:
        with st.spinner("正在生成标书提纲..."):
            messages = build_outline_prompt(
                st.session_state.bid_points,
                st.session_state.risk_report,
            )
            st.session_state.bid_outline = ""
            stream_placeholder = st.empty()
            for chunk in chat_stream(messages):
                st.session_state.bid_outline += chunk
                stream_placeholder.markdown(st.session_state.bid_outline)
    except LLMError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ 提纲生成失败：{e}")

if st.session_state.bid_outline:
    st.markdown("**📝 在线编辑提纲：**")
    st.session_state.bid_outline = st.text_area(
        "可直接修改大纲内容",
        value=st.session_state.bid_outline,
        height=520,
    )

# ========== Step 5: 导出 ==========
st.header("5️⃣ 导出交付")
if st.session_state.bid_outline:
    from core.exporter import markdown_to_docx

    col1, col2, col3 = st.columns(3)

    with col1:
        docx_bytes = markdown_to_docx(st.session_state.bid_outline, title="标书提纲")
        st.download_button(
            label="📄 导出标书提纲 Word",
            data=docx_bytes,
            file_name="标书提纲.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    with col2:
        risk_docx = markdown_to_docx(st.session_state.risk_report, title="投标风险扫描报告")
        st.download_button(
            label="⚠️ 导出风险清单 Word",
            data=risk_docx,
            file_name="投标风险清单.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    with col3:
        st.download_button(
            label="📋 导出全部 Markdown",
            data=f"# 项目要点\n\n{st.session_state.bid_points}\n\n---\n\n# 风险扫描\n\n{st.session_state.risk_report}\n\n---\n\n# 标书提纲\n\n{st.session_state.bid_outline}",
            file_name="标书小助手输出.md",
            mime="text/markdown",
        )

# ========== 重置 ==========
if st.button("🔄 重新开始"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()
