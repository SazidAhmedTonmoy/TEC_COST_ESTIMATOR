"""Public, version-pinned OCR resources. No user files are served by this route."""
OCR_PREFIX = '/tenders/assets/ocr-v6.0.1/'
OCR_MIME = {
    'tesseract.min.js': 'application/javascript; charset=utf-8',
    'worker.min.js': 'application/javascript; charset=utf-8',
    'tesseract-core-lstm.wasm.js': 'application/javascript; charset=utf-8',
    'tesseract-core-simd-lstm.wasm.js': 'application/javascript; charset=utf-8',
    'tesseract-core-lstm.wasm': 'application/wasm',
    'tesseract-core-simd-lstm.wasm': 'application/wasm',
    'eng.traineddata.gz': 'application/gzip',
    'tesseract-LICENSE.txt': 'text/plain; charset=utf-8',
    'core-LICENSE.txt': 'text/plain; charset=utf-8',
    'tesseract.min.js.LICENSE.txt': 'text/plain; charset=utf-8',
    'worker.min.js.LICENSE.txt': 'text/plain; charset=utf-8',
    'NOTICE.txt': 'text/plain; charset=utf-8',
}


def is_ocr_worker(path):
    return path == OCR_PREFIX + 'worker.min.js'
