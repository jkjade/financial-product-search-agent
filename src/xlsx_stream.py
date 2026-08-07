from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import iterparse

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_MAIN = f"{{{_MAIN_NS}}}"


def _column_index(cell_reference: str) -> int:
    match = re.match(r"([A-Za-z]+)", cell_reference)
    if not match:
        raise ValueError(f"Invalid Excel cell reference: {cell_reference!r}")
    number = 0
    for char in match.group(1).upper():
        number = number * 26 + ord(char) - 64
    return number - 1


def _resolve_sheet_path(archive: ZipFile, sheet_index: int) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relation_targets = {
        relation.attrib["Id"]: relation.attrib["Target"] for relation in relations
    }
    sheets = workbook.findall(f"{_MAIN}sheets/{_MAIN}sheet")
    if sheet_index < 0 or sheet_index >= len(sheets):
        raise IndexError(f"Sheet index {sheet_index} is out of range")
    relation_id = sheets[sheet_index].attrib[f"{{{_REL_NS}}}id"]
    target = relation_targets[relation_id]
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("xl", target))


def _shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall(f"{_MAIN}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{_MAIN}t")))
    return values


def iter_xlsx_rows(path: str | Path, sheet_index: int = 0) -> Iterator[list[str]]:
    """Stream rows from an XLSX worksheet without loading the workbook into memory.

    The competition files use inline strings and numeric values. Shared strings,
    booleans, formulas with cached values, and sparse cells are also supported.
    """
    workbook_path = Path(path)
    if not workbook_path.exists():
        raise FileNotFoundError(workbook_path)

    with ZipFile(workbook_path) as archive:
        worksheet_path = _resolve_sheet_path(archive, sheet_index)
        shared = _shared_strings(archive)
        with archive.open(worksheet_path) as stream:
            for _, element in iterparse(stream, events=("end",)):
                if element.tag != f"{_MAIN}row":
                    continue
                cells: dict[int, str] = {}
                for cell in element.findall(f"{_MAIN}c"):
                    index = _column_index(cell.attrib.get("r", "A1"))
                    cell_type = cell.attrib.get("t")
                    if cell_type == "inlineStr":
                        value = "".join(
                            node.text or "" for node in cell.iter(f"{_MAIN}t")
                        )
                    else:
                        value_node = cell.find(f"{_MAIN}v")
                        raw_value = value_node.text if value_node is not None else ""
                        if cell_type == "s" and raw_value:
                            value = shared[int(raw_value)]
                        elif cell_type == "b":
                            value = "true" if raw_value == "1" else "false"
                        else:
                            value = raw_value
                    cells[index] = value
                if cells:
                    yield [cells.get(i, "") for i in range(max(cells) + 1)]
                else:
                    yield []
                element.clear()
