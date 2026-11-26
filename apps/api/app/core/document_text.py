"""자료 파일에서 글만 꺼낸다. 이후 조각 나누기·충돌 검사는 기존 적재 흐름을 쓴다."""

from io import BytesIO
from pathlib import PurePath
import re
from xml.etree import ElementTree
from zipfile import ZipFile

from docx import Document
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from app.core.constants import DOCUMENT_SIZE_MESSAGE, MAX_DOCUMENT_BYTES
from app.modules.documents.parsing import DocumentFormatError

SAVE_AS_MESSAGE = "한글에서 hwpx나 PDF로 저장해 올려 주세요"


def extract_text(filename: str, data: bytes) -> str:
    suffix = PurePath(filename).suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentFormatError("UTF-8 글 파일이 아니에요") from error
    if suffix == ".hwp":
        raise DocumentFormatError(SAVE_AS_MESSAGE)
    if suffix not in {".pdf", ".docx", ".hwpx"}:
        raise DocumentFormatError("지금은 .md·.txt·.pdf·.docx·.hwpx 글 파일만 읽을 수 있어요")
    try:
        if suffix == ".pdf":
            content = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
        else:
            with ZipFile(BytesIO(data)) as archive:
                if sum(info.file_size for info in archive.infolist()) > MAX_DOCUMENT_BYTES:
                    raise DocumentFormatError(DOCUMENT_SIZE_MESSAGE)
                if suffix == ".docx":
                    parts = []
                    for block in Document(BytesIO(data)).iter_inner_content():
                        if isinstance(block, Paragraph):
                            parts.append(block.text)
                        else:
                            parts.extend("\t".join(cell.text for cell in row.cells) for row in block.rows)
                    content = "\n".join(parts)
                else:
                    sections = [name for name in archive.namelist() if re.fullmatch(r"Contents/section\d+\.xml", name)]
                    sections.sort(key=lambda name: int(re.search(r"\d+", name).group()))
                    parts = []
                    for name in sections:
                        for node in ElementTree.fromstring(archive.read(name)).iter():
                            tag = node.tag.rsplit("}", 1)[-1]
                            if tag == "p":
                                parts.append("\n")
                            elif tag == "t":
                                parts.append("".join(node.itertext()))
                    content = "".join(parts).lstrip("\n")
    except DocumentFormatError:
        raise
    except Exception as error:  # 잘못된 컨테이너·PDF·XML도 기존 적재 오류로 표시한다.
        raise DocumentFormatError("자료를 읽지 못했어요.") from error
    if not content.strip():
        raise DocumentFormatError(SAVE_AS_MESSAGE)
    return content
