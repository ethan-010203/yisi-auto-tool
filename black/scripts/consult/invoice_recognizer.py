from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import fitz


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


def process_uk_pdf(
    customer_id: str,
    customer_record: dict[str, str],
    pdf_file_path: Path,
) -> list[str]:
    pdf_text = extract_pdf_text(pdf_file_path)
    original_amount = ""
    document_type = ""
    processed_amount = ""
    mrn_number = extract_first_match(UK_MRN_PATTERN, pdf_text)
    document_date = extract_first_match(UK_DATE_DASH_PATTERN, pdf_text)
    if not document_date:
        document_date = extract_first_match(UK_DATE_SLASH_PATTERN, pdf_text)

    return build_result_row(
        customer_id=customer_id,
        country=customer_record["declaration_country"],
        company_name=customer_record["company_name_en"],
        declaration_period=customer_record["declaration_period"],
        tax_number=customer_record["tax_number"],
        pdf_file_name=pdf_file_path.name,
        document_date=document_date,
        mrn_number=mrn_number,
        original_amount=original_amount,
        document_type=document_type,
        deferred_document=processed_amount,
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
                    result_rows.append(process_uk_pdf(customer_id, customer_record, pdf_file_path))
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
