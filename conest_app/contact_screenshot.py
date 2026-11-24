"""Private, preview-only screenshot recognition for Opportunity contacts.

OCR is local: no uploaded image or contact data is sent to an AI provider.
"""
from __future__ import annotations

import base64
import binascii
import io
import os
import re
import shutil
import subprocess
import threading
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from .tenders import ValidationError, builder_key

MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_PIXELS = 12_000_000
MAX_TEXT = 24_000
MAX_ROWS = 60
_SLOTS = threading.BoundedSemaphore(1)
_EMAIL = re.compile(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}')
_PHONE = re.compile(r'(?<!\w)(?:\+?61[ .()-]*[2-478]|0[2-478])(?:[ .()-]*\d){8}(?!\d)|(?<!\d)(?:1300|1800)(?:[ .()-]*\d){6}(?!\d)|(?<!\d)13(?:[ .()-]*\d){4}(?!\d)')
_COMPANY = re.compile(r'\b(?:construction[s]?|construct|builders?|building|contractors?|projects?|group|fitout[s]?|fit[- ]out[s]?|interiors?|pty|ltd|limited|development[s]?|corp(?:oration)?|commercial|contracting)\b', re.I)
_REGION = re.compile(r'^\(?(?:NSW|VIC|QLD|WA|SA|TAS|NT|ACT)\)?$', re.I)
_HEADER = re.compile(r'^(?:builders?|contacts?|contact people|contact details|phone(?: number)?|email(?: address)?|name)\s*:?$', re.I)
_FIELD_LABEL = re.compile(r'^(?:builder|contact(?: person)?|name|phone(?: number)?|mobile|tel|email(?: address)?)\s*:\s*', re.I)


def parse_contact_text(text: str, known_builders=()):
    """Read vertical builder blocks; ambiguous labels stay editable, never invented."""
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValidationError('Contact text is too long.')
    known = {builder_key(name): name for name in known_builders if isinstance(name, str) and name.strip()}
    rows = []
    company = ''
    person = {'name': '', 'phones': [], 'emails': []}
    notices = []

    def flush():
        nonlocal person
        if person['name'] or person['phones'] or person['emails']:
            rows.append({'builder': company, **person})
        person = {'name': '', 'phones': [], 'emails': []}

    def new_company(value):
        nonlocal company
        old_len = len(rows)
        flush()
        if company and len(rows) == old_len and not any(row['builder'] == company for row in rows):
            rows.append({'builder': company, 'name': '', 'phones': [], 'emails': []})
        company = known.get(builder_key(value), value)[:500]

    for raw_line in text.splitlines():
        line = ' '.join(raw_line.strip().split()).strip('|•—–')
        if not line or _HEADER.fullmatch(line):
            continue
        explicit_builder = bool(re.match(r'^builder\s*:', line, re.I))
        line = _FIELD_LABEL.sub('', line).strip()
        if not line:
            continue
        if _REGION.fullmatch(line) and company and not any(person.values()):
            # OCR often wraps the regional suffix to the next line.
            suffix = '(' + line.strip('()').upper() + ')'
            company = known.get(builder_key(company + ' ' + suffix), company + ' ' + suffix)
            continue
        emails = _EMAIL.findall(line)
        phones = [value.strip() for value in _PHONE.findall(line)]
        label = _PHONE.sub('', _EMAIL.sub('', line)).strip(' |,;:-')
        if explicit_builder or (label and (builder_key(label) in known or _COMPANY.search(label))):
            new_company(label or line)
            label = ''
        elif label and not company and not (emails or phones):
            new_company(label)
            label = ''
        if label:
            if person['name']:
                flush()
            person['name'] = label[:200]
        if phones and not label and person['emails'] and person['name']:
            # The sample's next person starts with a phone before their name.
            flush()
        for field, values in (('phones', phones), ('emails', emails)):
            for value in values:
                if value not in person[field] and len(person[field]) < 12:
                    person[field].append(value)
    flush()
    if company and not any(row['builder'] == company for row in rows):
        rows.append({'builder': company, 'name': '', 'phones': [], 'emails': []})
    if any(not row['builder'] or not row['name'] for row in rows):
        notices.append('Some names or builders are missing. Check the screenshot before adding these rows.')
    if len(rows) > MAX_ROWS:
        notices.append('Only the first 60 detected rows are shown. Import the remainder separately.')
    if not rows:
        notices.append('No builder or contact could be identified. Correct the recognized text or enter details manually.')
    return {'rows': rows[:MAX_ROWS], 'text': text, 'warnings': notices}


def _prepare_image(content: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                    raise ValidationError('Choose a single PNG, JPEG or WebP screenshot.')
                if source.width * source.height > MAX_PIXELS:
                    raise ValidationError('Screenshot is too large. Crop it to the builder/contact list.')
                image = ImageOps.exif_transpose(source).convert('RGBA')
                background = Image.new('RGBA', image.size, 'white')
                background.alpha_composite(image)
                image = ImageOps.autocontrast(ImageOps.grayscale(background))
                # Improve small screenshots while bounding CPU/memory cost.
                scale = min(3.0, 2400 / max(image.size))
                if scale != 1:
                    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format='PNG')
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning, ValueError) as exc:
        raise ValidationError('Unable to read screenshot. Choose a valid PNG, JPEG or WebP image.') from None


def recognize(payload):
    known = payload.get('knownBuilders', [])
    if not isinstance(known, list) or len(known) > 2000 or any(not isinstance(name, str) or len(name) > 500 for name in known):
        raise ValidationError('Invalid builder list.')
    if 'text' in payload:
        return parse_contact_text(payload['text'], known)
    encoded = payload.get('content')
    if not isinstance(encoded, str) or not encoded or len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValidationError('Choose a screenshot smaller than 6 MB.', 413)
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValidationError('Invalid screenshot upload.') from None
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValidationError('Choose a screenshot smaller than 6 MB.', 413)
    executable = shutil.which(os.environ.get('CONEST_TESSERACT_PATH') or 'tesseract')
    if not executable:
        raise ValidationError('Private screenshot recognition needs Tesseract OCR on the server. Ask your administrator to enable it, or paste the contact text below.', 503)
    if not _SLOTS.acquire(blocking=False):
        raise ValidationError('Another screenshot is being recognized. Try again shortly.', 503)
    try:
        image = _prepare_image(content)
        try:
            output = subprocess.run([executable, 'stdin', 'stdout', '-l', 'eng', '--psm', '6'], input=image,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=18,
                                    env={**os.environ, 'OMP_THREAD_LIMIT': '1'}, check=True)
        except (OSError, subprocess.SubprocessError):
            raise ValidationError('Screenshot recognition is unavailable. Check the server OCR setup, or paste the contact text.', 503) from None
        return parse_contact_text(output.stdout.decode('utf-8', errors='replace')[:MAX_TEXT], known)
    finally:
        _SLOTS.release()
