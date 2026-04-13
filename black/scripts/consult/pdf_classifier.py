from __future__ import annotations

import json
import os
import re
import sys
import shutil
from pathlib import Path
from typing import Dict, List, Tuple


CONFIG_FILE = Path(__file__).resolve().parents[2] / "configs" / "CONSULT_pdf_classifier.json"

# 预定义的分类规则（基于关键词匹配）
CLASSIFICATION_RULES = {
    "合同": ["contract", "agreement", "合同", "协议", "terms", "条款"],
    "发票": ["invoice", "receipt", "发票", "收据", "billing", "账单"],
    "报告": ["report", "analysis", "报告", "分析", "summary", "总结"],
    "证书": ["certificate", "license", "证书", "执照", "certification", "资质"],
    "其他": []
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("配置文件不存在，请先在前端完成配置保存。")

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def validate_config(config: dict) -> Tuple[str, str]:
    source_folder = (config.get("folderPath") or "").strip()
    output_folder = (config.get("outputPath") or "").strip()

    if not source_folder:
        raise ValueError("缺少源PDF文件夹配置。")

    if not output_folder:
        raise ValueError("缺少输出文件夹配置。")

    return source_folder, output_folder


def extract_text_from_pdf(pdf_path: Path) -> str:
    """从PDF中提取文本"""
    text = ""
    
    # 尝试使用PyPDF2
    try:
        import PyPDF2
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception:
        pass
    
    # 如果PyPDF2失败或未安装，尝试pdfplumber
    if not text.strip():
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception:
            pass
    
    return text


def classify_pdf(text: str, filename: str) -> str:
    """基于文本内容分类PDF"""
    text_lower = text.lower()
    filename_lower = filename.lower()
    
    scores = {}
    
    for category, keywords in CLASSIFICATION_RULES.items():
        if category == "其他":
            continue
            
        score = 0
        for keyword in keywords:
            # 在文本中查找关键词
            score += len(re.findall(r'\b' + re.escape(keyword) + r'\b', text_lower, re.IGNORECASE))
            # 在文件名中查找关键词（权重更高）
            if keyword in filename_lower:
                score += 3
        
        scores[category] = score
    
    # 如果没有匹配到任何类别，归为"其他"
    if not scores or max(scores.values()) == 0:
        return "其他"
    
    # 返回得分最高的类别
    return max(scores, key=scores.get)


def process_pdfs(source_folder: str, output_folder: str) -> Dict:
    """处理文件夹中的所有PDF文件"""
    source_path = Path(source_folder)
    output_path = Path(output_folder)
    
    if not source_path.exists():
        raise FileNotFoundError(f"源文件夹不存在: {source_folder}")
    
    # 创建输出文件夹
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 获取所有PDF文件
    pdf_files = list(source_path.glob("*.pdf")) + list(source_path.glob("*.PDF"))
    
    if not pdf_files:
        print("[CONSULT] 未找到PDF文件")
        return {"total": 0, "classified": {}, "errors": []}
    
    print(f"[CONSULT] 找到 {len(pdf_files)} 个PDF文件")
    
    classification_results = {cat: [] for cat in CLASSIFICATION_RULES.keys()}
    errors = []
    
    for pdf_file in pdf_files:
        try:
            print(f"[CONSULT] 处理: {pdf_file.name}")
            
            # 提取文本
            text = extract_text_from_pdf(pdf_file)
            
            # 分类
            category = classify_pdf(text, pdf_file.name)
            classification_results[category].append(pdf_file.name)
            
            # 创建分类子文件夹
            category_folder = output_path / category
            category_folder.mkdir(exist_ok=True)
            
            # 复制文件到对应分类文件夹
            dest_file = category_folder / pdf_file.name
            counter = 1
            original_dest = dest_file
            while dest_file.exists():
                stem = original_dest.stem
                suffix = original_dest.suffix
                dest_file = category_folder / f"{stem}_{counter}{suffix}"
                counter += 1
            
            shutil.copy2(pdf_file, dest_file)
            
            # 同时保存提取的文本（可选）
            if text.strip():
                text_file = dest_file.with_suffix('.txt')
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(f"源文件: {pdf_file.name}\n")
                    f.write(f"分类: {category}\n")
                    f.write(f"{'='*50}\n\n")
                    f.write(text)
            
            print(f"[CONSULT]   → 分类为: {category}")
            
        except Exception as e:
            error_msg = f"处理 {pdf_file.name} 时出错: {str(e)}"
            print(f"[CONSULT] {error_msg}")
            errors.append(error_msg)
    
    # 输出统计结果
    print(f"\n[CONSULT] 分类完成统计:")
    for category, files in classification_results.items():
        if files:
            print(f"[CONSULT]   {category}: {len(files)} 个文件")
    
    if errors:
        print(f"[CONSULT]   错误: {len(errors)} 个")
    
    return {
        "total": len(pdf_files),
        "classified": {k: len(v) for k, v in classification_results.items() if v},
        "errors": errors
    }


def main() -> int:
    print("[CONSULT] PDF自动分类任务启动中...")

    try:
        config = load_config()
        source_folder, output_folder = validate_config(config)
    except Exception as error:
        print(f"[CONSULT] 配置检查失败: {error}")
        return 1

    print(f"[CONSULT] 源文件夹: {source_folder}")
    print(f"[CONSULT] 输出文件夹: {output_folder}")
    
    # 检查PDF处理库是否可用
    try:
        import PyPDF2
        print("[CONSULT] PDF处理库: PyPDF2")
    except ImportError:
        try:
            import pdfplumber
            print("[CONSULT] PDF处理库: pdfplumber")
        except ImportError:
            print("[CONSULT] 错误: 未安装PDF处理库，请先安装 PyPDF2 或 pdfplumber")
            print("[CONSULT] 运行: pip install PyPDF2")
            return 1
    
    print("[CONSULT] 开始扫描和分类PDF文件...")
    print()
    
    try:
        result = process_pdfs(source_folder, output_folder)
        
        if result["total"] == 0:
            print("[CONSULT] 未找到PDF文件，任务结束")
            return 0
        
        if result["errors"]:
            print(f"\n[CONSULT] 任务完成，但有 {len(result['errors'])} 个错误")
            return 0
        
        print("\n[CONSULT] 任务成功完成")
        return 0
        
    except Exception as e:
        print(f"[CONSULT] 处理过程中出错: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
