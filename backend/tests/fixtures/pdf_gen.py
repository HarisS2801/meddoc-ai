"""Hand-rolled minimal PDF generator used only by the test suite.

Creates small multi-page PDFs with a valid xref table so pypdf can parse
them, without depending on a PDF-writing library at test time.

All content is synthetic and generated on the fly.
"""

import io

_PAGE_SIZE = b"[0 0 612 792]"


def _escape_pdf_string(value: str) -> str:
    value = value.replace("\\", "\\\\")
    value = value.replace("(", "\\(")
    value = value.replace(")", "\\)")
    value = value.replace("\n", "\\n")
    return value


def _content_stream(text: str) -> bytes:
    body = ("BT /F1 11 Tf 72 720 Td (%s) Tj ET" % _escape_pdf_string(text)).encode(
        "latin-1", "replace"
    )
    return b"<< /Length %d >>\nstream\n%s\nendstream\n" % (len(body), body)


def build_pdf(page_texts: list[str]) -> bytes:
    """Build a valid PDF containing one text page per entry in ``page_texts``."""
    page_count = len(page_texts)

    def content_num(i: int) -> int:
        return 4 + 2 * i

    def page_num(i: int) -> int:
        return 4 + 2 * i + 1

    catalog_obj = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = b" ".join(b"%d 0 R" % page_num(i) for i in range(page_count))
    pages_obj = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, page_count)
    font_obj = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    objects: list[tuple[int, bytes]] = [
        (1, catalog_obj),
        (2, pages_obj),
        (3, font_obj),
    ]
    for i, text in enumerate(page_texts):
        objects.append((content_num(i), _content_stream(text)))
        page_obj = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox %s "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
            % (_PAGE_SIZE, content_num(i))
        )
        objects.append((page_num(i), page_obj))

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    max_num = objects[-1][0]
    offsets = [0] * (max_num + 1)
    for num, body in objects:
        offsets[num] = out.tell()
        out.write(b"%d 0 obj\n" % num)
        out.write(body)
        out.write(b"\nendobj\n")

    xref_position = out.tell()
    out.write(b"xref\n")
    out.write(b"0 %d\n" % (max_num + 1))
    out.write(b"0000000000 65535 f \n")
    for num in range(1, max_num + 1):
        out.write(b"%010d 00000 n \n" % offsets[num])
    out.write(b"trailer\n")
    out.write(b"<< /Size %d /Root 1 0 R >>\n" % (max_num + 1))
    out.write(b"startxref\n")
    out.write(b"%d\n" % xref_position)
    out.write(b"%%EOF\n")
    return out.getvalue()


_SAMPLE_PAGES = [
    "This care plan describes a synthetic patient. "
    "Follow-up appointment is scheduled for 15 October.",
    "The medication list includes metformin 500 mg twice daily.",
    "Contact the clinic if fasting blood glucose exceeds 10 mmol/L "
    "for three consecutive days.",
]


def sample_pdf_bytes() -> bytes:
    return build_pdf(_SAMPLE_PAGES)


def corrupt_pdf_bytes() -> bytes:
    """A PDF whose tail is cut off so parsing must fail."""
    valid = build_pdf(_SAMPLE_PAGES)
    return valid[: len(valid) // 2]