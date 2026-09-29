"""废标规则库 - 从 JSON 文件加载 30 条真实规则"""

import json
import os
import re

_RULES_FILE = os.path.join(os.path.dirname(__file__), "废标规则30条.json")

def _load_rules():
    """从 JSON 文件加载废标规则，加载失败则回退到内置 15 条"""
    try:
        with open(_RULES_FILE, "r", encoding="utf-8") as f:
            txt = f.read()
        # 修复 JSON 尾逗号
        txt = re.sub(r',\s*}', '}', txt)
        txt = re.sub(r',\s*]', ']', txt)
        data = json.loads(txt)
        raw = data.get("废标（否决投标）规则列表", [])
        rules = []
        for item in raw:
            # 映射字段：层级+法规依据+废标条款 → 兼容旧格式
            rule_text = item.get("废标条款", "")
            level_raw = item.get("层级", "")
            # 层级映射为严重度：国标→致命，省/市→高危
            level = "致命" if level_raw == "国标" else "高危"
            rules.append({
                "id": item.get("序号", len(rules) + 1),
                "rule": rule_text,
                "level": level,
                "层级": level_raw,
                "法规依据": item.get("法规依据", ""),
            })
        if rules:
            return rules
    except Exception:
        pass
    # 回退：内置 15 条演示规则
    return [
        {"id": 1, "rule": "投标文件未按要求签字盖章", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 2, "rule": "投标文件未按规定格式编制", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 3, "rule": "投标有效期不满足", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 4, "rule": "逾期送达", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 5, "rule": "不具备要求的资质等级", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 6, "rule": "营业执照过期", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 7, "rule": "近3年业绩不满足数量/金额", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 8, "rule": "项目经理无要求证书", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 9, "rule": "投标保证金金额不足或形式不对", "level": "致命", "层级": "国标", "法规依据": "政府采购法"},
        {"id": 10, "rule": "报价超预算", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 11, "rule": "带★号技术参数不满足", "level": "致命", "层级": "国标", "法规依据": "机电产品国际招标投标实施办法"},
        {"id": 12, "rule": "未提供要求的检测报告", "level": "高危", "层级": "国标", "法规依据": "招投标通用条款"},
        {"id": 13, "rule": "不接受联合体但我方想联合体", "level": "致命", "层级": "国标", "法规依据": "招标投标法实施条例"},
        {"id": 14, "rule": "未走联通内部CT签报审批", "level": "高危", "层级": "内部", "法规依据": "联通内部流程"},
        {"id": 15, "rule": "未走联通法务合同审核", "level": "高危", "层级": "内部", "法规依据": "联通内部流程"},
    ]


DISQUALIFICATION_RULES = _load_rules()


def format_rules_md():
    """把规则库格式化成 Markdown 文本，含层级和法规依据"""
    lines = [f"【废标规则库（共{len(DISQUALIFICATION_RULES)}条）】"]
    for r in DISQUALIFICATION_RULES:
        level_tag = "🔴" if r["level"] == "致命" else "🟡"
        lines.append(
            f"{r['id']}. [{r.get('层级', '')}] {r['rule']} "
            f"→ {level_tag}{r['level']}（依据：{r.get('法规依据', '')}）"
        )
    return "\n".join(lines)
