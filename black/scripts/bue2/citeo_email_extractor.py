from __future__ import annotations

import imaplib
import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from email import message_from_bytes
from email.header import decode_header
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def log_info(message: str) -> None:
    """输出持续累积的运行日志。"""
    print(f"[BUE2] {message}", flush=True)


def log_error(message: str) -> None:
    """输出筛选后的错误摘要。"""
    print(f"[BUE2] {message}", file=sys.stderr, flush=True)


def load_config() -> dict:
    """从配置文件中读取邮件配置"""
    config_path = Path(__file__).parent.parent.parent / "configs" / "BUE2_citeo_email_extractor.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 硬编码邮箱账号和授权码
    config["email"] = "infoeuvat@163.com"
    config["authCode"] = "FPdskjj8kTW5Fu4q"

    return config


def get_output_path() -> Path:
    """获取输出路径，从环境变量或默认路径"""
    network_path = os.environ.get("YISI_DEPT_NETWORK_PATH", "").strip()
    if not network_path:
        raise ValueError("未配置部门局域网路径，请在前端配置部门网络路径")
    return Path(network_path) / "FR-Citeo-注销成功名单邮件提取"


def extract_member_ids_from_emails(config: dict) -> list[str]:
    """从邮件中提取会员号"""
    email = config.get("email", "")
    auth_code = config.get("authCode", "")
    folder = config.get("selectedFolder", "INBOX")
    max_emails = config.get("maxEmails", 50)

    if not email or not auth_code:
        raise ValueError("邮箱账号或授权码未配置")

    log_info(f"连接邮箱: {email}")
    log_info(f"选择文件夹: {folder}")

    # 连接163邮箱IMAP服务器
    try:
        mail = imaplib.IMAP4_SSL("imap.163.com", 993)
        # 163邮箱需要在登录前发送ID命令解决"Unsafe Login"问题
        tag = mail._new_tag()
        mail.send(f"{tag.decode()} ID (\"name\" \"citeo_extractor\" \"version\" \"1.0\")\r\n".encode())
        while True:
            line = mail._get_response()
            if line.startswith(tag):
                break
        mail.login(email, auth_code)
        log_info("邮箱登录成功")
    except imaplib.IMAP4.error as e:
        error_msg = str(e).lower()
        if "login error" in error_msg or "password error" in error_msg or "authentication failed" in error_msg:
            raise Exception(
                f"邮箱登录失败: 账号或授权码错误。\n"
                f"请检查:\n"
                f"1. 邮箱账号是否正确: {email}\n"
                f"2. 授权码是否有效（注意：不是登录密码，是IMAP授权码）\n"
                f"3. 163邮箱设置中是否已开启IMAP服务"
            )
        elif "not enabled" in error_msg:
            raise Exception("邮箱登录失败: IMAP服务未开启，请前往163邮箱设置开启IMAP")
        else:
            raise Exception(f"邮箱登录失败: {str(e)}")

    # 选择文件夹（不标记为已读）
    try:
        # 对包含特殊字符的文件夹名加引号
        folder_quoted = f'"{folder}"' if not folder.startswith('"') else folder
        status, response = mail.select(folder_quoted, readonly=True)
        if status != "OK":
            raise Exception(f"无法选择文件夹: {folder}, 响应: {response}")
        log_info("文件夹选择成功")
    except Exception as e:
        mail.logout()
        raise Exception(f"选择文件夹失败: {str(e)}")

    # 搜索邮件（获取所有邮件，然后在代码中筛选主题）
    try:
        _, data = mail.search(None, "ALL")
        email_ids = data[0].split()
        log_info(f"找到 {len(email_ids)} 封邮件")
    except Exception as e:
        mail.logout()
        raise Exception(f"搜索邮件失败: {str(e)}")

    # 只取最近的max_emails封
    email_ids = email_ids[-max_emails:] if len(email_ids) > max_emails else email_ids
    log_info(f"处理最近 {len(email_ids)} 封邮件")

    member_ids = []
    # 使用更宽松的正则，处理n°字符编码问题
    subject_pattern = re.compile(r"Citeo.*Réf.*client.*n[°º]", re.IGNORECASE)
    member_id_pattern = re.compile(r"(\d+)")

    for idx, eid in enumerate(email_ids):
        try:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            raw_email = msg_data[0][1]

            # 解析邮件内容获取主题
            msg = message_from_bytes(raw_email)
            subject = msg.get("Subject", "")

            # 解码主题（处理可能的编码问题）
            decoded_parts = decode_header(subject)
            subject_str = ""
            for part, charset in decoded_parts:
                if isinstance(part, bytes):
                    subject_str += part.decode(charset or "utf-8", errors="ignore")
                else:
                    subject_str += part

            log_info(f"邮件[{idx+1}]主题: {subject_str[:100]}")

            # 筛选主题包含'Citeo - Réf. client n°'的邮件
            if subject_pattern.search(subject_str):
                log_info(f"✓ 匹配邮件: {subject_str[:80]}...")
                # 提取会员号
                match = member_id_pattern.search(subject_str)
                if match:
                    member_id = match.group(1)
                    member_ids.append(member_id)
                    log_info(f"✓ 提取会员号: {member_id}")
                else:
                    log_info("✗ 未找到会员号")
        except Exception as e:
            log_info(f"处理邮件[{idx+1}]失败: {str(e)}")
            continue

    mail.logout()
    log_info(f"共提取 {len(member_ids)} 个会员号")
    return member_ids


def save_to_excel(member_ids: list[str], output_path: Path) -> str:
    """将会员号保存到Excel（无表头，直接A列写入）。"""
    try:
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_file = output_path / f"注销成功名单_{timestamp}.xlsx"

        rows_xml = []
        for row_index, member_id in enumerate(member_ids, start=1):
            cell_value = escape(str(member_id))
            rows_xml.append(
                f'<row r="{row_index}">'
                f'<c r="A{row_index}" t="inlineStr"><is><t>{cell_value}</t></is></c>'
                f"</row>"
            )

        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            f"{''.join(rows_xml)}"
            "</sheetData>"
            "</worksheet>"
        )
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="会员号" sheetId="1" r:id="rId1"/></sheets>'
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
            "</Types>"
        )
        root_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )
        workbook_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )

        with ZipFile(excel_file, "w", compression=ZIP_DEFLATED) as workbook:
            workbook.writestr("[Content_Types].xml", content_types_xml)
            workbook.writestr("_rels/.rels", root_rels_xml)
            workbook.writestr("xl/workbook.xml", workbook_xml)
            workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
            workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        return str(excel_file)
    except Exception as e:
        raise Exception(f"Excel保存失败: {str(e)}")


def main() -> int:
    error_summary = None
    
    log_info("FR-Citeo-注销成功名单邮件提取任务启动...")

    # 1. 从配置读取数据
    try:
        log_info("正在读取配置...")
        config = load_config()
        log_info(f"配置读取完成: 邮箱={config.get('email')}")
    except Exception as error:
        error_summary = f"配置读取失败: {error}"
        log_info(error_summary)
        log_error(error_summary)
        traceback.print_exc(file=sys.stdout)
        return 1

    # 2&3. 从邮件提取会员号
    try:
        log_info("正在连接邮箱并提取会员号...")
        member_ids = extract_member_ids_from_emails(config)
        log_info(f"提取到 {len(member_ids)} 个会员号")
    except Exception as error:
        error_summary = f"邮件处理失败: {error}"
        log_info(error_summary)
        log_error(error_summary)
        traceback.print_exc(file=sys.stdout)
        return 1

    # 4. 保存到Excel
    try:
        output_path = get_output_path()
        log_info("正在保存到Excel...")
        excel_file = save_to_excel(member_ids, output_path)
        log_info(f"Excel文件已创建: {excel_file}")

        # 输出到stdout供前端日志显示
        print(f"任务执行完成")
        print(f"提取会员号数量: {len(member_ids)}")
        print(f"Excel文件路径: {excel_file}")
        return 0

    except Exception as error:
        error_summary = f"Excel保存失败: {error}"
        log_info(error_summary)
        log_error(error_summary)
        traceback.print_exc(file=sys.stdout)
        return 1


if __name__ == "__main__":
    sys.exit(main())
