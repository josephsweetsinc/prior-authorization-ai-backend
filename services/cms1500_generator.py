"""Service for generating CMS-1500 claim data summary PDFs."""

import io
import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

if TYPE_CHECKING:
    from reportlab.platypus.doctemplate import BaseDocTemplate

from models.ambulance_request import AmbulanceRequest

logger = logging.getLogger(__name__)


def _display_name(value: StrEnum | None) -> str | None:
    """Convert an enum value like GROUP_HEALTH_PLAN to 'Group Health Plan'.

    Args:
        value: Enum member (or None).

    Returns:
        str | None: Human-readable display name, or None if value is None.

    """
    if value is None:
        return None
    return value.value.replace('_', ' ').title()


class CMS1500GeneratorService:
    """Service for generating CMS-1500 claim data summary PDFs.

    This is a data summary of the fields on the standard CMS-1500 Health
    Insurance Claim Form (labeled with the form's real box numbers for
    traceability), not a print-ready reproduction of the official
    red-ink form - real CMS-1500 claims are normally filed electronically
    (837P) or by mail with a MAC, not generated as a standalone PDF.
    Service-line data (CPT/HCPCS codes, charges, days/units - Box 24) is
    not included, since this system does not yet model billing rates or
    procedure codes; that section is left as a note for billing staff.

    """

    def generate_cms1500_pdf(  # noqa: PLR0915
        self,
        request: AmbulanceRequest,
    ) -> bytes:
        """Generate a CMS-1500 claim data summary PDF.

        Args:
            request: AmbulanceRequest instance with all required fields.

        Returns:
            bytes: PDF file bytes.

        """
        buffer = io.BytesIO()

        header_blue = colors.HexColor('#1E407C')

        left_margin = 15 * mm
        right_margin = 15 * mm
        top_margin = 36 * mm
        bottom_margin = 15 * mm

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=right_margin,
            leftMargin=left_margin,
            topMargin=top_margin,
            bottomMargin=bottom_margin,
        )

        story: list[Any] = []
        styles = getSampleStyleSheet()

        header_title_style = ParagraphStyle(
            'HeaderTitle',
            parent=styles['Normal'],
            fontSize=22,
            leading=24,
            textColor=colors.white,
            fontName='Helvetica-Bold',
        )
        header_subtitle_style = ParagraphStyle(
            'HeaderSubtitle',
            parent=styles['Normal'],
            fontSize=11,
            leading=13,
            textColor=colors.HexColor('#E2E8F0'),
            fontName='Helvetica',
        )
        header_time_style = ParagraphStyle(
            'HeaderTime',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#BFDBFE'),
            fontName='Helvetica',
            alignment=2,
        )
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Normal'],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor('#111827'),
            spaceAfter=10,
            spaceBefore=5,
            fontName='Helvetica-Bold',
            textTransform='uppercase',
        )
        label_style = ParagraphStyle(
            'Label',
            parent=styles['Normal'],
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor('#6B7280'),
            fontName='Helvetica-Bold',
            textTransform='uppercase',
            spaceAfter=2,
        )
        value_style = ParagraphStyle(
            'Value',
            parent=styles['Normal'],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#000000'),
            fontName='Helvetica',
        )
        note_style = ParagraphStyle(
            'Note',
            parent=styles['Normal'],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#6B7280'),
            fontName='Helvetica-Oblique',
        )

        def draw_header_on_canvas(
            canvas: Canvas, doc: 'BaseDocTemplate'
        ) -> None:
            """Draw blue header on page canvas to ignore margins."""
            page_width, page_height = A4
            header_height = 30 * mm

            canvas.saveState()
            canvas.setFillColor(header_blue)
            canvas.rect(
                0,
                page_height - header_height,
                page_width,
                header_height,
                stroke=0,
                fill=1,
            )

            generation_time = datetime.now(UTC).strftime(
                '%b %d, %Y at %H:%M:%S UTC'
            )

            title_p = Paragraph('CMS-1500', header_title_style)
            subtitle_p = Paragraph(
                'Health Insurance Claim Form - Data Summary',
                header_subtitle_style,
            )
            time_p = Paragraph(generation_time, header_time_style)

            padding_left = 15 * mm
            padding_right = 15 * mm
            padding_top = 6 * mm

            _title_w, title_h = title_p.wrap(page_width * 0.6, header_height)
            _subtitle_w, subtitle_h = subtitle_p.wrap(
                page_width * 0.6, header_height
            )

            title_y = page_height - padding_top - title_h
            title_p.drawOn(canvas, padding_left, title_y)

            subtitle_y = title_y - subtitle_h - 1
            subtitle_p.drawOn(canvas, padding_left, subtitle_y)

            time_w, time_h = time_p.wrap(page_width * 0.3, header_height)
            time_x = page_width - padding_right - time_w
            time_y = page_height - padding_top - time_h - 2 * mm
            time_p.drawOn(canvas, time_x, time_y)

            canvas.restoreState()

        def create_field(label_text: str, value_text: Any) -> list[Any]:
            """Create a field with label and value.

            Args:
                label_text: Field label text.
                value_text: Field value (will be converted to string).

            Returns:
                List of flowables: label paragraph, value paragraph, spacer.

            """
            if value_text is None or value_text == '':
                value_text = 'N/A'
            return [
                Paragraph(label_text, label_style),
                Paragraph(str(value_text), value_style),
                Spacer(1, 3 * mm),
            ]

        available_width = A4[0] - left_margin - right_margin

        # Box 1 / 1a / 4 / 6: INSURANCE INFORMATION
        story.append(Paragraph('1. INSURANCE INFORMATION', section_style))

        ins_col1: list[Any] = []
        ins_col1.extend(
            create_field(
                'PAYER TYPE (BOX 1)', _display_name(request.insurance_type)
            )
        )
        ins_col1.extend(
            create_field(
                "INSURED'S ID NUMBER (BOX 1A)", request.insured_id_number
            )
        )

        ins_col2: list[Any] = []
        ins_col2.extend(
            create_field('PAYER NAME', request.insurance_payer_name)
        )
        ins_col2.extend(
            create_field(
                "PATIENT RELATIONSHIP TO INSURED (BOX 6)",
                _display_name(request.patient_relationship_to_insured),
            )
        )

        s1_table = Table(
            [[ins_col1, ins_col2]],
            colWidths=[available_width * 0.5, available_width * 0.5],
        )
        s1_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(s1_table)

        insured_name_data = create_field(
            "INSURED'S NAME (BOX 4, if different from patient)",
            request.insured_name,
        )
        s1b_table = Table([[insured_name_data]], colWidths=[available_width])
        s1b_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(s1b_table)

        story.append(Spacer(1, 2 * mm))
        story.append(
            HRFlowable(
                width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')
            )
        )
        story.append(Spacer(1, 3 * mm))

        # Box 2 / 3: PATIENT INFORMATION
        story.append(Paragraph('2. PATIENT INFORMATION', section_style))

        p_dob = (
            request.patient_date_of_birth.strftime('%m-%d-%Y')
            if request.patient_date_of_birth
            else 'N/A'
        )
        patient_name = (
            f'{request.patient_last_name}, {request.patient_first_name}'
        )

        pat_col1: list[Any] = []
        pat_col1.extend(create_field('PATIENT NAME (BOX 2)', patient_name))
        pat_col1.extend(create_field('DATE OF BIRTH (BOX 3)', p_dob))

        pat_col2: list[Any] = []
        pat_col2.extend(
            create_field('SEX (BOX 3)', _display_name(request.patient_sex))
        )
        pat_col2.extend(
            create_field(
                "PATIENT ID / MBI",
                request.patient_id,
            )
        )

        s2_table = Table(
            [[pat_col1, pat_col2]],
            colWidths=[available_width * 0.5, available_width * 0.5],
        )
        s2_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(s2_table)

        story.append(Spacer(1, 2 * mm))
        story.append(
            HRFlowable(
                width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')
            )
        )
        story.append(Spacer(1, 3 * mm))

        # Box 21: DIAGNOSIS
        story.append(Paragraph('3. DIAGNOSIS', section_style))
        diag_data = create_field(
            'DIAGNOSIS OR NATURE OF ILLNESS OR INJURY (BOX 21, LINE 1)',
            request.primary_diagnosis,
        )
        s3_table = Table([[diag_data]], colWidths=[available_width])
        s3_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(s3_table)

        story.append(Spacer(1, 2 * mm))
        story.append(
            HRFlowable(
                width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')
            )
        )
        story.append(Spacer(1, 3 * mm))

        # Box 17 / 17b: REFERRING / ORDERING PHYSICIAN
        story.append(
            Paragraph('4. REFERRING / ORDERING PHYSICIAN', section_style)
        )

        phys_col1: list[Any] = []
        phys_col1.extend(
            create_field(
                'NAME OF REFERRING PROVIDER (BOX 17)',
                request.ordering_physician,
            )
        )

        phys_col2: list[Any] = []
        phys_col2.extend(
            create_field('NPI (BOX 17B)', request.ordering_physician_npi)
        )
        phys_col2.extend(create_field('PHONE', request.physician_phone))

        s4_table = Table(
            [[phys_col1, phys_col2]],
            colWidths=[available_width * 0.5, available_width * 0.5],
        )
        s4_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(s4_table)

        story.append(Spacer(1, 2 * mm))
        story.append(
            HRFlowable(
                width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')
            )
        )
        story.append(Spacer(1, 3 * mm))

        # Box 23: PRIOR AUTHORIZATION
        story.append(Paragraph('5. PRIOR AUTHORIZATION', section_style))
        prior_auth_data = create_field(
            'PRIOR AUTHORIZATION NUMBER (BOX 23)',
            request.utn,
        )
        s5_table = Table([[prior_auth_data]], colWidths=[available_width])
        s5_table.setStyle(
            TableStyle(
                [
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(s5_table)
        story.append(
            Paragraph(
                'Populated once a Unique Tracking Number (UTN) is issued '
                'by the payer.',
                note_style,
            )
        )

        story.append(Spacer(1, 2 * mm))
        story.append(
            HRFlowable(
                width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')
            )
        )
        story.append(Spacer(1, 3 * mm))

        # Box 24 / 25 / 32 / 33: SERVICE LINE & BILLING
        story.append(
            Paragraph('6. SERVICE LINE & BILLING', section_style)
        )
        story.append(
            Paragraph(
                'Dates of service, place of service, CPT/HCPCS procedure '
                'codes, charges, and billing/facility provider '
                'information (Boxes 24, 25, 32, 33) are not available '
                'from prior authorization data and must be completed by '
                'billing staff before this claim is submitted.',
                note_style,
            )
        )

        doc.build(story, onFirstPage=draw_header_on_canvas)

        buffer.seek(0)
        pdf_bytes = buffer.read()

        logger.info(
            'Generated CMS-1500 PDF for request %s (size: %d bytes)',
            getattr(request, 'id', 'unknown'),
            len(pdf_bytes),
        )

        return pdf_bytes
