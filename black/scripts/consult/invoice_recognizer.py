from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import fitz
from openai import OpenAI


CONFIG_FILE = Path(__file__).resolve().parents[2] / "configs" / "CONSULT_invoice_recognizer.json"
SUMMARY_FILE_NAME = "汇总表.xlsx"
SUMMARY_SHEET_NAME = "汇总表"
SUMMARY_HEADERS = [
    "代理",
    "客户号",
    "申报国家",
    "公司中文名",
    "申报期间",
    "申报方式",
    "税号",
    "发票总个数",
    "成功提取个数",
    "失败个数",
    "递延总金额",
    "可抵扣总金额",
    "是否已出草稿",
]
RESULT_SHEET_NAME = "结果输出表格"
RESULT_FILE_SUFFIX = "-结果输出表格.xlsx"
RESULT_HEADERS = [
    "客户号",
    "国家",
    "公司名",
    "申报周期",
    "税号",
    "发票文件",
    "单据日期",
    "公司名是否存在",
    "MRN号",
    "原始金额",
    "单据类型",
    "递延单据",
    "可抵扣单据",
    "错误信息",
]
LIST_AGENT_COLUMN_INDEX = 1
LIST_CUSTOMER_COLUMN_INDEX = 3
LIST_DECLARATION_COUNTRY_COLUMN_INDEX = 4
LIST_COMPANY_NAME_CN_COLUMN_INDEX = 5
LIST_COMPANY_NAME_EN_COLUMN_INDEX = 6
LIST_DECLARATION_PERIOD_COLUMN_INDEX = 8
LIST_DECLARATION_METHOD_COLUMN_INDEX = 9
LIST_TAX_NUMBER_COLUMN_INDEX = 10
SUMMARY_CUSTOMER_COLUMN_INDEX = 2
SUMMARY_STATUS_COLUMN_INDEX = 13
MISSING_CUSTOMER_MESSAGE = "在总清单未找到该客户号"
ZERO_PDF_MESSAGE = "发票个数为0"
PDF_PAGE_LIMIT_MESSAGE = "PDF页数超过20，不符合规范"
INVALID_COUNTRY_MESSAGE = "当前申报国家不是英国或德国"
MODEL_RECOGNITION_MESSAGE = "当前pdf内容包含【Exempla】或【Type d’imposition:】，需调用模型识别"
UK_IMPORT_ENTRY_MESSAGE = "当前pdf内容包含【IMPORT ENTRY ACCEPTANCE ADVICE】，无需调用模型识别"
UK_VAT_REGISTRATION_MESSAGE = "当前pdf内容包含【VAT registration number】，无需调用模型识别"
UK_MODEL_B_MESSAGE = "当前pdf内容不包含【VAT registration number】或【IMPORT ENTRY ACCEPTANCE ADVICE】，需调用模型识别"
PDF_PAGE_LIMIT = 20
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NAMESPACES = {
    "main": SPREADSHEET_NS,
    "rel": RELATIONSHIP_NS,
    "pkg": PACKAGE_RELATIONSHIP_NS,
}
UK_MRN_PATTERN = re.compile(r"\d{2}[A-Z0-9]{13}[A-Z]{2}\d")
UK_DATE_DASH_PATTERN = re.compile(r"\d{2}-\d{2}-\d{4}")
UK_DATE_SLASH_PATTERN = re.compile(r"\b(?:0[1-9]|[12]\d|3[01])\/(?:0[1-9]|1[0-2])\/\d{4}\b")
UK_IMPORT_ENTRY_B00_LINE_PATTERN = re.compile(r".*B00.*(?=\r?\n.*CDS)", re.IGNORECASE)
UK_IMPORT_ENTRY_B00_LINE_FALLBACK_PATTERN = re.compile(r"^[^\r\n]*B00[^\r\n]*$", re.IGNORECASE | re.MULTILINE)
UK_TOTAL_VAT_LINE_PATTERN = re.compile(r"Total VAT (?:postponed|paid):\s*[£\u00A3]?[\d,.]+", re.IGNORECASE)
MODEL_TRIGGER_PATTERN = re.compile(r"exempla|type d[’']imposition:", re.IGNORECASE)
MODEL_JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
DEFERRED_DOCUMENT_TYPE_VALUES = {"0", "dispense", "vrijstelling", "vrijgestelling"}
MODEL_BASE_URL = "https://api.moonshot.cn/v1"
MODEL_NAME = "kimi-k2.5"
MODEL_API_KEY = os.getenv("MOONSHOT_API_KEY") or "sk-b7h4fryiqHdBwNvkKE85COl0CJ7PlgXJWZTyNKp2OWtjxmBU"
MODEL_SYSTEM_PROMPT = (
    "你是专业的PDF海关单据数据提取器，专门处理德国进口报关单（Zollanmeldung / Déclaration en douane）。\n"
    "\n"
    "任务：从PDF中提取所有税种代码为 B00 的数据，并最终输出原始金额、单据类型和总金额。\n"
    "\n"
    "【提取步骤】\n"
    "1. 遍历PDF中的每一个商品项（article）及其税费表格。\n"
    "2. 先定位税费表格中的 Type 列或 Type d’imposition 列，只在这两个列中搜索值为 B00 的行。\n"
    "3. 如果存在多个 B00 行，必须全部遍历并提取。\n"
    "4. 对每一个已确认的 B00 行：\n"
    "   - 在标题为「Maatstaf van heffing」或「Base d'imposition」或「Bemessungsgrundlage」或「Base」的列中，提取与该 B00 行交叉单元格的内容，作为该行的原始金额。\n"
    "   - 在标题为「Montant dû de l’imposition」的列、标题包含「Montant」的列、或标题为「Bedrag」的列中，提取与该 B00 行交叉单元格的内容，作为该行对应的 document_type 候选值。\n"
    "   - 如果该 Montant/Bedrag 单元格为空白、空字符串或无内容，则该行对应值视为 null。\n"
    "5. 所有值都必须来自“同一个 B00 行”和“正确列标题”的交叉位置，不能取相邻列、上下行或表格外部的值。\n"
    "\n"
    "【字段生成规则】\n"
    "1. original_amount：将所有 B00 行的 Base 值按出现顺序用 ' + ' 拼接，保留原始格式和货币符号。\n"
    "2. document_type：取最后一个 B00 行对应的 Montant/Bedrag/Montant dû de l’imposition 列的值，原样输出；如果该单元格为空，则输出 null。\n"
    "3. total_amount：将所有 B00 行的 Base 值按数值相加后输出结果。\n"
    "   - 需要进行数值计算，但输出时必须保持与原文金额风格一致。\n"
    "   - 如果所有 Base 都带相同币种符号，则 total_amount 不需要保留该币种符号并且要去掉千分位分隔符，逗号转为小数点。\n"
    "   - 例如：€ 36.034,90 + € 1.200,00 + € 500,00 = 37734.90\n"
    "\n"
    "【严格规则】\n"
    "- 第一步永远是先在 Type 列或 Type d’imposition 列定位 B00 行，这是唯一合法起点。\n"
    "- 如果页面其他位置出现 B00，但不在税费表格的 Type 列或 Type d’imposition 列中，必须忽略。\n"
    "- Base 值只能来自 B00 行与以下列的交叉单元格：Maatstaf van heffing / Base d'imposition / Bemessungsgrundlage / Base。\n"
    "- document_type 只能来自最后一个 B00 行与以下列的交叉单元格：Montant dû de l’imposition / 标题包含「Montant」的列 / Bedrag。\n"
    "- 如果表格中同时存在「Montant dû de l’imposition」和其他包含「Montant」的列，优先使用「Montant dû de l’imposition」这一列。\n"
    "- 绝对不能把「Mode de paiement」列当成 document_type。\n"
    "- 绝对不能把支付方式列中的单个字母（例如 P、E、D、C 等）误当成 document_type。\n"
    "- 绝对不能把 Base d'imposition、Maatstaf van heffing、Bemessungsgrundlage、Base 这些 Base 列的值复制到 document_type。\n"
    "- 如果 Montant/Bedrag/Montant dû de l’imposition 单元格为空，document_type 必须为 null。\n"
    "- 如果提取出的 document_type 是单个字母（如 P、E、D、C），说明读错列，必须改为 null。\n"
    "- 如果提取出的 document_type 与该行 Base 值相同或明显属于金额格式，说明读错列，必须改为 null。\n"
    "\n"
    "【金额计算规则】\n"
    "- total_amount 基于所有 B00 行的 Base 值计算。\n"
    "- 计算时需要正确识别欧洲金额格式，例如：36.034,90 表示 36034.90。\n"
    "- 输出 total_amount 时，必须保留欧洲格式（千位点、小数逗号）以及原有币种符号。\n"
    "- 如果任意一个 Base 值无法确认，则 total_amount 输出 null。\n"
    "- 如果没有找到任何 B00 行，则三个字段都输出 null。\n"
    "\n"
    "【数据准确性要求】\n"
    "- 你必须100%确认数据正确后才能输出。\n"
    "- 任何不确定值都输出 null，绝对禁止猜测、编造或推断。\n"
    "- 所有提取文本必须原样输出，保留货币符号、空格、千位分隔符和小数格式。\n"
    "\n"
    "【输出要求 - 极其重要】\n"
    "- 禁止输出任何分析过程、解释说明、页面摘要或思考过程。\n"
    "- 禁止输出 markdown 格式（如 ## 标题、```json 代码块等）。\n"
    "- 禁止输出任何非 JSON 内容（如 \"第1页\"、\"Article 1\" 等描述）。\n"
    "- 必须且只能输出一个纯文本的合法 JSON 对象。\n"
    "- JSON 外不允许有任何字符（包括空格、换行、注释）。\n"
    "- JSON 结构固定如下：\n"
    "{\n"
    '  "original_amount": "所有B00行Base值按顺序拼接后的字符串，不确定则为 null",\n'
    '  "document_type": "最后一个B00行Montant/Bedrag/Montant dû de l’imposition列对应的值，不确定则为 null",\n'
    '  "total_amount": "所有B00行Base数值相加后的结果，不确定则为 null"\n'
    "}\n"
    "- 不允许新增、删除、修改任何字段名。\n"
    "\n"
    "【违规惩罚】\n"
    "如果输出包含任何非 JSON 内容（分析、解释、markdown、代码块标记），视为严重错误。\n"
    "\n"
    "严格执行：只输出纯 JSON，先找 Type 列或 Type d’imposition 列中的 B00，再按列标题取同一行交叉值；任何偏离规则的提取都视为错误，不确定就输出 null。"
)
UK_MODEL_B_SYSTEM_PROMPT = (
    "你是报关税表数据提取器。根据PDF表格内容提取 tax_assessed 和 payment_amount，只输出 JSON。\n"
    "规则：\n"
    "1. 仅处理包含 B00 的报关表格。\n"
    "2. 优先在“Tax type”列中查找包含 B00 的行。\n"
    "3. 若有多个 B00 行，优先选择带 VAT 或 PVA 的那一行；单独 B00 优先级较低。\n"
    "4. 不得选择 Total、A00 或其他非 B00 行。\n"
    "5. tax_assessed 必须来自该 B00 行中，列标题包含 Assessed Amount、Tax Assessed、Amount Assessed、Tax Assessed Amount 任一关键词的单元格。\n"
    "6. payment_amount 必须来自同一张表格、同一 B00 行中，列标题包含 Amount Payable、Payment Amount、Payable Amount、Payable amount 任一关键词的单元格。\n"
    "7. tax_assessed 和 payment_amount 必须来自同一张表、同一行，不得跨行或跨表提取。\n"
    "8. 若找不到对应值，返回 null。\n"
    "9. 金额必须原样输出，不得修改、猜测或编造。\n"
    '只输出合法 JSON：{"tax_assessed": string | null, "payment_amount": string | null}'
)
UK_MODEL_B_KEYWORDS = ["B00", "Tax type", "Assessed", "Amount"]


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}")

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def validate_config(config: dict) -> tuple[Path, Path]:
    folder_value = (config.get("folderPath") or "").strip()
    list_excel_value = (config.get("excelPath") or config.get("listExcelPath") or "").strip()

    if not folder_value:
        raise ValueError("缺少递延税单据总文件夹路径配置。")

    if not list_excel_value:
        raise ValueError("缺少 Excel 清单文件路径配置。")

    folder_path = Path(folder_value)
    list_excel_path = Path(list_excel_value)

    if not folder_path.exists():
        raise FileNotFoundError(f"递延税单据总文件夹不存在: {folder_path}")

    if not folder_path.is_dir():
        raise NotADirectoryError(f"递延税单据总文件夹不是有效目录: {folder_path}")

    if not list_excel_path.exists():
        raise FileNotFoundError(f"Excel 清单文件不存在: {list_excel_path}")

    if not list_excel_path.is_file():
        raise FileNotFoundError(f"Excel 清单路径不是有效文件: {list_excel_path}")

    if list_excel_path.suffix.lower() != ".xlsx":
        raise ValueError("当前仅支持读取 .xlsx 格式的 Excel 清单文件。")

    return folder_path, list_excel_path


def normalize_customer_id(value: str) -> str:
    text = value.strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def excel_column_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def column_index_from_cell_reference(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha()).upper()
    if not letters:
        return 0

    column_index = 0
    for character in letters:
        column_index = column_index * 26 + (ord(character) - 64)
    return column_index


def build_sheet_xml(rows: list[list[str]]) -> str:
    last_column = max((len(row) for row in rows), default=1)
    last_row = max(len(rows), 1)
    dimension = f"A1:{excel_column_name(last_column)}{last_row}"

    row_xml_parts: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cell_xml_parts: list[str] = []
        for column_index, value in enumerate(row, start=1):
            if value == "":
                continue

            cell_reference = f"{excel_column_name(column_index)}{row_index}"
            cell_xml_parts.append(
                f'<c r="{cell_reference}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )

        row_xml_parts.append(f'<row r="{row_index}">{"".join(cell_xml_parts)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{SPREADSHEET_NS}">'
        f'<dimension ref="{dimension}"/>'
        "<sheetData>"
        f'{"".join(row_xml_parts)}'
        "</sheetData>"
        "</worksheet>"
    )


def write_workbook(workbook_path: Path, sheet_name: str, rows: list[list[str]]) -> None:
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{SPREADSHEET_NS}" '
        f'xmlns:r="{RELATIONSHIP_NS}">'
        f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_RELATIONSHIP_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_RELATIONSHIP_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Python</Application>"
        "</Properties>"
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>invoice_recognizer</dc:creator>"
        "<cp:lastModifiedBy>invoice_recognizer</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created_at}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created_at}</dcterms:modified>'
        "</cp:coreProperties>"
    )

    with ZipFile(workbook_path, "w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml)
        workbook.writestr("_rels/.rels", root_rels_xml)
        workbook.writestr("docProps/app.xml", app_xml)
        workbook.writestr("docProps/core.xml", core_xml)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", build_sheet_xml(rows))


def write_summary_workbook(summary_path: Path, rows: list[list[str]]) -> None:
    write_workbook(summary_path, SUMMARY_SHEET_NAME, rows)


def read_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []

    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    shared_strings: list[str] = []
    for item in root.findall("main:si", NAMESPACES):
        text = "".join(node.text or "" for node in item.findall(".//main:t", NAMESPACES))
        shared_strings.append(text)
    return shared_strings


def resolve_first_sheet_path(workbook: ZipFile) -> str:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    relationship_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))

    relationship_by_id = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in relationship_root.findall("pkg:Relationship", NAMESPACES)
    }

    first_sheet = workbook_root.find("main:sheets/main:sheet", NAMESPACES)
    if first_sheet is None:
        raise ValueError("Excel 清单中未找到任何工作表。")

    relation_id = first_sheet.attrib.get(f"{{{RELATIONSHIP_NS}}}id")
    if not relation_id:
        raise ValueError("Excel 清单工作表缺少关系定义。")

    target = relationship_by_id.get(relation_id)
    if not target:
        raise ValueError("Excel 清单工作表关系无效。")

    return f"xl/{target.lstrip('/')}"


def read_cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", NAMESPACES))

    if cell_type == "s":
        shared_index = cell.findtext("main:v", default="", namespaces=NAMESPACES)
        if not shared_index:
            return ""

        return shared_strings[int(shared_index)]

    return cell.findtext("main:v", default="", namespaces=NAMESPACES).strip()


def load_xlsx_rows(excel_path: Path) -> list[list[str]]:
    with ZipFile(excel_path, "r") as workbook:
        shared_strings = read_shared_strings(workbook)
        sheet_path = resolve_first_sheet_path(workbook)
        sheet_root = ET.fromstring(workbook.read(sheet_path))

    rows: list[list[str]] = []
    for row in sheet_root.findall("main:sheetData/main:row", NAMESPACES):
        values: list[str] = []
        for cell in row.findall("main:c", NAMESPACES):
            column_index = column_index_from_cell_reference(cell.attrib.get("r", ""))
            if column_index <= 0:
                continue

            while len(values) < column_index - 1:
                values.append("")

            values.append(read_cell_text(cell, shared_strings))

        rows.append(values)

    return rows


def read_row_value(row: list[str], column_index: int) -> str:
    if column_index <= 0 or len(row) < column_index:
        return ""
    return row[column_index - 1].strip()


def extract_list_customer_records(list_excel_path: Path) -> dict[str, dict[str, str]]:
    rows = load_xlsx_rows(list_excel_path)
    customer_records: dict[str, dict[str, str]] = {}

    for row_index, row in enumerate(rows[1:], start=2):
        if len(row) < LIST_CUSTOMER_COLUMN_INDEX:
            continue

        customer_id = normalize_customer_id(read_row_value(row, LIST_CUSTOMER_COLUMN_INDEX))
        if customer_id:
            customer_records[customer_id] = {
                "row_index": str(row_index),
                "agent": read_row_value(row, LIST_AGENT_COLUMN_INDEX),
                "customer_id": customer_id,
                "declaration_country": read_row_value(row, LIST_DECLARATION_COUNTRY_COLUMN_INDEX),
                "company_name_cn": read_row_value(row, LIST_COMPANY_NAME_CN_COLUMN_INDEX),
                "company_name_en": read_row_value(row, LIST_COMPANY_NAME_EN_COLUMN_INDEX),
                "declaration_period": read_row_value(row, LIST_DECLARATION_PERIOD_COLUMN_INDEX),
                "declaration_method": read_row_value(row, LIST_DECLARATION_METHOD_COLUMN_INDEX),
                "tax_number": read_row_value(row, LIST_TAX_NUMBER_COLUMN_INDEX),
            }

    return customer_records


def collect_customer_folders(folder_path: Path) -> list[tuple[str, Path]]:
    customer_folders: list[tuple[str, Path]] = []

    for item in sorted(folder_path.iterdir(), key=lambda path: path.name):
        if not item.is_dir():
            continue

        customer_id = normalize_customer_id(item.name)
        if customer_id:
            customer_folders.append((customer_id, item))

    return customer_folders


def collect_customer_pdf_files(customer_folder_path: Path) -> list[Path]:
    return sorted(
        [
            item
            for item in customer_folder_path.iterdir()
            if item.is_file() and item.suffix.lower() == ".pdf"
        ],
        key=lambda path: path.name.lower(),
    )


def count_customer_pdf_files(customer_folder_path: Path) -> int:
    return len(collect_customer_pdf_files(customer_folder_path))


def count_pdf_pages(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as document:
        return document.page_count


def extract_pdf_text(pdf_path: Path) -> str:
    text_parts: list[str] = []

    with fitz.open(pdf_path) as document:
        for page in document:
            page_text = page.get_text("text", sort=True).strip()
            if page_text:
                text_parts.append(page_text)

    return "\n".join(text_parts)


def extract_first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    if match is None:
        return ""
    return match.group(0)


def normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalize_company_name_for_match(company_name: str) -> str:
    normalized_company_name = normalize_match_text(company_name)
    normalized_company_name = re.sub(
        r"(?:,?\s*)?co\.?,?\s*ltd\.?$",
        "",
        normalized_company_name,
        flags=re.IGNORECASE,
    ).strip()
    return normalized_company_name


def detect_company_name_exists(pdf_text: str, company_name: str) -> str:
    normalized_company_name = normalize_company_name_for_match(company_name)
    if not normalized_company_name:
        return "否"

    normalized_pdf_text = normalize_match_text(pdf_text)
    return "是" if normalized_company_name in normalized_pdf_text else "否"


def needs_model_recognition(pdf_text: str) -> bool:
    return MODEL_TRIGGER_PATTERN.search(pdf_text) is not None


def pdf_to_images_b64(file_path: Path) -> tuple[list[str], dict[str, object]]:
    image_urls: list[str] = []
    selected_pages: list[int] = []
    stats: dict[str, object] = {
        "total_pages": 0,
        "filtered_pages": 0,
        "selected_pages": [],
        "filter_time": 0.0,
        "convert_time": 0.0,
    }

    filter_started_at = time.time()
    with fitz.open(str(file_path)) as document:
        stats["total_pages"] = len(document)

        for page_index in range(len(document)):
            page = document.load_page(page_index)
            page_text = page.get_text("text", sort=True).upper()
            has_b00 = "B00" in page_text
            has_type = any(keyword in page_text for keyword in ["TYPE", "TYPE D'IMPOSITION", "ABGABENART"])
            if has_b00 and has_type:
                selected_pages.append(page_index)

        stats["filter_time"] = time.time() - filter_started_at
        stats["filtered_pages"] = len(selected_pages)
        stats["selected_pages"] = [page + 1 for page in selected_pages]

        convert_started_at = time.time()
        for page_index in selected_pages:
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(dpi=150)
            image_bytes = pixmap.tobytes("jpeg")
            image_url = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('utf-8')}"
            image_urls.append(image_url)
        stats["convert_time"] = time.time() - convert_started_at

    return image_urls, stats


def page_contains_all_keywords(page: fitz.Page, keywords: list[str]) -> bool:
    page_text = page.get_text("text", sort=True).lower()
    return all(keyword.lower() in page_text for keyword in keywords)


def pdf_to_images_b64_by_keywords(
    file_path: Path,
    keywords: list[str],
    dpi: int,
) -> tuple[list[str], dict[str, object]]:
    image_urls: list[str] = []
    matched_indices: list[int] = []
    stats: dict[str, object] = {
        "total_pages": 0,
        "filtered_pages": 0,
        "selected_pages": [],
        "filter_time": 0.0,
        "convert_time": 0.0,
    }

    filter_started_at = time.time()
    with fitz.open(str(file_path)) as document:
        stats["total_pages"] = len(document)

        for page_index in range(len(document)):
            page = document.load_page(page_index)
            if page_contains_all_keywords(page, keywords):
                matched_indices.append(page_index)

        stats["filter_time"] = time.time() - filter_started_at
        stats["filtered_pages"] = len(matched_indices)
        stats["selected_pages"] = [page + 1 for page in matched_indices]

        if not matched_indices:
            raise ValueError(f"未找到包含关键字 {keywords} 的页面")

        convert_started_at = time.time()
        for page_index in matched_indices:
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(dpi=dpi)
            image_bytes = pixmap.tobytes("jpeg")
            image_url = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('utf-8')}"
            image_urls.append(image_url)
        stats["convert_time"] = time.time() - convert_started_at

    return image_urls, stats


def parse_model_json_response(response_text: str) -> dict[str, object]:
    cleaned_text = response_text.strip()
    cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
    cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
    cleaned_text = cleaned_text.strip()

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError:
        match = MODEL_JSON_BLOCK_PATTERN.search(cleaned_text)
        if match is None:
            raise
        return json.loads(match.group(0))


def recognize_pdf_with_model(pdf_file_path: Path) -> dict[str, object]:
    image_urls, _stats = pdf_to_images_b64(pdf_file_path)
    if not image_urls:
        return {
            "original_amount": None,
            "document_type": None,
            "total_amount": None,
        }

    client = OpenAI(base_url=MODEL_BASE_URL, api_key=MODEL_API_KEY)
    user_content: list[dict[str, object]] = []
    for image_url in image_urls:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
        )
    user_content.append(
        {
            "type": "text",
            "text": "请从该德国海关单据PDF中提取所有B00税种的Base数值，按JSON格式输出。",
        }
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": MODEL_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        extra_body={"thinking": {"type": "disabled"}},
    )
    response_text = response.choices[0].message.content or ""
    parsed_response = parse_model_json_response(response_text)
    return {
        "original_amount": parsed_response.get("original_amount"),
        "document_type": parsed_response.get("document_type"),
        "total_amount": parsed_response.get("total_amount"),
    }


def recognize_uk_pdf_with_model_b(pdf_file_path: Path) -> dict[str, object]:
    image_urls, _stats = pdf_to_images_b64_by_keywords(
        pdf_file_path,
        keywords=UK_MODEL_B_KEYWORDS,
        dpi=120,
    )

    client = OpenAI(base_url=MODEL_BASE_URL, api_key=MODEL_API_KEY)
    user_content: list[dict[str, object]] = []
    for image_url in image_urls:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": image_url},
            }
        )
    user_content.append(
        {
            "type": "text",
            "text": "提取税务数据并输出JSON。",
        }
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": UK_MODEL_B_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        extra_body={"thinking": {"type": "disabled"}},
    )
    response_text = response.choices[0].message.content or ""
    parsed_response = parse_model_json_response(response_text)
    return {
        "tax_assessed": parsed_response.get("tax_assessed"),
        "payment_amount": parsed_response.get("payment_amount"),
    }


def normalize_model_field_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value or stripped_value.lower() == "null":
            return ""
        return stripped_value
    return str(value).strip()


def resolve_document_type(document_type_raw: object) -> str:
    normalized_value = normalize_model_field_value(document_type_raw)
    if not normalized_value:
        return "不确定"
    if normalized_value.casefold() in DEFERRED_DOCUMENT_TYPE_VALUES:
        return "递延"
    return "不确定"


def resolve_uk_payment_amount_document_type(payment_amount: object) -> str:
    normalized_value = normalize_model_field_value(payment_amount)
    if not normalized_value:
        return "不确定"

    normalized_numeric_value = normalized_value.replace(",", "")
    if normalized_numeric_value in {"0", "0.0", "0.00"}:
        return "递延"
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized_numeric_value):
        return "可抵扣"
    return "不确定"


def extract_uk_import_entry_amount_and_type(pdf_text: str) -> tuple[str, str]:
    b00_line_match = UK_IMPORT_ENTRY_B00_LINE_PATTERN.search(pdf_text)
    if b00_line_match is None:
        b00_line_match = UK_IMPORT_ENTRY_B00_LINE_FALLBACK_PATTERN.search(pdf_text)
    if b00_line_match is None:
        return "", "不确定"

    b00_line = b00_line_match.group(0)
    parts = [part for part in re.split(r"\s+", b00_line.strip()) if part]
    if len(parts) < 3:
        return "", "不确定"

    original_amount = parts[1]
    tax_payable = normalize_model_field_value(parts[2]).replace(",", "")
    if tax_payable in {"0", "0.0", "0.00"}:
        return original_amount, "递延"
    return original_amount, "可抵扣"


def extract_uk_vat_amount_and_type(pdf_text: str) -> tuple[str, str]:
    target_line_match = UK_TOTAL_VAT_LINE_PATTERN.search(pdf_text)
    original_amount = ""
    if target_line_match is not None:
        target_line = target_line_match.group(0)
        _, _, amount_part = target_line.partition(":")
        original_amount = amount_part.strip().replace("£", "").replace("￡", "").strip()

    normalized_pdf_text = pdf_text.casefold()
    if "postponed" in normalized_pdf_text:
        return original_amount, "递延"
    if "c79" in normalized_pdf_text:
        return original_amount, "可抵扣"
    return original_amount, "不确定"


def build_missing_customer_summary_row(customer_id: str) -> list[str]:
    row = [""] * len(SUMMARY_HEADERS)
    row[SUMMARY_CUSTOMER_COLUMN_INDEX - 1] = customer_id
    row[SUMMARY_STATUS_COLUMN_INDEX - 1] = MISSING_CUSTOMER_MESSAGE
    return row


def build_zero_pdf_summary_row(customer_id: str, customer_record: dict[str, str], pdf_count: int) -> list[str]:
    return [
        customer_record["agent"],
        customer_id,
        "",
        customer_record["company_name_cn"],
        customer_record["declaration_period"],
        customer_record["declaration_method"],
        customer_record["tax_number"],
        str(pdf_count),
        "",
        "",
        "",
        "",
        ZERO_PDF_MESSAGE,
    ]


def build_customer_summary_row(
    customer_id: str,
    customer_record: dict[str, str],
    pdf_count: int,
    success_count: int,
    failure_count: int,
) -> list[str]:
    return [
        customer_record["agent"],
        customer_id,
        customer_record["declaration_country"],
        customer_record["company_name_cn"],
        customer_record["declaration_period"],
        customer_record["declaration_method"],
        customer_record["tax_number"],
        str(pdf_count),
        str(success_count),
        str(failure_count),
        "",
        "",
        "",
    ]


def build_result_output_path(customer_folder_path: Path, customer_id: str) -> Path:
    return customer_folder_path / f"{customer_id}{RESULT_FILE_SUFFIX}"


def build_result_row(
    customer_id: str,
    country: str,
    company_name: str,
    declaration_period: str,
    tax_number: str,
    pdf_file_name: str,
    document_date: str = "",
    company_name_exists: str = "",
    mrn_number: str = "",
    original_amount: str = "",
    document_type: str = "",
    deferred_document: str = "",
    deductible_document: str = "",
    error_message: str = "",
) -> list[str]:
    return [
        customer_id,
        country,
        company_name,
        declaration_period,
        tax_number,
        pdf_file_name,
        document_date,
        company_name_exists,
        mrn_number,
        original_amount,
        document_type,
        deferred_document,
        deductible_document,
        error_message,
    ]


def process_gt_pdf(
    customer_id: str,
    customer_record: dict[str, str],
    pdf_file_path: Path,
) -> list[str]:
    pdf_text = extract_pdf_text(pdf_file_path)
    original_amount = ""
    document_type = ""
    error_message = ""
    mrn_number = extract_first_match(UK_MRN_PATTERN, pdf_text)
    document_date = extract_first_match(UK_DATE_DASH_PATTERN, pdf_text)
    if not document_date:
        document_date = extract_first_match(UK_DATE_SLASH_PATTERN, pdf_text)
    company_name_exists = detect_company_name_exists(pdf_text, customer_record["company_name_en"])
    normalized_pdf_text = pdf_text.casefold()

    if "import entry acceptance advice" in normalized_pdf_text:
        error_message = UK_IMPORT_ENTRY_MESSAGE
        original_amount, document_type = extract_uk_import_entry_amount_and_type(pdf_text)
    elif "vat registration number" in normalized_pdf_text:
        error_message = UK_VAT_REGISTRATION_MESSAGE
        original_amount, document_type = extract_uk_vat_amount_and_type(pdf_text)
    else:
        error_message = UK_MODEL_B_MESSAGE
        model_result = recognize_uk_pdf_with_model_b(pdf_file_path)
        original_amount = normalize_model_field_value(model_result.get("tax_assessed"))
        payment_amount = model_result.get("payment_amount")
        document_type = resolve_uk_payment_amount_document_type(payment_amount)

    return build_result_row(
        customer_id=customer_id,
        country=customer_record["declaration_country"],
        company_name=customer_record["company_name_en"],
        declaration_period=customer_record["declaration_period"],
        tax_number=customer_record["tax_number"],
        pdf_file_name=pdf_file_path.name,
        document_date=document_date,
        company_name_exists=company_name_exists,
        mrn_number=mrn_number,
        original_amount=original_amount,
        document_type=document_type,
        error_message=error_message,
    )


def process_dt_pdf(
    customer_id: str,
    customer_record: dict[str, str],
    pdf_file_path: Path,
) -> list[str]:
    pdf_text = extract_pdf_text(pdf_file_path)
    original_amount = ""
    document_type = ""
    processed_amount = ""
    deferred_document = ""
    deductible_document = ""
    error_message = ""
    mrn_number = extract_first_match(UK_MRN_PATTERN, pdf_text)
    document_date = extract_first_match(UK_DATE_DASH_PATTERN, pdf_text)
    if not document_date:
        document_date = extract_first_match(UK_DATE_SLASH_PATTERN, pdf_text)
    company_name_exists = detect_company_name_exists(pdf_text, customer_record["company_name_en"])

    if needs_model_recognition(pdf_text):
        error_message = MODEL_RECOGNITION_MESSAGE
        model_result = recognize_pdf_with_model(pdf_file_path)
        original_amount = normalize_model_field_value(model_result.get("original_amount"))
        document_type_raw = model_result.get("document_type")
        processed_amount = normalize_model_field_value(model_result.get("total_amount"))
        document_type = resolve_document_type(document_type_raw)
        if document_type == "递延":
            deferred_document = processed_amount

    return build_result_row(
        customer_id=customer_id,
        country=customer_record["declaration_country"],
        company_name=customer_record["company_name_en"],
        declaration_period=customer_record["declaration_period"],
        tax_number=customer_record["tax_number"],
        pdf_file_name=pdf_file_path.name,
        document_date=document_date,
        company_name_exists=company_name_exists,
        mrn_number=mrn_number,
        original_amount=original_amount,
        document_type=document_type,
        deferred_document=deferred_document,
        deductible_document=deductible_document,
        error_message=error_message,
    )


def process_customer_folders(
    customer_folders: list[tuple[str, Path]],
    customer_records: dict[str, dict[str, str]],
) -> tuple[list[list[str]], int, int]:
    rows = [SUMMARY_HEADERS]
    missing_customer_count = 0
    zero_pdf_count = 0

    for customer_id, customer_folder_path in customer_folders:
        customer_record = customer_records.get(customer_id)
        if customer_record is None:
            rows.append(build_missing_customer_summary_row(customer_id))
            missing_customer_count += 1
            continue

        pdf_file_paths = collect_customer_pdf_files(customer_folder_path)
        pdf_count = len(pdf_file_paths)
        if pdf_count == 0:
            rows.append(build_zero_pdf_summary_row(customer_id, customer_record, pdf_count))
            zero_pdf_count += 1
            continue

        result_rows = [RESULT_HEADERS]
        success_count = 0
        failure_count = 0
        customer_id_upper = customer_id.upper()

        for pdf_file_path in pdf_file_paths:
            try:
                pdf_page_count = count_pdf_pages(pdf_file_path)
            except Exception as error:
                result_rows.append(
                    build_result_row(
                        customer_id=customer_id,
                        country=customer_record["declaration_country"],
                        company_name=customer_record["company_name_en"],
                        declaration_period=customer_record["declaration_period"],
                        tax_number=customer_record["tax_number"],
                        pdf_file_name=pdf_file_path.name,
                        error_message=str(error),
                    )
                )
                failure_count += 1
                continue

            if pdf_page_count >= PDF_PAGE_LIMIT:
                result_rows.append(
                    build_result_row(
                        customer_id=customer_id,
                        country="",
                        company_name=customer_record["company_name_en"],
                        declaration_period=customer_record["declaration_period"],
                        tax_number=customer_record["tax_number"],
                        pdf_file_name=pdf_file_path.name,
                        error_message=PDF_PAGE_LIMIT_MESSAGE,
                    )
                )
                failure_count += 1
                continue

            if "GT" not in customer_id_upper and "DT" not in customer_id_upper:
                result_rows.append(
                    build_result_row(
                        customer_id=customer_id,
                        country=customer_record["declaration_country"],
                        company_name=customer_record["company_name_en"],
                        declaration_period=customer_record["declaration_period"],
                        tax_number=customer_record["tax_number"],
                        pdf_file_name=pdf_file_path.name,
                        error_message=INVALID_COUNTRY_MESSAGE,
                    )
                )
                failure_count += 1
                continue

            if "GT" in customer_id_upper:
                try:
                    result_rows.append(process_gt_pdf(customer_id, customer_record, pdf_file_path))
                    success_count += 1
                except Exception as error:
                    result_rows.append(
                        build_result_row(
                            customer_id=customer_id,
                            country=customer_record["declaration_country"],
                            company_name=customer_record["company_name_en"],
                            declaration_period=customer_record["declaration_period"],
                            tax_number=customer_record["tax_number"],
                            pdf_file_name=pdf_file_path.name,
                            error_message=str(error),
                        )
                    )
                    failure_count += 1
                continue

            if "DT" in customer_id_upper:
                try:
                    result_rows.append(process_dt_pdf(customer_id, customer_record, pdf_file_path))
                    success_count += 1
                except Exception as error:
                    result_rows.append(
                        build_result_row(
                            customer_id=customer_id,
                            country=customer_record["declaration_country"],
                            company_name=customer_record["company_name_en"],
                            declaration_period=customer_record["declaration_period"],
                            tax_number=customer_record["tax_number"],
                            pdf_file_name=pdf_file_path.name,
                            error_message=str(error),
                        )
                    )
                    failure_count += 1
                continue

        write_workbook(
            build_result_output_path(customer_folder_path, customer_id),
            RESULT_SHEET_NAME,
            result_rows,
        )
        rows.append(build_customer_summary_row(customer_id, customer_record, pdf_count, success_count, failure_count))

    return rows, missing_customer_count, zero_pdf_count


def initialize_summary_workbook(folder_path: Path) -> Path:
    summary_path = folder_path / SUMMARY_FILE_NAME
    return summary_path


def main() -> int:
    print("[CONSULT] 递延税发票识别任务启动中...")

    try:
        config = load_config()
        folder_path, list_excel_path = validate_config(config)
        summary_path = initialize_summary_workbook(folder_path)
        list_customer_records = extract_list_customer_records(list_excel_path)
        customer_folders = collect_customer_folders(folder_path)
        summary_rows, missing_customer_count, zero_pdf_count = process_customer_folders(
            customer_folders,
            list_customer_records,
        )
        write_summary_workbook(summary_path, summary_rows)
    except Exception as error:
        print(f"[CONSULT] 执行失败: {error}")
        return 1

    print(f"[CONSULT] 递延税单据总文件夹: {folder_path}")
    print(f"[CONSULT] Excel 清单文件路径: {list_excel_path}")
    print(f"[CONSULT] 客户号文件夹数量: {len(customer_folders)}")
    print(f"[CONSULT] 总清单客户号数量: {len(list_customer_records)}")
    print(f"[CONSULT] 未在总清单命中的客户号数量: {missing_customer_count}")
    print(f"[CONSULT] 发票个数为0的客户号数量: {zero_pdf_count}")
    print(f"[CONSULT] 汇总表已更新: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
