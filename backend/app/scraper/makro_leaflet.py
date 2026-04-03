"""
Parse a Makro promotional leaflet PDF and extract product deals.

Makro leaflets are hosted on Publitas (gazetki.makro.pl).
Strategy: fetch sitemap → find food leaflet slug → fetch page for PDF URL → download → parse.

Returns a list of dicts compatible with db.save_deals().
"""
import json
import logging
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import fitz  # pymupdf

from .base import LeafletScraper

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

_SITEMAP_URL = "https://gazetki.makro.pl/sitemap.xml"
_FOOD_SLUG_PATTERNS = ["mega-oferty", "oferty-dla-twojego-sklepu"]

# ── Price pattern ────────────────────────────────────────────────────────────

_BRUTTO_RE = re.compile(r'^\s*(\d+[,\.]\d{2})\s+BRUTTO\s*$')

# ── Noise filtering ─────────────────────────────────────────────────────────

_NOISE_EXACT = {
    'NETTO', '!',
    'GŁĘBOKO', 'MROŻONY',
    'HISZPANIA', 'GRECJA', 'INDIE', 'EGIPT',
}

_NOISE_RE = [
    re.compile(r'^\d+$'),
    re.compile(r'^\d+\s+NETTO'),
    re.compile(r'^H\s*I\s*T\s+C\s*E\s*N\s*O\s*W\s*Y'),
    re.compile(r'^Tex[–-]\d+'),
    re.compile(r'^Niektóre produkty'),
    re.compile(r'^Informacja handlowa'),
    re.compile(r'^Oferta (handlowa|ważna|tylko)'),
    re.compile(r'^pobierz aplikację'),
    re.compile(r'^Sprawdź szczegóły'),
    re.compile(r'^W promocji dostępn'),
    re.compile(r'^PRODUKT\b'),
    re.compile(r'^CENA W\b'),
    re.compile(r'^CENA 1\b'),
    re.compile(r'^PRZY ZAKUPIE'),
    re.compile(r'^Zaloguj się'),
    re.compile(r'^ALKOHOLE W'),
    re.compile(r'^lub przyjdź'),
    re.compile(r'^Go bigger'),
    re.compile(r'^Konkurs dla'),
    re.compile(r'^Trwa od'),
    re.compile(r'^Wygraj'),
    re.compile(r'^Organizatorem'),
    re.compile(r'^ZGARNIJ'),
    re.compile(r'^\d+\)\s'),
    re.compile(r'^Szukaj certyfikatu'),
    re.compile(r'^ASC-'),
    re.compile(r'^PL-EKO'),
    re.compile(r'^PRODUKT BIO'),
    re.compile(r'^Centrum Zaopatrzenia'),
    re.compile(r'^W WYBRANYCH'),
    re.compile(r'^EU Ecolabel'),
    re.compile(r'^Prosimy o'),
    re.compile(r'^i w aplikacji'),
    re.compile(r'^na zakupy tylko'),
    re.compile(r'^i Zielonej'),
    re.compile(r'^z halą w celu'),
    re.compile(r'^oraz na stronie'),
    re.compile(r'^Kaliszu, Koszalinie'),
    re.compile(r'^skontaktuj się'),
    re.compile(r'^PROGRAMIE\b'),
    re.compile(r'^dostępności produktów'),
]


def _is_noise(s):
    if s in _NOISE_EXACT:
        return True
    return any(p.match(s) for p in _NOISE_RE)


# ── HTTP helper ──────────────────────────────────────────────────────────────

def _make_request(url, timeout=15):
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError):
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")


def _slugify(text):
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode()
    text = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return text


# ── PDF discovery via Publitas sitemap ───────────────────────────────────────

def _fetch_sitemap_urls():
    """Fetch gazetki.makro.pl/sitemap.xml and return all publication URLs."""
    xml_text = _make_request(_SITEMAP_URL)
    root = ET.fromstring(xml_text)
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    return [loc.text.strip() for loc in root.findall('.//sm:loc', ns) if loc.text]


def _extract_publication_data(page_html):
    """Extract the ``var data = {...};`` JSON blob from a Publitas page."""
    m = re.search(r'var\s+data\s*=\s*(\{.*?\});\s*$', page_html, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _find_food_leaflet_pdf_url():
    """Return (pdf_url, title) for the current Makro food leaflet."""
    urls = _fetch_sitemap_urls()
    candidates = [u for u in urls if any(p in u for p in _FOOD_SLUG_PATTERNS)]

    if not candidates:
        raise RuntimeError(f"No food leaflet found in sitemap ({len(urls)} URLs checked)")

    for url in candidates[:3]:
        page_html = _make_request(url)
        data = _extract_publication_data(page_html)
        if data and data.get('config', {}).get('downloadPdfUrl'):
            pdf_url = data['config']['downloadPdfUrl']
            title = data['config'].get('publicationOriginalTitle', 'Makro Leaflet')
            logger.info("Found Makro leaflet: %s → %s", title, pdf_url)
            return pdf_url, title

    raise RuntimeError("Could not extract PDF URL from Makro leaflet candidates")


def download_latest_leaflet():
    """Download the current Makro food leaflet PDF. Returns path (caller must delete)."""
    pdf_url, _title = _find_food_leaflet_pdf_url()
    base = pdf_url.split('/')[-1].split('?')[0] or 'makro_leaflet.pdf'
    tmp_path = os.path.join(tempfile.gettempdir(), base)

    req = urllib.request.Request(pdf_url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        with open(tmp_path, 'wb') as f:
            f.write(r.read())

    logger.info("Downloaded Makro leaflet to %s", tmp_path)
    return tmp_path


# ── PDF image extraction ─────────────────────────────────────────────────────

def _extract_image_blocks(page):
    """Return list of (fitz.Rect, xref) for meaningful-sized images on the page."""
    result = []
    for img in page.get_images():
        xref, width, height = img[0], img[2], img[3]
        if width < 60 or height < 60:
            continue
        try:
            for rect in page.get_image_rects(xref):
                result.append((rect, xref))
        except Exception:
            pass
    return result


def _find_product_image(price_rect, image_blocks):
    """Return the xref of the image above and closest to the given price rect, or None."""
    best_xref = None
    best_score = float('inf')
    price_cx = (price_rect.x0 + price_rect.x1) / 2

    for img_rect, xref in image_blocks:
        if img_rect.y1 > price_rect.y0 + 5:   # image must sit above the price line
            continue
        img_cx = (img_rect.x0 + img_rect.x1) / 2
        h_dist = abs(img_cx - price_cx)
        v_dist = price_rect.y0 - img_rect.y1
        score = h_dist + v_dist * 0.3          # horizontal alignment matters more
        if score < best_score:
            best_score = score
            best_xref = xref

    return best_xref


def _save_image(doc, xref, images_dir, product_id):
    """Extract image by xref, save to images_dir, return /api/images/<filename> URL."""
    img_info = doc.extract_image(xref)
    ext = img_info.get("ext", "png")
    filename = f"{product_id}.{ext}"
    os.makedirs(images_dir, exist_ok=True)
    with open(os.path.join(images_dir, filename), "wb") as f:
        f.write(img_info["image"])
    return f"/api/images/{filename}"


# ── PDF page parser ──────────────────────────────────────────────────────────

def _extract_qty(detail_lines):
    """Pull packaging info (opak./pak.) from bullet detail lines."""
    for d in detail_lines:
        d_text = d.lstrip('•').strip()
        if 'opak.' in d_text or 'pak.' in d_text:
            # Strip trailing "• cena ..." if two bullets were on one line
            cena_idx = d_text.find('cena ')
            if cena_idx > 0:
                d_text = d_text[:cena_idx].strip().rstrip('•').strip()
            return d_text
    return ''


def _parse_page(text):
    """Parse a single Makro leaflet page into product dicts."""
    lines = text.replace('\xa0', ' ').split('\n')
    lines = [l.strip() for l in lines if l.strip()]

    products = []
    name_lines = []
    detail_lines = []
    in_details = False

    for line in lines:
        clean = line.replace('\ufeff', '').strip()
        if not clean:
            continue

        # BRUTTO price line → finalise current product
        m = _BRUTTO_RE.match(clean)
        if m:
            price = float(m.group(1).replace(',', '.'))
            name = re.sub(r'\s+', ' ', ' '.join(name_lines)).strip()

            if name:
                products.append({
                    'name':  name,
                    'qty':   _extract_qty(detail_lines),
                    'price': price,
                })

            name_lines = []
            detail_lines = []
            in_details = False
            continue

        if _is_noise(clean):
            continue

        # Bullet detail lines
        if clean.startswith('•'):
            in_details = True
            # Skip "• cena 1 opak." lines (pricing-unit indicator, not product info)
            if not re.match(r'^•\s*cena\s', clean):
                detail_lines.append(clean)
            continue

        # Pack-quantity lines without bullet prefix (page 1 format):
        # e.g. "1/6 szt. x 150 g", "20 but. x 0,5 l"
        if re.match(r'^\d+[/\d]*\s*(szt|but|opak|rol|pusz)\b', clean, re.I):
            in_details = True
            detail_lines.append('• ' + clean)
            continue

        # Regular text line
        if in_details:
            # We were in details but hit a non-bullet line → start of a new product
            name_lines = [clean]
            detail_lines = []
            in_details = False
        else:
            name_lines.append(clean)

    return products


# ── Dedup & normalise ────────────────────────────────────────────────────────

def _dedup(products):
    """Keep first occurrence of each (name, qty, price) triple."""
    seen = set()
    result = []
    for p in products:
        key = (p['name'].lower(), p['qty'].lower(), p['price'])
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


# ── Public API ───────────────────────────────────────────────────────────────

def parse_leaflet(pdf_path, store='Makro', images_dir=None):
    """
    Parse a Makro leaflet PDF and return a list of deal dicts ready for db.save_deals().
    When images_dir is provided, product images are extracted from the PDF and saved there.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("Failed to open PDF %s: %s", pdf_path, e)
        return []

    raw_products = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()
        page_products = _parse_page(text)

        image_blocks = _extract_image_blocks(page) if images_dir else []

        for p in page_products:
            p['page'] = page_num
            p['category'] = 'Gazetka Makro'

            if image_blocks:
                price_str = f"{p['price']:.2f}".replace('.', ',')
                hits = page.search_for(f"{price_str} BRUTTO")
                if hits:
                    p['_xref'] = _find_product_image(hits[0], image_blocks)

            raw_products.append(p)

    deduped = _dedup(raw_products)
    logger.info("Makro leaflet %s: %d raw → %d after dedup", pdf_path, len(raw_products), len(deduped))

    deals = []
    for p in deduped:
        product_id = f"leaflet-{_slugify(store)}-{_slugify(p['name'])}-{_slugify(p['qty'])}"

        image_url = None
        if images_dir and p.get('_xref'):
            try:
                image_url = _save_image(doc, p['_xref'], images_dir, product_id)
            except Exception as e:
                logger.warning("Image extraction failed for %s: %s", product_id, e)

        deals.append({
            'product_id':   product_id,
            'name':         p['name'],
            'brand':        '',
            'qty':          p['qty'],
            'category':     p['category'],
            'price':        p['price'],
            'old_price':    None,
            'discount_pct': None,
            'promo_label':  None,
            'image_url':    image_url,
            'product_url':  None,
            'source':       'leaflet',
        })

    doc.close()
    return deals


class MakroLeafletScraper(LeafletScraper):
    store_name = 'Makro'

    def parse_leaflet(self, pdf_path):
        return parse_leaflet(pdf_path, store=self.store_name)

    def scrape_latest(self, images_dir=None):
        """Download the current Makro leaflet and parse it."""
        pdf_path = download_latest_leaflet()
        try:
            return parse_leaflet(pdf_path, store=self.store_name, images_dir=images_dir)
        finally:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass
