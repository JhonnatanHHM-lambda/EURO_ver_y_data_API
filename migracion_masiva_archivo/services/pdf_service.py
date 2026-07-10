def inspect_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return {
            'numero_paginas': 0,
            'es_digital': False,
            'requiere_ocr': True,
            'texto_extraido': '',
            'error': 'Instala pypdf para inspeccionar texto y paginas de PDF',
        }

    try:
        reader = PdfReader(str(path))
        pages_text = []
        for page in reader.pages[:2]:
            pages_text.append(page.extract_text() or '')

        text = '\n'.join(pages_text).strip()
        return {
            'numero_paginas': len(reader.pages),
            'es_digital': bool(text),
            'requiere_ocr': not bool(text),
            'texto_extraido': text,
            'error': '',
        }
    except Exception as exc:
        return {
            'numero_paginas': 0,
            'es_digital': False,
            'requiere_ocr': True,
            'texto_extraido': '',
            'error': str(exc),
        }


