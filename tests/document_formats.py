"""외부 파일 없이 만드는 작은 가상 자료. 실제 추출기를 통과시킨다."""

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def archive_bytes(entries):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def document_bytes(suffix, content="[TEST] picnic supplies"):
    output = BytesIO()
    if suffix == "pdf":
        writer = PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        if content:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            escaped = content.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.set_data(f"BT /F1 12 Tf 20 80 Td ({escaped}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(output)
    elif suffix == "docx":
        doc = Document()
        for line in content.splitlines():
            doc.add_paragraph(line)
        if content:
            doc.add_table(rows=1, cols=1).cell(0, 0).text = "[TEST] table supplies"
            doc.add_paragraph("[TEST] after table")
        doc.save(output)
    else:
        paragraphs = "".join(f"<hp:p><hp:run><hp:t>{escape(line)}</hp:t></hp:run></hp:p>"
                             for line in content.splitlines())
        sections = {"Contents/section0.xml":
                    f'<hs:sec xmlns:hs="urn:section" xmlns:hp="urn:paragraph">{paragraphs}</hs:sec>',
                    "Contents/header.xml": "<header>not body text</header>"}
        if content:
            for number in (10, 2):
                sections[f"Contents/section{number}.xml"] = (
                    f'<sec><p><run><t>[TEST] section {number}</t></run></p></sec>')
        return archive_bytes(sections)
    return output.getvalue()


def rejection_cases():
    for suffix in ("pdf", "docx", "hwpx"):
        yield "empty." + suffix, document_bytes(suffix, ""), "한글에서 hwpx나 PDF로 저장해 올려 주세요"
        yield "broken." + suffix, ("[TEST] broken " + suffix).encode(), "자료를 읽지 못했어요."
    yield "old.hwp", b"[TEST] hwp", "한글에서 hwpx나 PDF로 저장해 올려 주세요"
    yield "other.rtf", b"[TEST] rtf", "지금은 .md·.txt·.pdf·.docx·.hwpx 글 파일만 읽을 수 있어요"
