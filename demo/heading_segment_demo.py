"""
Gradio Demo 应用 - Markdown 文档切分测试
支持用户选择 md 文件，左右两栏展示原文档和切分后的分块内容
支持滑块设置文档切分长度，使用颜色背景区分分块
支持切换展示 JSON 或渲染回 Markdown
"""

import json
import re
import sys
import time
from pathlib import Path

import gradio as gr

# Add parent directory to path to import services module
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.heading_segment import ChunkType, HeadingSegmenter

# 配置常量
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_PREVIEW_CHUNKS = 500  # 最多显示500个分块的详细信息

# 分块类型对应的颜色配置（较浅的背景色，适合文本渲染）
CHUNK_COLORS = {
    ChunkType.TEXT: {
        "bg": "#e8f5e9",
        "border": "#a5d6a7",
        "text": "#2e7d32",
        "hover": "#c8e6c9",
    },
    ChunkType.IMAGE: {
        "bg": "#e3f2fd",
        "border": "#90caf9",
        "text": "#1565c0",
        "hover": "#bbdefb",
    },
    ChunkType.TABLE: {
        "bg": "#fff3e0",
        "border": "#ffcc80",
        "text": "#ef6c00",
        "hover": "#ffe0b2",
    },
    ChunkType.CODE: {
        "bg": "#f3e5f5",
        "border": "#ce93d8",
        "text": "#7b1fa2",
        "hover": "#e1bee7",
    },
    ChunkType.HEADER: {
        "bg": "#fce4ec",
        "border": "#f48fb1",
        "text": "#c2185b",
        "hover": "#f8bbd0",
    },
    ChunkType.HTML_IMAGE: {
        "bg": "#e8eaf6",
        "border": "#9fa8da",
        "text": "#283593",
        "hover": "#c5cae9",
    },
    ChunkType.HTML_TABLE: {
        "bg": "#fff8e1",
        "border": "#ffe082",
        "text": "#f57f17",
        "hover": "#ffecb3",
    },
    ChunkType.HTML_CODE: {
        "bg": "#efebe9",
        "border": "#bcaaa4",
        "text": "#4e342e",
        "hover": "#d7ccc8",
    },
}


def format_chunk_type(chunk_type: str) -> str:
    """为不同的分块类型添加标识"""
    type_icons = {
        ChunkType.TEXT: "📝",
        ChunkType.IMAGE: "🖼️",
        ChunkType.TABLE: "📊",
        ChunkType.CODE: "💻",
        ChunkType.HEADER: "📌",
        ChunkType.HTML_IMAGE: "🖼️",
        ChunkType.HTML_TABLE: "📊",
        ChunkType.HTML_CODE: "💻",
    }
    icon = type_icons.get(chunk_type, "📄")
    return f"{icon} {chunk_type.upper()}"


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def get_chunk_style(chunk_type: str) -> dict:
    """获取分块类型的颜色样式"""
    return CHUNK_COLORS.get(
        chunk_type,
        {"bg": "#f5f5f5", "border": "#bdbdbd", "text": "#616161", "hover": "#eeeeee"},
    )


def escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def markdown_to_html_preview(markdown_text: str) -> str:
    """简单的 Markdown 转 HTML 预览（用于显示分块内容）"""
    # 基本的 Markdown 转换
    html = markdown_text

    # 转义 HTML 特殊字符
    html = escape_html(html)

    # 转换标题
    html = re.sub(r"^######\s+(.+)$", r"<h6>\1</h6>", html, flags=re.MULTILINE)
    html = re.sub(r"^#####\s+(.+)$", r"<h5>\1</h5>", html, flags=re.MULTILINE)
    html = re.sub(r"^####\s+(.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^###\s+(.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^##\s+(.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^#\s+(.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

    # 转换粗体和斜体
    html = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", html)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"___(.+?)___", r"<strong><em>\1</em></strong>", html)
    html = re.sub(r"__(.+?)__", r"<strong>\1</strong>", html)
    html = re.sub(r"_(.+?)_", r"<em>\1</em>", html)

    # 转换行内代码
    html = re.sub(
        r"`(.+?)`",
        r'<code style="background: rgba(0,0,0,0.05); padding: 2px 6px; border-radius: 3px; font-family: monospace;">\1</code>',
        html,
    )

    # 转换代码块
    html = re.sub(
        r"```(\w+)?\n(.*?)```",
        r'<pre style="background: #f8f9fa; padding: 12px; border-radius: 5px; overflow-x: auto;"><code>\2</code></pre>',
        html,
        flags=re.DOTALL,
    )

    # 转换链接
    html = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" style="color: #1976d2;">\1</a>',
        html,
    )

    # 转换图片
    html = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        r'<img src="\2" alt="\1" style="max-width: 100%; height: auto;" />',
        html,
    )

    # 转换换行
    html = html.replace("\n", "<br>")

    return html


def split_markdown_formatted(
    file,
    max_segment_length: int = 500,
    heading_level_limit: int = 6,
    progress=gr.Progress(),
) -> tuple[str, str, str]:
    """
    处理上传的 md 文件，返回原文档、JSON 格式和 Markdown 渲染

    :param file: 上传的文件
    :param max_segment_length: 文本分块最大长度
    :param heading_level_limit: 标题切分等级限制（1-6）
    """
    if file is None:
        return "请选择一个 Markdown 文件", "", "等待上传文件..."

    try:
        # 第一步：读取文件并检查大小
        progress(0.1, desc="正在读取文件...")
        file_size = file.size if hasattr(file, "size") else 0

        with open(file.name, "r", encoding="utf-8") as f:
            md_content = f.read()

        actual_size = len(md_content.encode("utf-8"))

        # 文件过大警告
        if actual_size > MAX_FILE_SIZE:
            warning = (
                f"\n\n⚠️ 警告: 文件大小 {format_file_size(actual_size)} 超过建议大小 "
                f"{format_file_size(MAX_FILE_SIZE)}，处理可能较慢。\n"
                f"建议拆分文件或增加 `max_segment_length` 参数。\n"
            )
        else:
            warning = ""

        progress(0.2, desc="正在解析 Markdown 文档...")

        # 第二步：使用 HeadingSegmenter 进行切分
        splitter = HeadingSegmenter(
            max_segment_length=max_segment_length,
            heading_level_limit=heading_level_limit,
        )
        start_time = time.time()
        chunks = splitter.split(md_content)
        parse_time = time.time() - start_time

        if not chunks:
            return (
                md_content + warning,
                json.dumps(
                    {"error": "未检测到任何内容分块"}, ensure_ascii=False, indent=2
                ),
                "未检测到任何内容分块",
            )

        progress(0.5, desc="正在生成 JSON 结果...")

        # 第三步：JSON 格式结果
        json_result = {
            "summary": {
                "total_chunks": len(chunks),
                "max_segment_length": max_segment_length,
                "parse_time_seconds": round(parse_time, 2),
                "file_size": format_file_size(actual_size),
            },
            "chunks": chunks,
        }
        json_output = json.dumps(json_result, ensure_ascii=False, indent=2)

        progress(0.7, desc="正在生成 Markdown 渲染...")

        # 第四步：Markdown 渲染（带颜色背景的分块）
        html_parts = []

        # 标题区域
        html_parts.append(f"""
        <div style="padding: 20px; margin-bottom: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; color: white;">
            <h2 style="margin: 0; font-size: 24px;">📄 切分结果渲染</h2>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">
                共 {len(chunks)} 个分块 | 解析时间: {parse_time:.2f} 秒 | 文件大小: {format_file_size(actual_size)}
            </p>
        </div>
        """)

        # 按类型统计
        type_counts = {}
        for chunk in chunks:
            chunk_type = chunk["type"]
            type_counts[chunk_type] = type_counts.get(chunk_type, 0) + 1

        html_parts.append(
            "<div style='margin-bottom: 15px;'><strong>📊 分块类型统计:</strong> "
        )
        for chunk_type, count in sorted(type_counts.items()):
            style = get_chunk_style(chunk_type)
            html_parts.append(f"""
            <span style="background: {style["bg"]}; border: 1px solid {style["border"]}; padding: 4px 12px; border-radius: 15px; margin-right: 8px; font-size: 12px; color: {style["text"]}; font-weight: bold;">
                {format_chunk_type(chunk_type)}: {count}
            </span>
            """)
        html_parts.append("</div>")

        # 限制显示的分块数量
        display_chunks = chunks[:MAX_PREVIEW_CHUNKS]

        if len(chunks) > MAX_PREVIEW_CHUNKS:
            html_parts.append(f"""
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px 15px; margin-bottom: 20px; border-radius: 5px; color: #856404;">
                <strong>⚠️ 注意:</strong> 分块数量过多（共 {len(chunks)} 个），仅显示前 {MAX_PREVIEW_CHUNKS} 个分块。
                完整数据请查看 JSON 格式结果。
            </div>
            """)

        # 渲染分块为 Markdown（带颜色背景）
        html_parts.append(
            "<div style='display: flex; flex-direction: column; gap: 12px;'>"
        )

        for i, chunk in enumerate(display_chunks):
            style = get_chunk_style(chunk["type"])

            # 分块标签信息
            chunk_info = f"""
            <div style="
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 6px 12px;
                background: {style["bg"]};
                border: 1px solid {style["border"]};
                border-radius: 6px 6px 0 0;
                border-bottom: none;
                font-size: 11px;
                color: {style["text"]};
                font-weight: 500;
            ">
                <span style="background: {style["border"]}; color: white; padding: 2px 8px; border-radius: 8px; font-weight: bold;">
                    #{chunk["id"]}
                </span>
                <span>{format_chunk_type(chunk["type"])}</span>
                <span style="opacity: 0.7;">|</span>
                <span>层级: {chunk["level"]}</span>
                <span style="opacity: 0.7;">|</span>
                <span>父级: {chunk["pids"][-1] if chunk["pids"] else "无"}</span>
            </div>
            """

            # 分块内容（转换为 HTML 预览）
            content_html = markdown_to_html_preview(chunk["content"])

            # 分块容器
            html_parts.append(f"""
            <div style="
                margin-bottom: 20px;
                border: 2px solid {style["border"]};
                border-radius: 0 6px 6px 6px;
                overflow: hidden;
                background: white;
                transition: all 0.2s ease;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            " onmouseover="this.style.boxShadow='0 4px 8px rgba(0,0,0,0.1)'; this.style.borderColor='{style["hover"]}'"
               onmouseout="this.style.boxShadow='0 1px 3px rgba(0,0,0,0.05)'; this.style.borderColor='{style["border"]}'">
                {chunk_info}
                <div style="
                    padding: 16px;
                    background: {style["bg"]};
                    border-top: 1px solid {style["border"]};
                    line-height: 1.8;
                    color: #333;
                ">
                    {content_html}
                </div>
            </div>
            """)

        html_parts.append("</div>")

        progress(1.0, desc="完成！")

        return md_content, json_output, "".join(html_parts)

    except Exception as e:
        error_msg = f"处理出错: {str(e)}"
        import traceback

        traceback.print_exc()
        return (
            f"读取文件失败: {error_msg}",
            json.dumps(
                {"error": error_msg, "traceback": traceback.format_exc()},
                ensure_ascii=False,
                indent=2,
            ),
            f'<div style="color: #d32f2f; padding: 20px; background: #ffebee; border-radius: 5px; border-left: 4px solid #d32f2f;">{escape_html(error_msg)}</div>',
        )


def clear_all() -> tuple[None, str, str]:
    """清空所有内容"""
    return None, "", ""


# 自定义 CSS 样式
custom_css = """
/* 颜色图例 */
.color-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    padding: 15px;
    background: #f8f9fa;
    border-radius: 8px;
    margin-bottom: 15px;
}

.color-legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
}

.color-box {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 2px solid rgba(0,0,0,0.1);
}

/* 渲染预览容器 */
.render-preview {
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 8px;
    background: #fafafa;
    max-height: 800px;
    overflow-y: auto;
}

/* 分块间的分隔线 */
.chunk-separator {
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.chunk-separator::before,
.chunk-separator::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #e0e0e0;
}
.chunk-separator span {
    padding: 0 10px;
    font-size: 11px;
    color: #999;
}
"""


# 创建 Gradio 界面
with gr.Blocks(
    title="Markdown 文档切分测试",
    theme=gr.themes.Soft(),
    css=custom_css,
    analytics_enabled=False,
) as demo:
    gr.Markdown("# 📄 Markdown 文档切分测试工具")
    gr.Markdown(
        "上传 Markdown 文档，查看智能切分后的分块内容（支持渲染回文档和 JSON 切换）"
    )

    with gr.Row():
        with gr.Column(scale=1):
            file_input = gr.File(
                label="选择 Markdown 文件", file_types=[".md"], type="filepath"
            )

        with gr.Column(scale=1):
            with gr.Row():
                process_btn = gr.Button("🚀 开始切分", variant="primary", size="lg")
                clear_btn = gr.Button("🗑️ 清空", variant="secondary")

    gr.Markdown("---")

    # 配置区域
    with gr.Row():
        with gr.Column():
            gr.Markdown("### ⚙️ 切分参数配置")
            max_segment_length = gr.Slider(
                minimum=100,
                maximum=2000,
                value=500,
                step=50,
                label="最大分块长度（字符数）",
                info="较小的值会产生更多分块，较大的值会产生更少的分块",
                interactive=True,
            )
            heading_level_limit = gr.Slider(
                minimum=1,
                maximum=6,
                value=6,
                step=1,
                label="标题切分等级（H1-H6）",
                info="控制哪些级别的标题会被作为独立分块切分。例如设为 3 时，只有 H1-H3 会成为分块，H4-H6 视为正文",
                interactive=True,
            )

    gr.Markdown("---")

    # 颜色图例
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🎨 分块类型颜色图例")
            color_legend_html = ""
            for chunk_type, style in CHUNK_COLORS.items():
                color_legend_html += f"""
                <div class="color-legend-item" style="background: {style["bg"]}; border: 1px solid {style["border"]}; color: {style["text"]};">
                    <div class="color-box" style="background: {style["bg"]}; border-color: {style["border"]};"></div>
                    <span style="font-weight: 500;">{format_chunk_type(chunk_type)}</span>
                </div>
                """
            gr.HTML(color_legend_html)

    gr.Markdown("---")

    # 主要内容区域 - 使用 Tabs 切换视图
    with gr.Row():
        # 左栏：原文档内容
        with gr.Column(scale=1):
            gr.Markdown("### 📋 原始 Markdown 文档")
            original_output = gr.Textbox(
                label="原文档内容",
                lines=30,
                show_label=False,
                placeholder="上传的 md 文档内容将显示在这里...",
                interactive=False,
            )

        # 右栏：切分结果（支持 Markdown 渲染和 JSON 切换）
        with gr.Column(scale=1):
            gr.Markdown("### 📊 切分结果")
            with gr.Tabs() as result_tabs:
                with gr.Tab("📝 Markdown 渲染（带切分标识）"):
                    render_output = gr.HTML(
                        value="<div style='padding: 60px; text-align: center; color: #999; font-size: 14px;'>等待上传文件...<br><br>点击「🚀 开始切分」按钮查看分块渲染结果</div>"
                    )

                with gr.Tab("🔧 JSON 数据"):
                    json_output = gr.Code(
                        label="JSON 格式",
                        language="json",
                        lines=30,
                        show_label=False,
                        interactive=False,
                    )

    # 事件绑定
    process_btn.click(
        fn=split_markdown_formatted,
        inputs=[file_input, max_segment_length, heading_level_limit],
        outputs=[original_output, json_output, render_output],
    )

    clear_btn.click(fn=clear_all, outputs=[file_input, json_output, render_output])

    # 示例说明
    gr.Markdown("---")
    gr.Markdown("""
    ### 💡 使用说明

    1. 点击"选择 Markdown 文件"上传你的 .md 文件
    2. 使用滑块调整最大分块长度（100-2000 字符）
    3. 使用滑块调整标题切分等级（1-6），控制哪些级别的标题会被作为独立分块
    4. 点击"🚀 开始切分"按钮进行文档切分
    5. 在右侧切换「Markdown 渲染」或「JSON 数据」查看不同格式的结果

    ### 🎨 查看模式

    - **Markdown 渲染**: 将分块重新渲染为 Markdown，每个分块用不同颜色背景标识切分点，便于直观查看文档是如何被切分的
    - **JSON 数据**: 查看完整的结构化数据，包含每个分块的详细信息（ID、类型、层级、父级、内容等）

    ### 🔍 切分类型说明

    - **TEXT** 📝: 普通文本内容
    - **IMAGE** 🖼️: 图片内容
    - **TABLE** 📊: 表格内容
    - **CODE** 💻: 代码块
    - **HEADER** 📌: 标题内容
    - **HTML_IMAGE** 🖼️: HTML 图片
    - **HTML_TABLE** 📊: HTML 表格
    - **HTML_CODE** 💻: HTML 代码块

    ### ⚙️ 配置建议

    **最大分块长度：**
    - **100-300 字符**: 适合需要精确匹配的场景，会产生更多分块
    - **500 字符**: 默认值，适合大多数文档处理场景
    - **1000-2000 字符**: 适合长文档，减少分块数量，提高处理效率

    **标题切分等级：**
    - **1-2**: 只将最高级别标题（H1-H2）作为分块，适合扁平化文档
    - **3-4**: 将主要标题（H1-H4）作为分块，中等层级结构
    - **5-6**: 将所有标题（H1-H6）作为分块，保留完整层级结构（默认值）
    """)


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=3008,
        share=False,
    )
