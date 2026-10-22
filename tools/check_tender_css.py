"""Validate mobile CSS as delivered by either Vite or a prebuilt release.

Vite combines imported CSS into a fingerprinted asset and deletes old dist files
on each build. Test what the generated HTML actually serves, not obsolete names.
"""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit


class _StylesheetLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag != 'link':
            return
        values = dict(attrs)
        if 'stylesheet' in (values.get('rel') or '').split():
            self.hrefs.append(values.get('href') or '')


def served_mobile_css(root: Path, *required: str) -> str:
    """Return bundled CSS, raising AssertionError when mobile rules are absent.

    Supports a build with a single hashed Vite stylesheet as well as the
    manually packaged /tenders/assets/mobile-vNNNN.css sheets.
    """
    index = root / 'tenders_web' / 'index.html'
    assert index.is_file(), f'Missing built Tender HTML: {index}'
    parser = _StylesheetLinks()
    parser.feed(index.read_text(encoding='utf-8'))

    asset_prefix = '/tenders/assets/'
    assets_dir = root / 'tenders_web' / 'assets'
    css_files = []
    for href in parser.hrefs:
        path = urlsplit(href).path
        if not path.startswith(asset_prefix) or not path.endswith('.css'):
            continue
        name = path[len(asset_prefix):]
        # Only allow CSS files immediately inside the built assets directory.
        assert name == Path(name).name, f'Unexpected stylesheet path: {href}'
        css_path = assets_dir / name
        assert css_path.is_file(), f'CSS referenced by built HTML is missing: {css_path}'
        css_files.append(css_path)

    assert css_files, 'Built Tender HTML references no bundled Tender stylesheet'
    css = '\n'.join(path.read_text(encoding='utf-8') for path in css_files)
    normalized = re.sub(r'\s+', '', css)
    for fragment in required:
        compact = re.sub(r'\s+', '', fragment)
        assert compact in normalized, (
            f'Missing mobile CSS rule {fragment!r} from the stylesheets served by '
            f'{index}: {[file.name for file in css_files]}'
        )
    return css
