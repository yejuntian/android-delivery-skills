#!/usr/bin/env python3
"""脚本名称：document_sources.py

用途：把 DOCX 需求输入转换为保留结构的可审阅 Markdown。

核心流程：读取标准 OOXML 正文、段落样式和超链接关系，按原顺序转换标题、列表、表格、
链接和图片缺口标记，不依赖第三方 Word 解析库。

职责边界：只读取文档并返回文本；不判断业务语义、不修改需求文件、不访问网络。
"""

from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W = f"{{{WORD_NS}}}"
R = f"{{{REL_NS}}}"
HEADING_RE = re.compile(r"(?:heading|标题)\s*([1-6])", re.IGNORECASE)


class DocumentSourceError(RuntimeError):
    """表示需求文档损坏或无法转换为可审阅 Markdown。"""


def _relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    """读取正文使用的关系映射；没有关系文件时返回空映射。"""
    try:
        root = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    except KeyError:
        return {}
    except ET.ParseError as exc:
        raise DocumentSourceError(f"DOCX 关系文件损坏: {exc}") from exc
    return {
        item.attrib["Id"]: item.attrib["Target"]
        for item in root.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
        if item.attrib.get("Id") and item.attrib.get("Target")
    }


def _style_role(value: str) -> str | None:
    """把样式 ID 或名称转换为 Markdown 标题角色。"""
    heading = HEADING_RE.search(value)
    if heading:
        return f"heading:{heading.group(1)}"
    if value.lower() in {"title", "标题"}:
        return "title"
    return None


def _paragraph_style_roles(archive: zipfile.ZipFile) -> dict[str, str]:
    """解析段落样式名称、继承和 outline level，避免把 style ID 当显示名称。"""
    try:
        root = ET.fromstring(archive.read("word/styles.xml"))
    except KeyError:
        return {}
    except ET.ParseError as exc:
        raise DocumentSourceError(f"DOCX 样式文件损坏: {exc}") from exc

    definitions: dict[str, tuple[str, str, int | None]] = {}
    for style in root.findall(f"{W}style"):
        if style.attrib.get(f"{W}type") not in {None, "paragraph"}:
            continue
        style_id = style.attrib.get(f"{W}styleId", "")
        if not style_id:
            continue
        name = style.find(f"{W}name")
        based_on = style.find(f"{W}basedOn")
        outline = style.find(f"{W}pPr/{W}outlineLvl")
        outline_level: int | None = None
        if outline is not None:
            try:
                candidate = int(outline.attrib.get(f"{W}val", ""))
            except ValueError:
                candidate = -1
            if 0 <= candidate <= 5:
                outline_level = candidate
        definitions[style_id] = (
            name.attrib.get(f"{W}val", "") if name is not None else "",
            based_on.attrib.get(f"{W}val", "") if based_on is not None else "",
            outline_level,
        )

    resolved: dict[str, str] = {}

    def resolve(style_id: str, active: set[str]) -> str | None:
        if style_id in resolved:
            return resolved[style_id]
        if style_id in active or style_id not in definitions:
            return _style_role(style_id)
        name, based_on, outline_level = definitions[style_id]
        role = _style_role(style_id) or _style_role(name)
        if role is None and outline_level is not None:
            role = f"heading:{outline_level + 1}"
        if role is None and based_on:
            role = resolve(based_on, {*active, style_id})
        if role is not None:
            resolved[style_id] = role
        return role

    for style_id in definitions:
        resolve(style_id, set())
    return resolved


def _node_text(node: ET.Element) -> str:
    """按 OOXML 节点顺序提取文字、制表符和显式换行。"""
    parts: list[str] = []
    for child in node.iter():
        if child.tag == f"{W}t":
            parts.append(child.text or "")
        elif child.tag == f"{W}tab":
            parts.append("\t")
        elif child.tag in {f"{W}br", f"{W}cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _paragraph_text(paragraph: ET.Element, relationships: dict[str, str]) -> str:
    """提取段落文字并保留超链接和无法文本化的图片缺口。"""
    parts: list[str] = []
    for child in paragraph:
        if child.tag == f"{W}hyperlink":
            label = _node_text(child)
            target = relationships.get(child.attrib.get(f"{R}id", ""))
            parts.append(f"[{label}]({target})" if label and target else label)
        else:
            parts.append(_node_text(child))
    text = "".join(parts).strip()
    if any(
        node.tag in {f"{W}drawing", f"{W}pict", f"{W}object"}
        for node in paragraph.iter()
    ):
        text = f"{text} [内嵌图片：需结合原 DOCX 核对]".strip()
    return text


def _paragraph_markdown(
    paragraph: ET.Element,
    relationships: dict[str, str],
    style_roles: dict[str, str],
) -> str:
    """根据段落样式转换标题、列表或普通正文。"""
    text = _paragraph_text(paragraph, relationships)
    if not text:
        return ""
    properties = paragraph.find(f"{W}pPr")
    style_value = ""
    is_list = False
    if properties is not None:
        style = properties.find(f"{W}pStyle")
        if style is not None:
            style_value = style.attrib.get(f"{W}val", "")
        is_list = properties.find(f"{W}numPr") is not None
    role = style_roles.get(style_value) or _style_role(style_value)
    if role and role.startswith("heading:"):
        return f"{'#' * int(role.partition(':')[2])} {text}"
    if role == "title":
        return f"# {text}"
    return f"- {text}" if is_list else text


def _table_markdown(table: ET.Element, relationships: dict[str, str]) -> str:
    """把表格按行列转换成 Markdown，保持单元格内段落顺序。"""
    rows: list[list[str]] = []
    for row in table.findall(f"{W}tr"):
        cells: list[str] = []
        for cell in row.findall(f"{W}tc"):
            paragraphs = [
                _paragraph_text(paragraph, relationships)
                for paragraph in cell.findall(f"{W}p")
            ]
            cells.append("<br>".join(filter(None, paragraphs)).replace("|", "\\|"))
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(map(len, rows))
    normalized = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(normalized[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in normalized[1:])
    return "\n".join(lines)


def docx_to_markdown(path: str | Path) -> str:
    """按正文顺序保留标题、列表、表格、链接和图片缺口。"""
    source = Path(path).expanduser().resolve()
    try:
        with zipfile.ZipFile(source) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
            relationships = _relationships(archive)
            style_roles = _paragraph_style_roles(archive)
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise DocumentSourceError(
            f"DOCX 文件损坏或结构不受支持: {source}: {exc}"
        ) from exc
    body = root.find(f"{W}body")
    if body is None:
        raise DocumentSourceError(f"DOCX 缺少正文: {source}")
    if not any((node.text or "").strip() for node in body.iter(f"{W}t")):
        return ""
    blocks: list[str] = []
    for child in body:
        if child.tag == f"{W}p":
            block = _paragraph_markdown(child, relationships, style_roles)
        elif child.tag == f"{W}tbl":
            block = _table_markdown(child, relationships)
        else:
            continue
        if block:
            blocks.append(block)
    return "\n\n".join(blocks).strip()
