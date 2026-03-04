#!/usr/bin/env python3
"""Test script: extract product deals from a Lidl leaflet PDF."""
import re, sys, json
import fitz  # pymupdf

sys.stdout.reconfigure(encoding='utf-8')

PDF_PATH = 'resources/leaflet.pdf'

# ── Noise filtering ───────────────────────────────────────────────────────────

NOISE_EXACT = {
    'Nowa cena', 'regularna', 'ceny', 'Twoje', 'niskie', 'gratis',
    'Rewolucja cenowa!', 'Każdego dnia tanio,', 'także bez promocji.',
    'Oszczędzaj każdego dnia', 'Więcej na lidl.pl',
    'tylko', 'na lidl.pl', 'Miksuj', 'Taniej', 'dowolnie',
    'drugi, tańszy', 'produkt', 'Supercena',
    'Mięso', 'Słodycze', 'Napoje',
}

NOISE_STARTSWITH = [
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

NOISE_RE = [
    re.compile(r'^\d+$'),               # standalone page numbers
    re.compile(r'^\d+ \+ \d+'),         # "1 + 1"
    re.compile(r'^\d+% taniej$', re.I), # "30% taniej"
    re.compile(r'^R \d+/\d+$'),         # "R 10/26"
    re.compile(r'^Od poniedziałku'),
    re.compile(r'^Od środy'),
    re.compile(r'^Od pon\.,'),
    re.compile(r'^Wszystkie '),
    re.compile(r'^\d+ x '),             # "8 x 3,19 zł"
    re.compile(r'^1 (szt|rolka|L|kg|opak|but|pusz)\. = '),  # unit price lines e.g. "1 szt. = 0,44"
    re.compile(r'^100 (g|ml) = '),      # "100 g = 3,47"
    re.compile(r'^1 (L|kg) = '),        # "1 L = 51,98"
]

def is_noise(s):
    if s in NOISE_EXACT: return True
    if any(s.startswith(p) for p in NOISE_STARTSWITH): return True
    return any(p.match(s) for p in NOISE_RE)

# ── Brand detection ───────────────────────────────────────────────────────────

def is_brand(s):
    """True if line looks like an ALL-CAPS brand name."""
    if not s or len(s) < 2: return False
    alpha = [c for c in s if c.isalpha()]
    if len(alpha) < 2: return False
    upper = sum(1 for c in alpha if c == c.upper() and c != c.lower())
    return upper / len(alpha) >= 0.85

# ── Price / quantity patterns ─────────────────────────────────────────────────

DISCOUNT_RE   = re.compile(r'^-(\d+)%$')
PRICE_RE      = re.compile(r'^(\d+[,\.]\d{2})$')
OLD_STAR_RE   = re.compile(r'^(\d+[,\.]\d{2})\*$')
COMPACT_RE    = re.compile(r'^-(\d+)%\s+(\d+[,\.]\d{2})\*$')   # "-13% 29,99*"
STARA_CENA_RE = re.compile(r'^\* (stara cena|najniższa cena|cena przed)')
OLD_PRICE_RE  = re.compile(r'(?:przed obniżką|poza promocją):?\s*(?:1 \w+ = )?(\d+[,\.]\d{2})')

QTY_RE = re.compile(
    r'^\d[\d,\.]*\s*'
    r'(szt\.?|sztuk|L\b|ml\b|g\b|kg\b|rolek|rolka|pusz\.?|opak\.?|but\.?|butel\.?|cm\b|pary|para|kpl\.?)'
    r'(\s|$)',
    re.I
)

def pf(s): return float(s.replace(',', '.'))

# ── Page cleaning ─────────────────────────────────────────────────────────────

def clean_lines(text):
    # Replace non-breaking spaces
    text = text.replace('\xa0', ' ')
    result = []
    for raw in text.split('\n'):
        s = raw.strip()
        if s and not is_noise(s):
            result.append(s)
    return result

# ── Helper: finalize name/qty from accumulated _desc lines ───────────────────

def finalize_desc(prod):
    """Set name and qty from _desc if not already set, then remove _desc."""
    desc = prod.pop('_desc', [])
    if not desc:
        return
    if not prod['qty']:
        # Find last line that looks like a quantity; everything before it is the name
        qty_idx = None
        for idx in range(len(desc) - 1, -1, -1):
            if QTY_RE.search(desc[idx]):
                qty_idx = idx
                break
        if qty_idx is not None:
            prod['qty']  = desc[qty_idx]
            prod['name'] = ' '.join(desc[:qty_idx]).strip()
        else:
            # No qty found — treat all lines as name
            prod['name'] = ' '.join(desc).strip()
    elif not prod['name']:
        prod['name'] = ' '.join(desc).strip()

# ── Price block parser ────────────────────────────────────────────────────────

def try_parse_price_block(lines, i):
    """
    Try to parse a single inline price block starting at lines[i].
    Returns (discount_pct_or_None, new_price, old_price, next_i) or None.

    Formats:
      A) NEW  \\n  -XX% OLD*     (compact)
      B) -XX% \\n  NEW  \\n  OLD* (expanded, only 1 discount line)
      C) NEW  \\n  OLD*           (no explicit discount)
    """
    n = len(lines)
    if i >= n:
        return None

    # Format A / C: starts with a plain price
    if PRICE_RE.match(lines[i]):
        new_price = pf(PRICE_RE.match(lines[i]).group(1))
        if i + 1 < n:
            m = COMPACT_RE.match(lines[i + 1])
            if m:
                return int(m.group(1)), new_price, pf(m.group(2)), i + 2
            m2 = OLD_STAR_RE.match(lines[i + 1])
            if m2:
                return None, new_price, pf(m2.group(1)), i + 2

    # Format B: exactly one discount line followed by price + old*
    if DISCOUNT_RE.match(lines[i]):
        disc = int(DISCOUNT_RE.match(lines[i]).group(1))
        # Make sure next line is a price (not another discount — that's grouped format)
        if i + 1 < n and PRICE_RE.match(lines[i + 1]) and not DISCOUNT_RE.match(lines[i + 1]):
            if i + 2 < n and OLD_STAR_RE.match(lines[i + 2]):
                return disc, pf(PRICE_RE.match(lines[i + 1]).group(1)), pf(OLD_STAR_RE.match(lines[i + 2]).group(1)), i + 3

    return None


def collect_grouped_prices(lines, i):
    """
    Parse a grouped price cluster where all discounts come first, then all
    new prices, then all old prices (e.g. page 7 layout):
      -27%
      -20%
      13,99
      6,49
      19,24*
      8,19*
    Returns (list_of_(disc,new,old), next_i) or ([], i).
    """
    n = len(lines)
    j = i

    discounts = []
    while j < n and DISCOUNT_RE.match(lines[j]):
        discounts.append(int(DISCOUNT_RE.match(lines[j]).group(1)))
        j += 1

    if len(discounts) < 2:  # single discount handled by try_parse_price_block
        return [], i

    prices = []
    while j < n and PRICE_RE.match(lines[j]):
        prices.append(pf(PRICE_RE.match(lines[j]).group(1)))
        j += 1

    old_prices = []
    while j < n and OLD_STAR_RE.match(lines[j]):
        old_prices.append(pf(OLD_STAR_RE.match(lines[j]).group(1)))
        j += 1

    if not prices or not old_prices:
        return [], i

    result = [(d, p, op) for d, p, op in zip(discounts, prices, old_prices)]
    return result, j

def extract_old_price(stara_lines):
    joined = ' '.join(stara_lines)
    m = OLD_PRICE_RE.search(joined)
    return pf(m.group(1)) if m else None

# ── Core page parser ──────────────────────────────────────────────────────────

def parse_page(lines):
    products = []
    orphans  = []   # products awaiting price match
    floaters = []   # price blocks without a product context

    i = 0
    n = len(lines)

    def current_prod():
        return products[-1] if products and '_desc' in products[-1] else None

    while i < n:
        line = lines[i]

        # ── stara cena anchor ──────────────────────────────────────────────
        if STARA_CENA_RE.match(line):
            stara = [line]
            i += 1
            while i < n:
                peek = lines[i]
                if is_brand(peek) or STARA_CENA_RE.match(peek):
                    break
                if DISCOUNT_RE.match(peek) or PRICE_RE.match(peek) or COMPACT_RE.match(peek):
                    break
                stara.append(peek)
                i += 1

            old_price = extract_old_price(stara)
            prod = current_prod()

            result = try_parse_price_block(lines, i)
            if result:
                disc, new_price, old_from_block, i = result
                if prod:
                    finalize_desc(prod)
                    prod['discount_pct'] = disc
                    prod['new_price']    = new_price
                    prod['old_price']    = old_price or old_from_block
            else:
                if prod:
                    finalize_desc(prod)
                    prod['old_price'] = old_price
                    orphans.append(prod)

        # ── brand line → new product ───────────────────────────────────────
        elif is_brand(line):
            brand_parts = [line]
            i += 1
            while i < n and is_brand(lines[i]) and not STARA_CENA_RE.match(lines[i]):
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

        # ── accumulate lines into current product ──────────────────────────
        elif current_prod() is not None:
            prod = current_prod()
            desc = prod['_desc']
            desc.append(line)
            # Eagerly detect qty to set name early
            if QTY_RE.search(line) and not prod['qty']:
                prod['qty']  = line
                prod['name'] = ' '.join(desc[:-1]).strip()
            i += 1

        # ── floating price block ───────────────────────────────────────────
        else:
            # Try grouped format first (multiple discounts stacked)
            clusters, new_i = collect_grouped_prices(lines, i)
            if clusters:
                for disc, new_price, old_price in clusters:
                    floaters.append({'discount_pct': disc, 'new_price': new_price, 'old_price': old_price})
                i = new_i
            else:
                result = try_parse_price_block(lines, i)
                if result:
                    disc, new_price, old_price, i = result
                    floaters.append({'discount_pct': disc, 'new_price': new_price, 'old_price': old_price})
                else:
                    i += 1

    # Finalize any product still accumulating (end of page without stara cena)
    for prod in products:
        if '_desc' in prod:
            prod.pop('_desc')

    # Match orphans to floaters by old_price
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

    # Keep only products that have a price and a name
    return [p for p in products if p['new_price'] is not None and p['name']]


# ── PDF entry point ───────────────────────────────────────────────────────────

def parse_pdf(path):
    doc = fitz.open(path)
    all_products = []
    for page_num, page in enumerate(doc, start=1):
        lines = clean_lines(page.get_text())
        products = parse_page(lines)
        for p in products:
            p['page'] = page_num
        all_products.extend(products)
    return all_products


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    products = parse_pdf(PDF_PATH)

    print(f"Total products parsed: {len(products)}")
    print()
    print(f"{'Pg':>2}  {'Brand':<26} {'Name':<38} {'Qty':<12} {'Price':>7}  {'Old':>7}  {'Disc':>5}")
    print('-' * 105)
    for p in products:
        disc = f"-{p['discount_pct']}%" if p['discount_pct'] else '  n/a'
        old  = f"{p['old_price']:.2f}" if p['old_price'] else '   n/a'
        print(f"{p['page']:>2}  {p['brand']:<26} {p['name']:<38} {p['qty']:<12} "
              f"{p['new_price']:>7.2f}  {old:>7}  {disc:>5}")

    with open('resources/parsed_deals.json', 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to resources/parsed_deals.json")
