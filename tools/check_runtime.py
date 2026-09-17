"""Fail deployment clearly when the app's actual Python lacks import support."""
import importlib
import sys
if sys.version_info < (3, 10):
    raise SystemExit('TEC ConEst requires Python 3.10 or newer')
print('Python:', sys.executable)
failed = []
for name in ('openpyxl', 'pdfplumber', 'PIL'):
    try:
        module = importlib.import_module(name)
        print(name, getattr(module, '__version__', ''), module.__file__)
    except ImportError:
        failed.append(name)
if failed:
    raise SystemExit('Missing application dependencies: ' + ', '.join(failed) + '. Install requirements.txt with the Python interpreter shown above.')
