import os
import re
import shutil
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


class OCRNotConfiguredError(RuntimeError):
    pass


SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}
PROJECT_TESSDATA_DIR = Path(__file__).resolve().parents[2] / 'recursos' / 'tessdata'

_PDF_RENDER_MATRIX_SCALE      = 5.5    # ~396 DPI — página completa, primera pasada
_PDF_RENDER_MATRIX_SCALE_HD   = 8.33   # ~600 DPI — página completa, segunda pasada condicional
_PDF_RENDER_MATRIX_SCALE_CLIP = 11.1   # ~800 DPI — clip de header, zona del consecutivo
_PDF_HEADER_CLIP_RATIO        = 0.25   # fracción superior de la página para el clip

_DIGITAL_TEXT_MIN_CHARS       = 80
_DIGITAL_TEXT_MIN_ALNUM_RATIO = 0.25

# Rango de ratio alfanumérico que activa el reintento a 600 DPI.
# < 10%: imagen fundamentalmente ilegible — más DPI no agrega información.
# > 28%: extracción aceptable a 396 DPI — no vale la pena el coste extra.
_HD_RETRY_RATIO_MIN = 0.10
_HD_RETRY_RATIO_MAX = 0.28

# Confianza mínima del OSD de Tesseract para aceptar la rotación detectada.
_OSD_MIN_CONFIDENCE = 2.0


def extract_text_with_ocr(path, max_pages=2, lang='spa+eng', early_exit_fn=None):
    configure_tesseract()

    file_path = Path(path)
    extension = file_path.suffix.lower()

    if extension == '.pdf':
        return extract_pdf_text_with_ocr(file_path, max_pages=max_pages, lang=lang, early_exit_fn=early_exit_fn)

    if extension in SUPPORTED_IMAGE_EXTENSIONS:
        text = ocr_image(file_path, lang=lang)
        return {
            'text': text,
            'pages_text': [{'page': 1, 'text': text}],
            'page_detected': 1,
            'pages_processed': 1,
        }

    return {
        'text': '',
        'pages_text': [],
        'page_detected': None,
        'pages_processed': 0,
    }


def configure_tesseract():
    try:
        import pytesseract
    except ImportError as exc:
        raise OCRNotConfiguredError('Instala pytesseract para ejecutar OCR local.') from exc

    configured_cmd = os.getenv('TESSERACT_CMD', '').strip()
    common_paths = [
        configured_cmd,
        shutil.which('tesseract') or '',
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]

    for candidate in common_paths:
        if candidate and Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            configure_tessdata_dir()
            return candidate

    raise OCRNotConfiguredError(
        'Tesseract no esta instalado o no esta configurado. Define TESSERACT_CMD en .env.'
    )


def configure_tessdata_dir():
    configured_tessdata = os.getenv('TESSDATA_DIR', '').strip()
    candidates = [
        Path(configured_tessdata) if configured_tessdata else None,
        PROJECT_TESSDATA_DIR,
    ]

    for candidate in candidates:
        if candidate and candidate.exists():
            os.environ['TESSDATA_PREFIX'] = str(candidate)
            return candidate

    return None


def extract_pdf_text_with_ocr(file_path, max_pages=2, lang='spa+eng', early_exit_fn=None):
    try:
        import fitz
    except ImportError as exc:
        raise OCRNotConfiguredError('Instala PyMuPDF para renderizar PDFs escaneados.') from exc

    text_chunks = []
    pages_text  = []
    page_detected = None

    with fitz.open(str(file_path)) as document:
        pages_to_process = min(max_pages, document.page_count)

        for page_index in range(pages_to_process):
            page = document.load_page(page_index)

            # ── Nivel 1A: texto digital embebido (omite OCR si el PDF ya tiene texto) ─
            page_text = _extract_digital_text_from_page(page)

            if not page_text:
                # ── Nivel 1B: header clip a ~800 DPI — zona donde aparece el consecutivo
                header_text = _try_header_clip_ocr(page, lang)

                # ── Nivel 1C: página completa a ~396 DPI ──────────────────────────────
                matrix = fitz.Matrix(_PDF_RENDER_MATRIX_SCALE, _PDF_RENDER_MATRIX_SCALE)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image  = Image.frombytes('RGB', [pixmap.width, pixmap.height], pixmap.samples)

                # ── Nivel 2A: corregir rotación antes de OCR ──────────────────────────
                image = _correct_rotation(image)

                # ── Niveles 1C + 2C: OCR con fallbacks PSM 6 → 4 → 3 → 11 ──────────
                page_text = ocr_pillow_image(image, lang=lang).strip()
                if _looks_poor_ocr(page_text):
                    page_text = ocr_pillow_image(image, lang=lang, psm=4).strip()
                if _looks_poor_ocr(page_text):
                    alt = ocr_pillow_image(image, lang=lang, psm=3).strip()
                    if len(alt) > len(page_text):
                        page_text = alt
                if _looks_poor_ocr(page_text):
                    alt = ocr_pillow_image(image, lang=lang, psm=11).strip()
                    if len(alt) > len(page_text):
                        page_text = alt

                # ── Nivel 2B: segunda pasada a ~600 DPI si extracción fue parcial ────
                if _is_partially_readable(page_text):
                    page_text = _try_high_dpi_ocr(page, page_text, lang)

                # ── Nivel 2C: anteponer header clip si aporta texto no contenido ──────
                if header_text and header_text not in page_text:
                    page_text = header_text + '\n' + page_text

            text_chunks.append(page_text)
            pages_text.append({'page': page_index + 1, 'text': page_text})

            if page_text and page_detected is None:
                page_detected = page_index + 1

            if early_exit_fn is not None and early_exit_fn(pages_text):
                break

    return {
        'text': '\n'.join(text_chunks).strip(),
        'pages_text': pages_text,
        'page_detected': page_detected,
        'pages_processed': len(pages_text),
    }


def _extract_digital_text_from_page(page):
    """Extrae texto digital embebido del PDF sin OCR.

    Retorna el texto si tiene contenido útil suficiente; cadena vacía si la
    página es una imagen escaneada o el texto embebido es insignificante.
    """
    try:
        text = page.get_text().strip()
        if not text or len(text) < _DIGITAL_TEXT_MIN_CHARS:
            return ''
        alnum_ratio = sum(c.isalnum() for c in text) / max(len(text), 1)
        if alnum_ratio < _DIGITAL_TEXT_MIN_ALNUM_RATIO:
            return ''
        return text
    except Exception:
        return ''


def _correct_rotation(image):
    """Detecta la orientación de la página con OSD de Tesseract y la corrige.

    Solo aplica rotaciones de 90°/180°/270° con confianza suficiente.
    Sin efecto si OSD falla o la imagen no tiene suficiente texto detectable.
    """
    try:
        import pytesseract
        gray = ImageOps.grayscale(image)
        osd  = pytesseract.image_to_osd(gray, config='--psm 0')
        rotate_match = re.search(r'Rotate:\s*(\d+)', osd)
        conf_match   = re.search(r'Orientation confidence:\s*([\d.]+)', osd)
        angle      = int(rotate_match.group(1))  if rotate_match else 0
        confidence = float(conf_match.group(1))  if conf_match   else 0.0
        if angle != 0 and confidence >= _OSD_MIN_CONFIDENCE:
            return image.rotate(angle, expand=True)
    except Exception:
        pass
    return image


def _try_header_clip_ocr(page, lang):
    """Renderiza solo el top 25 % de la página a ~800 DPI y aplica OCR.

    El consecutivo PEL aparece siempre en el encabezado. Una región pequeña a
    mayor DPI da mayor precisión que la página completa a menor DPI, con un costo
    de cómputo menor. Si el clip falla por cualquier razón retorna cadena vacía.
    """
    try:
        import fitz
        rect = page.rect
        clip = fitz.Rect(
            rect.x0, rect.y0,
            rect.x1, rect.y0 + rect.height * _PDF_HEADER_CLIP_RATIO,
        )
        matrix = fitz.Matrix(_PDF_RENDER_MATRIX_SCALE_CLIP, _PDF_RENDER_MATRIX_SCALE_CLIP)
        pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        image  = Image.frombytes('RGB', [pixmap.width, pixmap.height], pixmap.samples)
        image  = _correct_rotation(image)
        text   = ocr_pillow_image(image, lang=lang, psm=6).strip()
        if _looks_poor_ocr(text):
            alt = ocr_pillow_image(image, lang=lang, psm=7).strip()
            if len(alt) > len(text):
                text = alt
        return text
    except Exception:
        return ''


def _try_high_dpi_ocr(page, current_text, lang):
    """Segunda pasada a ~600 DPI — solo cuando 396 DPI extrajo texto parcial.

    No se ejecuta si la imagen es fundamentalmente ilegible (ratio < 10%) porque
    más DPI no agrega información que no existe en el escaneo original.
    """
    try:
        import fitz
        matrix_hd = fitz.Matrix(_PDF_RENDER_MATRIX_SCALE_HD, _PDF_RENDER_MATRIX_SCALE_HD)
        pixmap_hd = page.get_pixmap(matrix=matrix_hd, alpha=False)
        image_hd  = Image.frombytes('RGB', [pixmap_hd.width, pixmap_hd.height], pixmap_hd.samples)
        image_hd  = _correct_rotation(image_hd)
        for psm in (6, 4, 3):
            text_hd = ocr_pillow_image(image_hd, lang=lang, psm=psm).strip()
            if not _looks_poor_ocr(text_hd) and len(text_hd) > len(current_text):
                return text_hd
    except Exception:
        pass
    return current_text


def _is_partially_readable(text):
    """True si el ratio alfanumérico está en el rango donde 600 DPI puede ayudar."""
    if not text:
        return False
    ratio = sum(c.isalnum() for c in text) / max(len(text), 1)
    return _HD_RETRY_RATIO_MIN <= ratio <= _HD_RETRY_RATIO_MAX


def ocr_image(file_path, lang='spa+eng'):
    with Image.open(file_path) as image:
        return ocr_pillow_image(image, lang=lang)


def ocr_pillow_image(image, lang='spa+eng', psm=6):
    import pytesseract

    configure_tesseract()
    configure_tessdata_dir()
    processed_image = preprocess_image(image)
    config_parts = [f'--psm {psm}', '--oem 3']
    return pytesseract.image_to_string(processed_image, lang=lang, config=' '.join(config_parts))


def preprocess_image(image):
    """Preprocesa la imagen adaptándose a su calidad.

    Usa OpenCV cuando está disponible. Cae a Pillow como fallback.
    """
    try:
        import cv2   # noqa: F401
        import numpy # noqa: F401
        return _preprocess_opencv(image)
    except ImportError:
        return _preprocess_pillow(image)


def _preprocess_opencv(image):
    """Preprocesamiento adaptativo según calidad del escaneo.

    - Buena calidad (std ≥ 60): umbral de Otsu — óptimo para histogramas bimodales,
      evita degradar documentos que ya tienen buen contraste.
    - Baja calidad  (std < 60): umbralización adaptativa gaussiana — maneja iluminación
      desigual, sombras de doblez y manchas típicas de escaneos físicos de PEL.
    """
    import cv2
    import numpy as np

    img_array = np.array(image)
    gray      = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY) if img_array.ndim == 3 else img_array
    denoised  = cv2.medianBlur(gray, 3)

    if gray.std() >= 60:
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,
            C=10,
        )

    return Image.fromarray(binary)


def _preprocess_pillow(image):
    """Preprocesamiento con Pillow — fallback si OpenCV no está disponible."""
    grayscale = ImageOps.grayscale(image)
    grayscale = ImageOps.autocontrast(grayscale)
    enhanced  = ImageEnhance.Contrast(grayscale).enhance(2.0)
    sharpened = ImageEnhance.Sharpness(enhanced).enhance(1.8)
    denoised  = sharpened.filter(ImageFilter.MedianFilter(size=3))
    return denoised.point(lambda pixel: 255 if pixel > 165 else 0)


def _looks_poor_ocr(text):
    if not text or len(text.strip()) < 80:
        return True
    alnum = sum(char.isalnum() for char in text)
    return (alnum / max(len(text), 1)) < 0.30


def extract_consecutivo_roi(file_path, lang='spa+eng'):
    """Extrae texto del consecutivo desde la región superior derecha del PDF (ROI OCR).

    Región: x=[60%, 100%], y=[0%, 15%] de la primera página.
    Sólo activa para PDFs. Retorna cadena vacía si falla o no hay texto.
    """
    configure_tesseract()
    file_path = Path(file_path)
    if file_path.suffix.lower() != '.pdf':
        return ''
    try:
        import fitz
        import pytesseract
    except ImportError:
        return ''
    try:
        with fitz.open(str(file_path)) as doc:
            if doc.page_count == 0:
                return ''
            page = doc.load_page(0)
            rect = page.rect
            clip = fitz.Rect(
                rect.x0 + rect.width * 0.60,
                rect.y0,
                rect.x1,
                rect.y0 + rect.height * 0.15,
            )
            matrix = fitz.Matrix(_PDF_RENDER_MATRIX_SCALE_CLIP, _PDF_RENDER_MATRIX_SCALE_CLIP)
            pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
            image = Image.frombytes('RGB', [pixmap.width, pixmap.height], pixmap.samples)
            image = _correct_rotation(image)
            image = preprocess_image(image)

            # Whitelist: dígitos + prefijos MAY-PEL/PRO/RCG/RCI/RCP
            _whitelist = '0123456789MYPELRGIOCNDB- '
            text = pytesseract.image_to_string(
                image, lang=lang,
                config=f'--psm 7 --oem 3 -c tessedit_char_whitelist={_whitelist}',
            ).strip()
            if not text:
                text = pytesseract.image_to_string(
                    image, lang=lang,
                    config=f'--psm 6 --oem 3 -c tessedit_char_whitelist={_whitelist}',
                ).strip()
            return text
    except Exception:
        return ''


