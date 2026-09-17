"""Safe local image normalization; never fetch user-provided image URLs."""
import base64
import binascii
import io
import re
import warnings


def prepare_image(data_url, *, max_side=1600, max_mb=12, square=False):
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise ValueError('Image support is not installed on the server. Redeploy with requirements.txt installed in the app Python environment.') from exc
    if not isinstance(data_url, str) or len(data_url) > (max_mb * 4 / 3 + 1) * 1024 * 1024:
        raise ValueError(f'Choose an image smaller than {max_mb} MB')
    match = re.fullmatch(r'data:image/(?:png|jpeg|webp|gif|bmp);base64,([A-Za-z0-9+/=\r\n]+)', data_url)
    if not match:
        raise ValueError('Use a PNG, JPEG, WebP, GIF or BMP image, not an image link or SVG')
    try:
        content = base64.b64decode(match[1], validate=True)
        if not content or len(content) > max_mb * 1024 * 1024:
            raise ValueError(f'Choose a non-empty image smaller than {max_mb} MB')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.width * source.height > 20_000_000:
                    raise ValueError('Image is too large; use at most 20 megapixels')
                if source.format not in ('PNG', 'JPEG', 'WEBP', 'GIF', 'BMP'):
                    raise ValueError('Unsupported image format')
                source.seek(0)
                image = ImageOps.exif_transpose(source)
                alpha = image.mode in ('RGBA', 'LA') or 'transparency' in image.info
                image = image.convert('RGBA' if alpha else 'RGB')
                if square:
                    side = min(max_side, image.width, image.height)
                    image = ImageOps.fit(image, (side, side), method=Image.Resampling.LANCZOS)
                else:
                    image.thumbnail((max_side, max_side), resample=Image.Resampling.LANCZOS)
                # A fresh image discards EXIF, ICC and textual metadata.
                safe = Image.new(image.mode, image.size)
                safe.paste(image)
                output = io.BytesIO()
                safe.save(output, format='PNG' if alpha else 'JPEG', **({} if alpha else {'quality': 88}))
                encoded = output.getvalue()
                if len(encoded) > 4 * 1024 * 1024:
                    raise ValueError('Image is too detailed; resize it before uploading')
                return ('image/png' if alpha else 'image/jpeg'), encoded
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Image could not be read safely; choose a smaller PNG, JPEG or WebP image') from exc
