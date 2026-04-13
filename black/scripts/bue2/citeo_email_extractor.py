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

    print(f"[BUE2] 连接邮箱: {email}", file=sys.stderr)
    print(f"[BUE2] 选择文件夹: {folder}", file=sys.stderr)

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
        print(f"[BUE2] 邮箱登录成功", file=sys.stderr)
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
        print(f"[BUE2] 文件夹选择成功", file=sys.stderr)
    except Exception as e:
        mail.logout()
        raise Exception(f"选择文件夹失败: {str(e)}")

    # 搜索邮件（获取所有邮件，然后在代码中筛选主题）
    try:
        _, data = mail.search(None, "ALL")
        email_ids = data[0].split()
        print(f"[BUE2] 找到 {len(email_ids)} 封邮件", file=sys.stderr)
    except Exception as e:
        mail.logout()
        raise Exception(f"搜索邮件失败: {str(e)}")

    # 只取最近的max_emails封
    email_ids = email_ids[-max_emails:] if len(email_ids) > max_emails else email_ids
    print(f"[BUE2] 处理最近 {len(email_ids)} 封邮件", file=sys.stderr)

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

            print(f"[BUE2] 邮件[{idx+1}]主题: {subject_str[:100]}", file=sys.stderr)

            # 筛选主题包含'Citeo - Réf. client n°'的邮件
            if subject_pattern.search(subject_str):
                print(f"[BUE2] ✓ 匹配邮件: {subject_str[:80]}...", file=sys.stderr)
                # 提取会员号
                match = member_id_pattern.search(subject_str)
                if match:
                    member_id = match.group(1)
                    member_ids.append(member_id)
                    print(f"[BUE2] ✓ 提取会员号: {member_id}", file=sys.stderr)
                else:
                    print(f"[BUE2] ✗ 未找到会员号", file=sys.stderr)
        except Exception as e:
            print(f"[BUE2] 处理邮件[{idx+1}]失败: {str(e)}", file=sys.stderr)
            continue

    mail.logout()
    print(f"[BUE2] 共提取 {len(member_ids)} 个会员号", file=sys.stderr)
    return member_ids


def save_to_excel(member_ids: list[str], output_path: Path) -> str:
    """将会员号保存到Excel（无表头，直接A列写入）"""
    try:
        import pandas as pd

        # 确保输出目录存在
        output_path.mkdir(parents=True, exist_ok=True)

        # 创建DataFrame（无表头）
        df = pd.DataFrame(member_ids, columns=[None])

        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_file = output_path / f"注销成功名单_{timestamp}.xlsx"

        # 保存到Excel（无表头无索引）
        df.to_excel(excel_file, index=False, header=False, sheet_name="会员号")

        return str(excel_file)

    except ImportError:
        raise ImportError("缺少必要的库，请安装: pip install pandas openpyxl")
    except Exception as e:
        raise Exception(f"Excel保存失败: {str(e)}")


def main() -> int:
    error_summary = None
    
    print("[BUE2] FR-Citeo-注销成功名单邮件提取任务启动...", file=sys.stderr)

    # 1. 从配置读取数据
    try:
        print("[BUE2] 正在读取配置...", file=sys.stderr)
        config = load_config()
        print(f"[BUE2] 配置读取完成: 邮箱={config.get('email')}", file=sys.stderr)
    except Exception as error:
        error_summary = f"配置读取失败: {error}"
        print(f"[BUE2] {error_summary}", file=sys.stderr)
        traceback.print_exc()
        print(error_summary)  # 输出到stdout供复制
        return 1

    # 2&3. 从邮件提取会员号
    try:
        print("[BUE2] 正在连接邮箱并提取会员号...", file=sys.stderr)
        member_ids = extract_member_ids_from_emails(config)
        print(f"[BUE2] 提取到 {len(member_ids)} 个会员号", file=sys.stderr)
    except Exception as error:
        error_summary = f"邮件处理失败: {error}"
        print(f"[BUE2] {error_summary}", file=sys.stderr)
        traceback.print_exc()
        print(error_summary)  # 输出到stdout供复制
        return 1

    # 4. 保存到Excel
    try:
        output_path = get_output_path()
        print(f"[BUE2] 正在保存到Excel...", file=sys.stderr)
        excel_file = save_to_excel(member_ids, output_path)
        print(f"[BUE2] Excel文件已创建: {excel_file}", file=sys.stderr)

        # 输出到stdout供前端日志显示
        print(f"任务执行完成")
        print(f"提取会员号数量: {len(member_ids)}")
        print(f"Excel文件路径: {excel_file}")
        return 0

    except Exception as error:
        error_summary = f"Excel保存失败: {error}"
        print(f"[BUE2] {error_summary}", file=sys.stderr)
        traceback.print_exc()
        print(error_summary)  # 输出到stdout供复制
        return 1


if __name__ == "__main__":
    sys.exit(main())
