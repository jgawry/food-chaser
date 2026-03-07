"""
Parse a Lidl promotional leaflet PDF and extract product deals.

Returns a list of dicts compatible with db.save_deals(), with these extra fields:
  brand, qty, source='leaflet'

Deduplication: within a single PDF, (brand, name, qty) triples are unique —
the same item often appears on cover pages AND detail pages.
"""
import logging
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.request

import fitz  # pymupdf

from .lidl import _make_request, _extract_nuxt_data, _HEADERS

logger = logging.getLogger(__name__)

# ── Noise filtering ───────────────────────────────────────────────────────────

_NOISE_EXACT = {
    'Nowa cena', 'regularna', 'ceny', 'Twoje', 'niskie', 'gratis',
    'Rewolucja cenowa!', 'Każdego dnia tanio,', 'także bez promocji.',
    'Oszczędzaj każdego dnia', 'Więcej na lidl.pl',
    'tylko', 'na lidl.pl', 'Miksuj', 'Taniej', 'dowolnie',
    'drugi, tańszy', 'produkt', 'Supercena',
    'Mięso', 'Słodycze', 'Napoje',
}

_NOISE_STARTSWITH = [
    'Lista produktów', 'i u asystenta', 'Artykuły prezentowane',
    'przy produktach lub', 'wyczerpania zapasów', 'Znaki firmowe',
    'Sprawdź nasze', 'tych oraz innych', 'z oznaczeniem', 'na etykietach',
    'From Mon.', 'Szczegóły promocji', 'Aktywuj kupon', 'przy zakupie',
    'Co to jest Nutri', 'uzupełnienie klasycznej', 'jednak, czy dana',
    'Więcej informacji', 'Od czwartku', 'Od pt.,', 'Od sob.,',
    'Tylko w', 'Tylko we', 'Cena poza promocją:', 'Limit:',
    'Promocja nie łączy', 'Kupon będzie', 'pod warunkiem',
    'i odebrania kuponu', '+ kaucja', 'Produkty sprzedawane',
    'Do jednego opakowania', 'Codzienna', 'porcja kolorów',
    'To się opłaca', 'Ośmiosztuk',
]

_NOISE_RE = [
    re.compile(r'^\d+$'),
    re.compile(r'^\d+ \+ \d+'),
    re.compile(r'^\d+% taniej$', re.I),
    re.compile(r'^R \d+/\d+$'),
    re.compile(r'^Od poniedziałku'),
    re.compile(r'^Od środy'),
    re.compile(r'^Od pon\.,'),
    re.compile(r'^Wszystkie '),
    re.compile(r'^\d+ x '),
    re.compile(r'^1 (szt|rolka|L|kg|opak|but|pusz)\. = '),
    re.compile(r'^100 (g|ml) = '),
    re.compile(r'^1 (L|kg) = '),
]


def _is_noise(s):
    if s in _NOISE_EXACT:
        return True
    if any(s.startswith(p) for p in _NOISE_STARTSWITH):
        return True
    return any(p.match(s) for p in _NOISE_RE)


# ── Brand / qty detection ─────────────────────────────────────────────────────

def _is_brand(s):
    if not s or len(s) < 2:
        return False
    alpha = [c for c in s if c.isalpha()]
    if len(alpha) < 2:
        return False
    upper = sum(1 for c in alpha if c == c.upper() and c != c.lower())
    return upper / len(alpha) >= 0.85


_QTY_RE = re.compile(
    r'^\d[\d,\.]*\s*'
    r'(szt\.?|sztuk|L\b|ml\b|g\b|kg\b|rolek|rolka|pusz\.?|opak\.?|but\.?|butel\.?|cm\b|pary|para|kpl\.?)'
    r'(\s|$)',
    re.I,
)

# ── Price patterns ────────────────────────────────────────────────────────────

_DISCOUNT_RE      = re.compile(r'^-(\d+)%$')
_PRICE_RE         = re.compile(r'^(\d+[,\.]\d{2})$')
_OLD_STAR_RE      = re.compile(r'^(\d+[,\.]\d{2})\*$')
_COMPACT_RE       = re.compile(r'^-(\d+)%\s+(\d+[,\.]\d{2})\*$')
_STARA_RE         = re.compile(r'^\* (stara cena|najniższa cena|cena przed)')
_OLD_PRICE_RE     = re.compile(r'(?:przed obniżką|poza promocją):?\s*(?:1 \w+ = )?(\d+[,\.]\d{2})')
_COUPON_ANCHOR_RE = re.compile(r'^Cena poza promocją:', re.I)
_BUY_GET_RE       = re.compile(r'^(\d+)\s*\+\s*(\d+)$')


def _pf(s):
    return float(s.replace(',', '.'))


# ── Page text cleaning ────────────────────────────────────────────────────────

def _clean_lines(text):
    text = text.replace('\xa0', ' ')
    result = []
    for raw in text.split('\n'):
        s = raw.strip()
        if s and not _is_noise(s):
            result.append(s)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _finalize_desc(prod):
    desc = prod.pop('_desc', [])
    if not desc:
        return
    if not prod['qty']:
        qty_idx = None
        for idx in range(len(desc) - 1, -1, -1):
            if _QTY_RE.search(desc[idx]):
                qty_idx = idx
                break
        if qty_idx is not None:
            prod['qty']  = desc[qty_idx]
            prod['name'] = ' '.join(desc[:qty_idx]).strip()
        else:
            prod['name'] = ' '.join(desc).strip()
    elif not prod['name']:
        prod['name'] = ' '.join(desc).strip()


def _extract_old_price(stara_lines):
    joined = ' '.join(stara_lines)
    m = _OLD_PRICE_RE.search(joined)
    return _pf(m.group(1)) if m else None


# ── Price block parsers ───────────────────────────────────────────────────────

def _try_parse_price_block(lines, i):
    """Single inline price block. Returns (disc, new, old, next_i) or None."""
    n = len(lines)
    if i >= n:
        return None

    if _PRICE_RE.match(lines[i]):
        new_price = _pf(_PRICE_RE.match(lines[i]).group(1))
        if i + 1 < n:
            m = _COMPACT_RE.match(lines[i + 1])
            if m:
                return int(m.group(1)), new_price, _pf(m.group(2)), i + 2
            m2 = _OLD_STAR_RE.match(lines[i + 1])
            if m2:
                return None, new_price, _pf(m2.group(1)), i + 2

    if _DISCOUNT_RE.match(lines[i]):
        disc = int(_DISCOUNT_RE.match(lines[i]).group(1))
        if i + 1 < n and _PRICE_RE.match(lines[i + 1]) and not _DISCOUNT_RE.match(lines[i + 1]):
            if i + 2 < n and _OLD_STAR_RE.match(lines[i + 2]):
                return disc, _pf(_PRICE_RE.match(lines[i + 1]).group(1)), _pf(_OLD_STAR_RE.match(lines[i + 2]).group(1)), i + 3

    return None


def _collect_grouped_prices(lines, i):
    """
    Grouped format: N discount lines, then N price lines, then N old-price lines.
    Returns (list_of_(disc,new,old), next_i) or ([], i).
    """
    n = len(lines)
    j = i

    discounts = []
    while j < n and _DISCOUNT_RE.match(lines[j]):
        discounts.append(int(_DISCOUNT_RE.match(lines[j]).group(1)))
        j += 1

    if len(discounts) < 2:
        return [], i

    prices = []
    while j < n and _PRICE_RE.match(lines[j]):
        prices.append(_pf(_PRICE_RE.match(lines[j]).group(1)))
        j += 1

    old_prices = []
    while j < n and _OLD_STAR_RE.match(lines[j]):
        old_prices.append(_pf(_OLD_STAR_RE.match(lines[j]).group(1)))
        j += 1

    if not prices or not old_prices:
        return [], i

    return [(d, p, op) for d, p, op in zip(discounts, prices, old_prices)], j


# ── Coupon / app-deal parser ──────────────────────────────────────────────────

_COUPON_STOP_STARTS = (
    'Tylko w', 'Tylko we', 'Od pon', 'Od czw', 'Od pt', 'Od sob',
    'Lista ', 'Aktywuj kupon',
)


def _parse_coupon_page(text):
    """
    Parse 'N + M gratis' app-coupon deals anchored on 'Cena poza promocją:'.
    Operates on raw (uncleaned) page text so the anchor lines aren't filtered.
    Returns list of product dicts (same schema as _parse_page output).
    """
    text = text.replace('\xa0', ' ')
    raw = [l.strip() for l in text.split('\n') if l.strip()]
    n = len(raw)
    deals = []
    i = 0

    while i < n:
        if not _COUPON_ANCHOR_RE.match(raw[i]):
            i += 1
            continue

        # ── Backtrack to collect product description ──
        j = i - 1
        # Skip tail lines of any preceding deal
        while j >= 0 and (
            raw[j] == 'gratis'
            or _BUY_GET_RE.match(raw[j])
            or _PRICE_RE.match(raw[j])
        ):
            j -= 1

        desc = []
        while j >= 0:
            l = raw[j]
            if any(l.startswith(p) for p in _COUPON_STOP_STARTS):
                break
            if _COUPON_ANCHOR_RE.match(l):
                break
            # Stop at regular-deal price lines so we don't bleed into adjacent deals
            if _OLD_STAR_RE.match(l) or _PRICE_RE.match(l) or _STARA_RE.match(l):
                break
            if re.match(r'^\d+%', l):
                break
            desc.insert(0, l)
            j -= 1

        # Parse brand / name / qty out of desc
        brand, name, qty = '', '', ''
        if desc:
            idx = 0
            if _is_brand(desc[0]):
                brand = desc[0]
                idx = 1
            qty_idx = None
            for k in range(len(desc) - 1, idx - 1, -1):
                if _QTY_RE.search(desc[k]):
                    qty_idx = k
                    break
            if qty_idx is not None:
                name = ' '.join(desc[idx:qty_idx]).strip()
                qty  = desc[qty_idx]
            else:
                name = ' '.join(desc[idx:]).strip()

        # ── Scan forward for price then 'N + M' ──
        k = i + 1
        price = None
        buy_n = get_m = None

        while k < n:
            l = raw[k]
            if _PRICE_RE.match(l):
                price = _pf(_PRICE_RE.match(l).group(1))
                k += 1
                if k < n and _BUY_GET_RE.match(raw[k]):
                    m = _BUY_GET_RE.match(raw[k])
                    buy_n, get_m = int(m.group(1)), int(m.group(2))
                break
            # Stop if we hit another anchor or next product start
            if _COUPON_ANCHOR_RE.match(l) or _is_brand(l):
                break
            k += 1

        if price is not None and name and buy_n is not None:
            disc = round(get_m / (buy_n + get_m) * 100)
            deals.append({
                'brand':        brand,
                'name':         name,
                'qty':          qty,
                'new_price':    price,
                'old_price':    None,
                'discount_pct': disc,
                'buy_n':        buy_n,
                'get_m':        get_m,
            })

        i = k + 1

    return deals


# ── Core page parser ──────────────────────────────────────────────────────────

def _parse_page(lines):
    products = []
    orphans  = []
    floaters = []

    i = 0
    n = len(lines)

    def current_prod():
        return products[-1] if products and '_desc' in products[-1] else None

    while i < n:
        line = lines[i]

        if _STARA_RE.match(line):
            stara = [line]
            i += 1
            while i < n:
                peek = lines[i]
                if _is_brand(peek) or _STARA_RE.match(peek):
                    break
                if _DISCOUNT_RE.match(peek) or _PRICE_RE.match(peek) or _COMPACT_RE.match(peek):
                    break
                stara.append(peek)
                i += 1

            old_price = _extract_old_price(stara)
            prod = current_prod()

            result = _try_parse_price_block(lines, i)
            if result:
                disc, new_price, old_from_block, i = result
                if prod:
                    _finalize_desc(prod)
                    prod['discount_pct'] = disc
                    prod['new_price']    = new_price
                    prod['old_price']    = old_price or old_from_block
            else:
                if prod:
                    _finalize_desc(prod)
                    prod['old_price'] = old_price
                    orphans.append(prod)

        elif _is_brand(line):
            brand_parts = [line]
            i += 1
            while i < n and _is_brand(lines[i]) and not _STARA_RE.match(lines[i]):
                brand_parts.append(lines[i])
                i += 1
            products.append({
                'brand':        ' '.join(brand_parts),
                'name':         '',
                'qty':          '',
                '_desc':        [],
                'old_price':    None,
                'new_price':    None,
                'discount_pct': None,
            })

        elif current_prod() is not None:
            prod = current_prod()
            desc = prod['_desc']
            desc.append(line)
            if _QTY_RE.search(line) and not prod['qty']:
                prod['qty']  = line
                prod['name'] = ' '.join(desc[:-1]).strip()
            i += 1

        else:
            clusters, new_i = _collect_grouped_prices(lines, i)
            if clusters:
                for disc, new_price, old_price in clusters:
                    floaters.append({'discount_pct': disc, 'new_price': new_price, 'old_price': old_price})
                i = new_i
            else:
                result = _try_parse_price_block(lines, i)
                if result:
                    disc, new_price, old_price, i = result
                    floaters.append({'discount_pct': disc, 'new_price': new_price, 'old_price': old_price})
                else:
                    i += 1

    for prod in products:
        if '_desc' in prod:
            prod.pop('_desc')

    used = set()
    for prod in orphans:
        op = prod.get('old_price')
        if op is None:
            continue
        for j, fl in enumerate(floaters):
            if j in used:
                continue
            if fl['old_price'] is not None and abs(fl['old_price'] - op) < 0.01:
                prod['new_price']    = fl['new_price']
                prod['discount_pct'] = fl['discount_pct']
                used.add(j)
                break

    return [p for p in products if p['new_price'] is not None and p['name']]


# ── Dedup & normalise ─────────────────────────────────────────────────────────

def _slugify(text):
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode()
    text = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return text


def _dedup(products):
    """Keep first occurrence of each (category, brand, name, qty) tuple."""
    seen = set()
    result = []
    for p in products:
        key = (p.get('category', ''), p['brand'].lower(), p['name'].lower(), p['qty'].lower())
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


# ── Auto-download: find & fetch the latest Lidl leaflet PDF ──────────────────

_GAZETKI_URL  = "https://www.lidl.pl/c/nasze-gazetki/s10008614"
_PDF_BASE_URL = "https://object.storage.eu01.onstackit.cloud/leaflets/pdfs"


def _slugify_pdf(text: str) -> str:
    """Normalise a leaflet title to the uppercase-hyphen filename style used by onstackit."""
    import html as _html
    text = _html.unescape(text)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[\s.]+', '-', text.upper())
    text = re.sub(r'-+', '-', text).strip('-')
    return text


def _fetch_latest_pdf_url() -> str:
    """
    Return the direct PDF download URL for the current Lidl leaflet.

    Strategy:
      1. Fetch the gazetki listing page and extract UUID + title of the first flyer
         from its data-track-id / data-track-name / .flyer__title attributes.
      2. Construct the base filename from the slugified name + title.
      3. Probe onstackit storage with HEAD requests for suffixes 1–30 until
         a 200 is found (the suffix appears to be the page count).
    """
    import html as _html

    listing_html = _make_request(_GAZETKI_URL)

    # ── Extract first flyer block ──────────────────────────────────
    flyer_m = re.search(r'<a[^>]+class="flyer"[^>]+>.*?</a>', listing_html, re.DOTALL)
    if not flyer_m:
        raise RuntimeError("Could not find any flyer block on gazetki listing page")
    flyer_html = flyer_m.group(0)

    uuid_m  = re.search(r'data-track-id="([0-9a-f-]+)"', flyer_html)
    name_m  = re.search(r'data-track-name="([^"]+)"', flyer_html)
    title_m = re.search(r'class="flyer__title"[^>]*>\s*([^<]+)', flyer_html)

    if not uuid_m or not name_m:
        raise RuntimeError("Could not extract UUID or name from first flyer block")

    uuid  = uuid_m.group(1)
    name  = _html.unescape(name_m.group(1))
    title = title_m.group(1).strip() if title_m else ''

    base_name = _slugify_pdf(f"{name} {title}".strip())
    logger.info("Leaflet UUID=%s  base_name=%s", uuid, base_name)

    # ── Probe for numeric suffix (page count) ─────────────────────
    for n in range(1, 31):
        url = f"{_PDF_BASE_URL}/{uuid}/{base_name}-{n}.pdf"
        try:
            req = urllib.request.Request(url, headers=_HEADERS, method='HEAD')
            with urllib.request.urlopen(req, timeout=8) as r:
                if r.status == 200:
                    logger.info("Found PDF at suffix %d: %s", n, url)
                    return url
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        except Exception:
            raise

    raise RuntimeError(
        f"Could not find PDF for UUID={uuid} base_name={base_name} (tried suffixes 1–30)"
    )


def download_latest_leaflet() -> str:
    """
    Download the current Lidl leaflet PDF to a temp file.
    Returns the path to the downloaded file (caller must delete it).
    """
    pdf_url = _fetch_latest_pdf_url()
    filename = pdf_url.split('/')[-1].split('?')[0] or 'lidl_leaflet.pdf'
    tmp_path = os.path.join(tempfile.gettempdir(), filename)

    req = urllib.request.Request(pdf_url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        with open(tmp_path, 'wb') as f:
            f.write(r.read())

    logger.info("Downloaded latest leaflet to %s", tmp_path)
    return tmp_path


# ── Public API ────────────────────────────────────────────────────────────────

def parse_leaflet(pdf_path: str, store: str = 'Lidl') -> list[dict]:
    """
    Parse a leaflet PDF and return a list of deal dicts ready for db.save_deals().

    Each dict contains:
      product_id, name, brand, qty, category, price, old_price,
      discount_pct, image_url, product_url, source
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("Failed to open PDF %s: %s", pdf_path, e)
        return []

    raw_products = []
    for page_num, page in enumerate(doc, start=1):
        raw_text = page.get_text()
        lines = _clean_lines(raw_text)
        for p in _parse_page(lines):
            p['page']     = page_num
            p['category'] = 'Gazetka'
            raw_products.append(p)
        for p in _parse_coupon_page(raw_text):
            p['page']     = page_num
            p['category'] = 'Kupon'
            raw_products.append(p)

    deduped = _dedup(raw_products)
    logger.info("Leaflet %s: %d raw → %d after dedup", pdf_path, len(raw_products), len(deduped))

    deals = []
    for p in deduped:
        product_id = f"leaflet-{_slugify(store)}-{_slugify(p['brand'])}-{_slugify(p['name'])}-{_slugify(p['qty'])}"
        promo_label = None
        if 'buy_n' in p:
            promo_label = f"{p['buy_n']}+{p['get_m']} gratis z aplikacją"
        deals.append({
            'product_id':   product_id,
            'name':         p['name'],
            'brand':        p['brand'],
            'qty':          p['qty'],
            'category':     p['category'],
            'price':        p['new_price'],
            'old_price':    p['old_price'],
            'discount_pct': p['discount_pct'],
            'promo_label':  promo_label,
            'image_url':    None,
            'product_url':  None,
            'source':       'leaflet',
        })

    return deals


from .base import LeafletScraper


class LidlLeafletScraper(LeafletScraper):
    store_name = 'Lidl'

    def parse_leaflet(self, pdf_path: str) -> list[dict]:
        return parse_leaflet(pdf_path, store=self.store_name)

    def scrape_latest(self) -> list[dict]:
        """Download the current Lidl leaflet and parse it."""
        pdf_path = download_latest_leaflet()
        try:
            return parse_leaflet(pdf_path, store=self.store_name)
        finally:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass
