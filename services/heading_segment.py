import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Pattern

from markdown_it import MarkdownIt
from markdown_it.token import Token

# ==================== 数据结构定义 ====================


class ChunkType:
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    CODE = "code"
    HEADER = "header"
    HTML_IMAGE = "html_image"
    HTML_TABLE = "html_table"
    HTML_CODE = "html_code"


@dataclass
class Chunk:
    id: int
    pids: List[int]
    level: int
    content: str
    type: str
    headers: List[str]
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SectionNode:
    def __init__(self, level: int, raw_title: str):
        self.level = level
        self.raw_title = raw_title
        self.tokens: List[Token] = []
        self.children: List["SectionNode"] = []
        self.parent: Optional["SectionNode"] = None


# ==================== 核心工具类 ====================


class HeadingSegmenter:
    def __init__(self, max_segment_length: int = 500, heading_level_limit: int = 6):
        self.md = MarkdownIt("commonmark", {"breaks": True, "html": True})
        self.max_segment_length = max_segment_length
        self.heading_level_limit = heading_level_limit
        self.current_id = 1

        self.sentence_split_pattern: Pattern = re.compile(r"([。？！.?!])")
        self.html_img_pattern: Pattern = re.compile(
            r'<img\s+[^>]*?src=["\'](.*?)["\'][^>]*?>', re.IGNORECASE
        )
        self.html_table_pattern: Pattern = re.compile(
            r"<table[\s\S]*?</table>", re.IGNORECASE
        )
        self.html_pre_pattern: Pattern = re.compile(
            r"<pre[\s\S]*?</pre>", re.IGNORECASE
        )

        # 【修复关键】：宽松的正则兜底，用于匹配标准解析器无法识别的“坏”URL（如包含不平衡括号）
        # 匹配逻辑：![...](...)，尽量匹配到行尾的右括号
        self.fallback_md_image_pattern = re.compile(r"!\[([^\]]*)\]\((.*)\)")

    def split(self, markdown_text: str) -> List[Dict[str, Any]]:
        if not markdown_text:
            return []
        tokens = self.md.parse(markdown_text)
        source_lines = markdown_text.splitlines()
        root = self._build_section_tree(tokens, source_lines)
        chunks = []
        if root.tokens:
            self._process_section_content(root, [], [], chunks, source_lines)
        for child in root.children:
            self._process_node_recursively(child, [], [], chunks, source_lines)
        return [c.to_dict() for c in chunks]

    def _build_section_tree(
        self, tokens: List[Token], source_lines: List[str]
    ) -> SectionNode:
        root = SectionNode(level=0, raw_title="")
        current_node = root
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.type == "heading_open":
                level = int(token.tag[1:])
                if level <= self.heading_level_limit:
                    raw_title = self._get_source_content(token, source_lines) or ""
                    if not raw_title:
                        inline_content = (
                            tokens[i + 1].content if i + 1 < len(tokens) else ""
                        )
                        raw_title = f"{'#' * level} {inline_content}"
                    new_node = SectionNode(level, raw_title)
                    while (
                        current_node.level >= level and current_node.parent is not None
                    ):
                        current_node = current_node.parent
                    new_node.parent = current_node
                    current_node.children.append(new_node)
                    current_node = new_node
                    while i < len(tokens) and tokens[i].type != "heading_close":
                        i += 1
                else:
                    current_node.tokens.append(token)
            else:
                current_node.tokens.append(token)
            i += 1
        return root

    def _process_node_recursively(
        self,
        node: SectionNode,
        parent_pids: List[int],
        parent_headers: List[str],
        chunks: List[Chunk],
        source_lines: List[str],
    ) -> None:
        current_headers = parent_headers + [node.raw_title]
        header_id = self.current_id
        self.current_id += 1
        self._add_chunk(
            chunks,
            header_id,
            parent_pids,
            node.level,
            node.raw_title,
            ChunkType.HEADER,
            parent_headers,
        )
        current_pids = parent_pids + [header_id]
        if node.tokens:
            self._process_section_content(
                node, current_pids, current_headers, chunks, source_lines
            )
        for child in node.children:
            self._process_node_recursively(
                child, current_pids, current_headers, chunks, source_lines
            )

    def _process_section_content(
        self,
        node: SectionNode,
        pids: List[int],
        headers: List[str],
        chunks: List[Chunk],
        source_lines: List[str],
    ) -> None:
        tokens = node.tokens
        level = node.level
        text_buffer: List[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token.type in ("fence", "code_block"):
                self._flush_text_buffer(text_buffer, pids, level, headers, chunks)
                content = self._get_source_content(token, source_lines) or token.content
                self._add_chunk(
                    chunks,
                    self.current_id,
                    pids,
                    level,
                    content,
                    ChunkType.CODE,
                    headers,
                )
                self.current_id += 1
            elif token.type == "table_open":
                self._flush_text_buffer(text_buffer, pids, level, headers, chunks)
                close_idx = self._find_closing_token_index(tokens, i, "table_close")
                content = (
                    self._get_source_content(token, source_lines) or "<table markdown>"
                )
                self._add_chunk(
                    chunks,
                    self.current_id,
                    pids,
                    level,
                    content,
                    ChunkType.TABLE,
                    headers,
                )
                self.current_id += 1
                i = close_idx
            elif token.type == "html_block":
                content = token.content
                if (
                    self.html_img_pattern.search(content)
                    or self.html_table_pattern.search(content)
                    or self.html_pre_pattern.search(content)
                ):
                    self._flush_text_buffer(text_buffer, pids, level, headers, chunks)
                    self._handle_html_block(content, pids, level, headers, chunks)
                else:
                    text_buffer.append(content)
            elif token.type in (
                "paragraph_open",
                "bullet_list_open",
                "ordered_list_open",
                "blockquote_open",
                "heading_open",
            ):
                close_type = token.type.replace("_open", "_close")
                close_idx = self._find_closing_token_index(tokens, i, close_type)
                block_content = self._get_source_content(token, source_lines)
                if block_content:
                    # 1. 检查标准 Token 图片
                    inline_tokens = [
                        t for t in tokens[i + 1 : close_idx] if t.type == "inline"
                    ]
                    has_standard_image = False
                    for t in inline_tokens:
                        if t.children and any(c.type == "image" for c in t.children):
                            has_standard_image = True
                            break

                    # 2. 检查不规范图片 (正则兜底)
                    has_broken_image = self.fallback_md_image_pattern.search(
                        block_content
                    )

                    if has_standard_image or has_broken_image:
                        self._flush_text_buffer(
                            text_buffer, pids, level, headers, chunks
                        )
                        self._handle_mixed_content_robust(
                            block_content, inline_tokens, pids, level, headers, chunks
                        )
                    else:
                        text_buffer.append(block_content)
                i = close_idx
            i += 1
        self._flush_text_buffer(text_buffer, pids, level, headers, chunks)

    def _handle_mixed_content_robust(
        self, block_text: str, inline_tokens: List[Token], pids, level, headers, chunks
    ):
        """
        增强版混合内容切分：结合 Token 定位和正则兜底
        """
        image_spans = []  # 存储 (start, end, content, meta)

        # A. Token 方式提取 (标准 Markdown 图片)
        for t in inline_tokens:
            if not t.children:
                continue
            for child in t.children:
                if child.type == "image":
                    attrs = child.attrs if child.attrs is not None else {}
                    src_raw = attrs.get("src", "")
                    src = str(src_raw) if src_raw is not None else ""

                    alt_raw = child.content
                    alt = str(alt_raw) if alt_raw is not None else ""

                    if not src:
                        continue  # 跳过无链接图片

                    # 在源码中定位 src
                    search_start = 0
                    while True:
                        src_idx = block_text.find(src, search_start)
                        if src_idx == -1:
                            break

                        # 简单验证前面是否有 ](
                        if (
                            src_idx >= 2
                            and block_text[src_idx - 2 : src_idx].strip() == "]("
                        ):
                            # 向后找右括号
                            end_paren = block_text.find(")", src_idx + len(src))
                            # 向前找左侧 ![
                            start_bracket = block_text.rfind("![", 0, src_idx)

                            if end_paren != -1 and start_bracket != -1:
                                full_img_str = block_text[start_bracket : end_paren + 1]
                                meta = {"url": src, "alt": alt}
                                image_spans.append(
                                    (start_bracket, end_paren + 1, full_img_str, meta)
                                )
                                search_start = end_paren + 1
                                continue
                        search_start = src_idx + 1

        # B. 正则兜底提取 (针对 markdown-it 无法识别的损坏图片)
        for match in self.fallback_md_image_pattern.finditer(block_text):
            start, end = match.span()

            # 检查是否与 Token 识别的图片重叠，避免重复
            is_overlap = False
            for t_start, t_end, _, _ in image_spans:
                if not (end <= t_start or start >= t_end):
                    is_overlap = True
                    break

            if not is_overlap:
                # 这是一个被 Parser 遗漏的图片！
                alt = match.group(1)
                src = match.group(2)
                src = src.strip()
                meta = {"url": src, "alt": alt}
                full_img_str = match.group(0)
                image_spans.append((start, end, full_img_str, meta))

        # C. 按位置切分
        image_spans.sort(key=lambda x: x[0])

        cursor = 0
        for start, end, img_content, meta in image_spans:
            if start > cursor:
                pre_text = block_text[cursor:start]
                self._handle_text_splitting_hierarchical(
                    pre_text, pids, level, headers, chunks
                )

            self._add_chunk(
                chunks,
                self.current_id,
                pids,
                level,
                img_content,
                ChunkType.IMAGE,
                headers,
                meta,
            )
            self.current_id += 1
            cursor = end

        if cursor < len(block_text):
            remaining_text = block_text[cursor:]
            self._handle_text_splitting_hierarchical(
                remaining_text, pids, level, headers, chunks
            )

    def _flush_text_buffer(self, buffer: List[str], pids, level, headers, chunks):
        if not buffer:
            return
        full_text = "\n\n".join(buffer)
        buffer.clear()
        self._handle_text_splitting_hierarchical(
            full_text, pids, level, headers, chunks
        )

    def _handle_text_splitting_hierarchical(
        self,
        text: str,
        pids: List[int],
        level: int,
        headers: List[str],
        chunks: List[Chunk],
    ):
        if not text.strip():
            return
        if len(text) <= self.max_segment_length:
            self._add_chunk(
                chunks,
                self.current_id,
                pids,
                level,
                text.strip(),
                ChunkType.TEXT,
                headers,
            )
            self.current_id += 1
            return
        lines = text.splitlines(keepends=True)
        current_buffer = ""
        for line in lines:
            if len(current_buffer) + len(line) > self.max_segment_length:
                if current_buffer:
                    self._add_chunk(
                        chunks,
                        self.current_id,
                        pids,
                        level,
                        current_buffer.strip(),
                        ChunkType.TEXT,
                        headers,
                    )
                    self.current_id += 1
                    current_buffer = ""
                if len(line) > self.max_segment_length:
                    self._handle_sentence_splitting(line, pids, level, headers, chunks)
                else:
                    current_buffer = line
            else:
                current_buffer += line
        if current_buffer:
            self._add_chunk(
                chunks,
                self.current_id,
                pids,
                level,
                current_buffer.strip(),
                ChunkType.TEXT,
                headers,
            )
            self.current_id += 1

    def _handle_sentence_splitting(
        self,
        text: str,
        pids: List[int],
        level: int,
        headers: List[str],
        chunks: List[Chunk],
    ):
        parts = self.sentence_split_pattern.split(text)
        current_chunk_text = ""
        i = 0
        while i < len(parts):
            part = parts[i]
            sep = parts[i + 1] if i + 1 < len(parts) else ""
            segment = part + sep
            if len(current_chunk_text) + len(segment) > self.max_segment_length:
                if current_chunk_text:
                    self._add_chunk(
                        chunks,
                        self.current_id,
                        pids,
                        level,
                        current_chunk_text.strip(),
                        ChunkType.TEXT,
                        headers,
                    )
                    self.current_id += 1
                    current_chunk_text = ""
                if len(segment) > self.max_segment_length:
                    self._add_chunk(
                        chunks,
                        self.current_id,
                        pids,
                        level,
                        segment.strip(),
                        ChunkType.TEXT,
                        headers,
                    )
                    self.current_id += 1
                else:
                    current_chunk_text = segment
            else:
                current_chunk_text += segment
            i += 2
        if current_chunk_text:
            self._add_chunk(
                chunks,
                self.current_id,
                pids,
                level,
                current_chunk_text.strip(),
                ChunkType.TEXT,
                headers,
            )
            self.current_id += 1

    def _handle_html_block(
        self,
        content: str,
        pids: List[int],
        level: int,
        headers: List[str],
        chunks: List[Chunk],
    ):
        type_str = ChunkType.TEXT
        meta = {}
        if self.html_img_pattern.search(content):
            type_str = ChunkType.HTML_IMAGE
            match = self.html_img_pattern.search(content)
            if match:
                meta = {"url": match.group(1), "alt": ""}
        elif self.html_table_pattern.search(content):
            type_str = ChunkType.HTML_TABLE
        elif self.html_pre_pattern.search(content):
            type_str = ChunkType.HTML_CODE

        if type_str != ChunkType.TEXT:
            self._add_chunk(
                chunks, self.current_id, pids, level, content, type_str, headers, meta
            )
            self.current_id += 1
        else:
            self._handle_text_splitting_hierarchical(
                content, pids, level, headers, chunks
            )

    def _get_source_content(
        self, token: Token, source_lines: List[str]
    ) -> Optional[str]:
        if token.map:
            return "\n".join(source_lines[token.map[0] : token.map[1]])
        return None

    def _find_closing_token_index(
        self, tokens: List[Token], start_index: int, close_type: str
    ) -> int:
        nesting = 1
        open_type = close_type.replace("_close", "_open")
        for j in range(start_index + 1, len(tokens)):
            if tokens[j].type == open_type:
                nesting += 1
            elif tokens[j].type == close_type:
                nesting -= 1
            if nesting == 0:
                return j
        return start_index

    def _add_chunk(
        self, chunks, chunk_id, pids, level, content, type_str, headers, meta=None
    ):
        if type_str == ChunkType.TEXT and not content.strip():
            return
        chunks.append(
            Chunk(
                chunk_id,
                list(pids),
                level,
                content,
                type_str,
                list(headers),
                meta or {},
            )
        )
