"""One-off diagnostic tool: send a real test fax through RingCentral.

Builds a simple, realistic-looking referral document and faxes it to
the given number via RingCentral's own send-fax API - the same
RingCentralClient.send_fax() the app uses for real Novitas
submissions. Sending it to PAAI's own fax number is a genuine
end-to-end test of the inbound pipeline: RingCentral receives it,
calls our webhook, and the app should auto-create a draft request
from it, exactly as it would for a real referral fax.

Usage:
    python scripts/send_test_fax.py <to_number>

Example:
    python scripts/send_test_fax.py +15514652826

"""

import asyncio
import io
import sys
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from services.fax.ringcentral_client import RingCentralClient  # noqa: E402


def _build_test_referral_pdf() -> bytes:
    """Build a one-page fake ambulance transport referral PDF.

    Returns:
        bytes: The rendered PDF content.

    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    transport_date = date.today() + timedelta(days=3)  # noqa: DTZ011

    lines = [
        'NON-EMERGENT AMBULANCE TRANSPORT REQUEST',
        '',
        'Patient Name: Jane TestPatient',
        'Date of Birth: 01/15/1950',
        'Medicare Beneficiary ID: 1EG4-TE5-TEST',
        '',
        'Pickup Address: 123 Test St, Springfield, IL 62701',
        'Destination Address: Springfield Dialysis Center, '
        '456 Medical Dr, Springfield, IL 62702',
        '',
        f'Date of Transport: {transport_date.strftime("%m/%d/%Y")}',
        'Time of Transport: 09:00 AM',
        '',
        'Primary Diagnosis: End-stage renal disease',
        'Medical Justification: Patient requires wheelchair van '
        'transport for dialysis; unable to sit upright for car travel.',
        '',
        'Ordering Physician: Dr. Test Physician',
        'Physician Phone: (555) 555-0100',
        '',
        '*** THIS IS A TEST DOCUMENT - NOT A REAL PATIENT ***',
    ]

    text = c.beginText(72, 720)
    text.setFont('Helvetica', 11)
    for line in lines:
        text.textLine(line)
    c.drawText(text)
    c.showPage()
    c.save()
    return buffer.getvalue()


async def send_test_fax(to_number: str) -> bool:
    """Send the test referral fax to the given number.

    Args:
        to_number: Destination fax number (E.164 format recommended).

    Returns:
        bool: True if the fax was accepted by RingCentral for sending.

    """
    pdf_bytes = _build_test_referral_pdf()

    client = RingCentralClient()
    try:
        result = await client.send_fax(
            to_number=to_number,
            attachments=[
                ('test-referral.pdf', pdf_bytes, 'application/pdf'),
            ],
        )
    except Exception as e:
        print(f'❌ Failed to send test fax: {e}')
        return False
    else:
        print('✅ Test fax submitted to RingCentral')
        print(f"   id: {result.get('id')}")
        print(f"   status: {result.get('messageStatus')}")
        return True
    finally:
        await client.aclose()


async def main() -> None:  # noqa: D103
    if len(sys.argv) != 2:  # noqa: PLR2004
        print('Usage: python scripts/send_test_fax.py <to_number>')
        sys.exit(1)
    to_number = sys.argv[1]
    sent = await send_test_fax(to_number)
    sys.exit(0 if sent else 1)


if __name__ == '__main__':
    asyncio.run(main())
