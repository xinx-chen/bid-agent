"""Word 导出模块 - 按联通范本格式生成投标文件

字体策略：
- 正文：思源宋体（Noto Serif CJK SC）
- 标题：华文黑体（STHeiti）
- 每段末尾自动加签章行
"""

import re
import io
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


FONT_BODY = "Noto Serif CJK SC"
FONT_HEADING = "STHeiti"

# 投标主体（固定）
BIDDER_NAME = "中国联合网络通信有限公司成都市分公司"
SEAL_TEXT = "（单位盖章）"


BLACK = (0, 0, 0)


def _set_run_font(run, font_name=FONT_BODY, size=None, bold=None, color=BLACK):
    run.font.name = font_name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ["w:eastAsia", "w:ascii", "w:hAnsi", "w:cs"]:
        rfonts.set(qn(attr), font_name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)


def _set_style_font(style, font_name=FONT_BODY, size=11, color=BLACK):
    style.font.name = font_name
    style.font.size = Pt(size)
    if color is not None:
        style.font.color.rgb = RGBColor(*color)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ["w:eastAsia", "w:ascii", "w:hAnsi", "w:cs"]:
        rfonts.set(qn(attr), font_name)


def _add_seal_footer(doc, date_str="2026年4月15日"):
    """添加签章行：投标人名称+盖章+日期"""
    p1 = doc.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p1.add_run(f"投标人名称：{BIDDER_NAME}{SEAL_TEXT}")
    _set_run_font(run, FONT_BODY, 11)

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p2.add_run(f"日期：{date_str}")
    _set_run_font(run, FONT_BODY, 11)

    doc.add_paragraph()  # 空行


def _add_table_with_style(doc, rows, has_header=True):
    """添加表格，表头加粗"""
    if not rows:
        return
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for r_idx, row_data in enumerate(rows):
        for c_idx, cell_text in enumerate(row_data):
            if c_idx < len(table.rows[r_idx].cells):
                cell = table.rows[r_idx].cells[c_idx]
                cell.text = ""
                p = cell.paragraphs[0]
                run = p.add_run(str(cell_text))
                is_header = (r_idx == 0 and has_header)
                _set_run_font(run, FONT_BODY, 10, bold=is_header)
    doc.add_paragraph()


def _add_commitment_letter(doc, title, recipient, project_name, project_id,
                            clauses, date_str="2026年4月15日"):
    """添加承诺函"""
    h = doc.add_heading(title, level=2)
    for run in h.runs:
        _set_run_font(run, FONT_HEADING, 14, bold=True)

    p = doc.add_paragraph()
    run = p.add_run("承诺函")
    _set_run_font(run, FONT_BODY, 11, bold=True)

    p = doc.add_paragraph()
    run = p.add_run(f"致：{recipient}")
    _set_run_font(run, FONT_BODY, 11)

    p = doc.add_paragraph()
    run = p.add_run(
        f"我单位作为{project_name}（项目编号：{project_id}）的投标（响应）供应商，"
        f"自愿参与本项目政府采购活动，充分理解采购文件的要求，"
        f"在此郑重声明及承诺："
    )
    _set_run_font(run, FONT_BODY, 11)

    for clause in clauses:
        p = doc.add_paragraph()
        run = p.add_run(clause)
        _set_run_font(run, FONT_BODY, 11)

    p = doc.add_paragraph()
    run = p.add_run(
        "本单位对上述承诺的内容事项真实性负责。如经查实上述承诺的内容事项存在虚假，"
        "我单位愿意接受以提供虚假材料谋取成交追究法律责任。"
    )
    _set_run_font(run, FONT_BODY, 11)

    p = doc.add_paragraph()
    run = p.add_run("特此承诺！")
    _set_run_font(run, FONT_BODY, 11, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(f"供应商名称：{BIDDER_NAME}（签章）")
    _set_run_font(run, FONT_BODY, 11)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(f"日 期：{date_str}")
    _set_run_font(run, FONT_BODY, 11)

    doc.add_paragraph()


def markdown_to_docx(markdown_text: str, title: str = "投标文件") -> bytes:
    """把 Markdown 文本转成 Word 文档，按联通范本格式"""
    doc = Document()

    # 全局样式
    _set_style_font(doc.styles["Normal"], FONT_BODY, 11)
    for level in range(1, 7):
        sname = f"Heading {level}"
        if sname in doc.styles:
            _set_style_font(doc.styles[sname], FONT_HEADING, 18 - level * 2)
    for sname in ("List Bullet", "List Number"):
        if sname in doc.styles:
            _set_style_font(doc.styles[sname], FONT_BODY, 11)

    # 文档大标题
    heading = doc.add_heading(title, level=0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in heading.runs:
        _set_run_font(run, FONT_HEADING, 22, bold=True)

    # 按 === 分段
    sections = re.split(r"^===\s*(.*)\s*===", markdown_text)

    # 如果没有 === 分段标记，走原来的逐行解析
    if len(sections) <= 1:
        _parse_markdown_lines(doc, markdown_text)
    else:
        # sections = ['', '标题1', '内容1', '标题2', '内容2', ...]
        i = 1
        while i < len(sections):
            section_title = sections[i].strip() if i < len(sections) else ""
            section_content = sections[i + 1].strip() if i + 1 < len(sections) else ""
            if section_title:
                _parse_section(doc, section_title, section_content)
            i += 2

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _parse_section(doc, section_title, content):
    """解析一个 === 分段"""
    # 段标题
    h = doc.add_heading(section_title, level=1)
    for run in h.runs:
        _set_run_font(run, FONT_HEADING, 16, bold=True)
    doc.add_paragraph()

    # 解析内容
    _parse_markdown_lines(doc, content)


def _parse_markdown_lines(doc, text):
    """逐行解析 Markdown"""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if not line.strip():
            i += 1
            continue

        # 分隔线
        if line.strip() in ("---", "***", "___"):
            i += 1
            continue

        # 标题
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = len(heading_match.group(1))
            text_content = heading_match.group(2)
            p = doc.add_heading(text_content, level=min(level, 6))
            size_map = {1: 18, 2: 16, 3: 14, 4: 12, 5: 12, 6: 11}
            for run in p.runs:
                _set_run_font(run, FONT_HEADING, size_map.get(min(level, 6), 12), bold=True)
            i += 1
            continue

        # 表格
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            _parse_table(doc, table_lines)
            continue

        # 列表项
        list_match = re.match(r"^(\s*)[-*]\s+(.*)", line)
        if list_match:
            text_content = list_match.group(2)
            p = doc.add_paragraph(style="List Bullet")
            _add_bold_runs(p, text_content)
            i += 1
            continue

        # 普通段落
        p = doc.add_paragraph()
        _add_bold_runs(p, line)
        i += 1


def _parse_table(doc, table_lines):
    """解析 Markdown 表格"""
    rows = []
    for tl in table_lines:
        cells = [c.strip() for c in tl.strip().strip("|").split("|")]
        if all(re.match(r"^[\s\-:]+$", c) for c in cells):
            continue
        rows.append(cells)

    if not rows:
        return

    _add_table_with_style(doc, rows, has_header=True)


def _add_bold_runs(paragraph, text):
    """处理 **粗体** 语法，添加到段落"""
    parts = re.split(r"(\*\*.*?\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            _set_run_font(run, FONT_BODY, 11, bold=True)
        else:
            run = paragraph.add_run(part)
            _set_run_font(run, FONT_BODY, 11)
