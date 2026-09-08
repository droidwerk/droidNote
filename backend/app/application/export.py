from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from app.domain.models import Person, Session, Summary, TranscriptSegment


def _clock(ms: int) -> str:
    seconds = max(ms, 0) // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def _speaker_name(segment: TranscriptSegment, people: dict[str, str]) -> str:
    if segment.speaker_id and segment.speaker_id in people:
        return people[segment.speaker_id]
    return ""


def export_pdf(
    session: Session,
    segments: list[TranscriptSegment],
    summary: Summary | None,
    people: list[Person],
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    font = _register_pdf_font()
    names = {item.id: item.name for item in people}
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DroidTitle",
        parent=styles["Heading1"],
        fontName=font,
        fontSize=16,
        leading=20,
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "DroidHeading",
        parent=styles["Heading2"],
        fontName=font,
        fontSize=13,
        leading=16,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "DroidBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=session.title,
    )
    story: list = [
        Paragraph(_escape(session.title), title_style),
        Paragraph(_escape(f"Início: {session.started_at.isoformat()}"), body_style),
    ]
    if session.ended_at:
        story.append(Paragraph(_escape(f"Fim: {session.ended_at.isoformat()}"), body_style))
    story.extend(_summary_paragraphs(summary, heading_style, body_style))
    story.append(Paragraph("Transcrição", heading_style))
    if not segments:
        story.append(Paragraph("—", body_style))
    for segment in segments:
        speaker = _speaker_name(segment, names)
        prefix = f"<b>{_escape(speaker)}</b> " if speaker else ""
        story.append(
            Paragraph(
                f"[{_clock(segment.start_ms)}] {prefix}{_escape(segment.text)}",
                body_style,
            )
        )
    document.build(story)
    return buffer.getvalue()


def export_docx(
    session: Session,
    segments: list[TranscriptSegment],
    summary: Summary | None,
    people: list[Person],
) -> bytes:
    from docx import Document

    names = {item.id: item.name for item in people}
    document = Document()
    document.add_heading(session.title, level=1)
    document.add_paragraph(f"Início: {session.started_at.isoformat()}")
    if session.ended_at:
        document.add_paragraph(f"Fim: {session.ended_at.isoformat()}")
    if summary:
        document.add_heading("Nota", level=2)
        if summary.notes_markdown.strip():
            document.add_paragraph(summary.notes_markdown.strip())
        if summary.overview:
            document.add_paragraph(summary.overview)
        _docx_list(document, "Pontos principais", summary.highlights)
        _docx_list(document, "Decisões", summary.decisions)
        if summary.action_items:
            document.add_heading("Prazos e donos", level=3)
            for item in summary.action_items:
                owner = f" ({item.owner})" if item.owner else ""
                due = f" — {item.due}" if item.due else ""
                document.add_paragraph(f"{item.text}{owner}{due}", style="List Bullet")
    document.add_heading("Transcrição", level=2)
    if not segments:
        document.add_paragraph("—")
    for segment in segments:
        speaker = _speaker_name(segment, names)
        prefix = f"{speaker}: " if speaker else ""
        document.add_paragraph(f"[{_clock(segment.start_ms)}] {prefix}{segment.text}")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _summary_paragraphs(summary: Summary | None, heading, body) -> list:
    if summary is None:
        return []
    story = [Paragraph("Nota", heading)]
    if summary.notes_markdown.strip():
        story.append(Paragraph(_escape(summary.notes_markdown.strip()).replace("\n", "<br/>"), body))
    if summary.overview:
        story.append(Paragraph(_escape(summary.overview), body))
    if summary.highlights:
        story.append(Paragraph("Pontos principais", heading))
        for item in summary.highlights:
            story.append(Paragraph(f"• {_escape(item)}", body))
    if summary.decisions:
        story.append(Paragraph("Decisões", heading))
        for item in summary.decisions:
            story.append(Paragraph(f"• {_escape(item)}", body))
    if summary.action_items:
        story.append(Paragraph("Prazos e donos", heading))
        for item in summary.action_items:
            owner = f" ({item.owner})" if item.owner else ""
            due = f" — {item.due}" if item.due else ""
            story.append(Paragraph(f"• {_escape(item.text)}{_escape(owner)}{_escape(due)}", body))
    return story


def _docx_list(document, title: str, items: list[str]) -> None:
    if not items:
        return
    document.add_heading(title, level=3)
    for item in items:
        document.add_paragraph(item, style="List Bullet")


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _register_pdf_font() -> str:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windir / "Fonts" / "arial.ttf",
        windir / "Fonts" / "segoeui.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "DroidBody" in pdfmetrics.getRegisteredFontNames():
        return "DroidBody"
    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont("DroidBody", str(path)))
            return "DroidBody"
    return "Helvetica"
