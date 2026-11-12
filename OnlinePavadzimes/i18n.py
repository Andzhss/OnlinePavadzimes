# Dokumentu teksti latviešu un angļu valodā.
# Iekšēji doc_type vienmēr glabājas latviski (vēsturei), tulkojam tikai attēlošanai.

LANGUAGES = {"Latviešu": "lv", "English": "en"}

LABELS = {
    'lv': {
        'nr':               "Nr.",
        'date':             "Datums",
        'due_date':         "Apmaksāt līdz",
        'client':           "KLIENTS",
        'address':          "Adrese",
        'reg_no':           "Reģ. Nr.",
        'vat_no':           "PVN Nr.",
        'phone':            "Tālrunis",
        'bank_account':     "Bankas konta numurs",
        'seller_address':   ["Ķekavas nov., Ķekava,", "Dārzenieku iela 42, LV-2123"],
        'receiver':         "Saņēmējs",
        'customer':         "Pasūtītājs",
        'sender':           "Nosūtītājs",
        'legal_address':    "Juridiskā adrese",
        'col_name':         "NOSAUKUMS",
        'col_unit':         "Mērvienība",
        'col_qty':          "DAUDZUMS",
        'col_price':        "CENA (EUR)",
        'col_total':        "KOPĀ (EUR)",
        'subtotal':         "KOPĀ",
        'subtotal_pre':     "KOPĀ (bez PVN un atlaides)",
        'discount':         "Atlaides apjoms",
        'after_discount':   "Kopā ar atlaidi (bez PVN)",
        'vat':              "PVN",
        'total':            "Kopumā",
        'total_due':        "KOPUMĀ APMAKSAI",
        'advance_due':      "APMAKSĀJAMAIS AVANSS",
        'in_words':         "Vārdiem: ",
        'comments':         "Papildus informācija:",
        'prepared': {
            'pavadzīme':     "Pavadzīmi sagatavoja:",
            'avansa rēķins': "Avansa rēķinu sagatavoja:",
            'rēķins':        "Rēķinu sagatavoja:",
        },
        'received': {
            'pavadzīme':     "Pavadzīmi saņēma:",
            'avansa rēķins': "Avansa rēķinu saņēma:",
            'rēķins':        "Rēķinu saņēma:",
        },
        'default_title':    "valdes loceklis",
    },
    'en': {
        'nr':               "No.",
        'date':             "Date",
        'due_date':         "Due date",
        'client':           "CLIENT",
        'address':          "Address",
        'reg_no':           "Reg. No.",
        'vat_no':           "VAT No.",
        'phone':            "Phone",
        'bank_account':     "Bank account (IBAN)",
        'seller_address':   ["Dārzenieku iela 42, Ķekava,", "Ķekavas nov., LV-2123, Latvia"],
        'receiver':         "Recipient",
        'customer':         "Customer",
        'sender':           "Sender",
        'legal_address':    "Legal address",
        'col_name':         "DESCRIPTION",
        'col_unit':         "Unit",
        'col_qty':          "QUANTITY",
        'col_price':        "PRICE (EUR)",
        'col_total':        "AMOUNT (EUR)",
        'subtotal':         "SUBTOTAL",
        'subtotal_pre':     "SUBTOTAL (excl. VAT and discount)",
        'discount':         "Discount",
        'after_discount':   "Subtotal after discount (excl. VAT)",
        'vat':              "VAT",
        'total':            "Total",
        'total_due':        "TOTAL DUE",
        'advance_due':      "ADVANCE PAYMENT DUE",
        'in_words':         "In words: ",
        'comments':         "Additional information:",
        'prepared': {
            'pavadzīme':     "Delivery note prepared by:",
            'avansa rēķins': "Advance invoice prepared by:",
            'rēķins':        "Invoice prepared by:",
        },
        'received': {
            'pavadzīme':     "Delivery note received by:",
            'avansa rēķins': "Advance invoice received by:",
            'rēķins':        "Invoice received by:",
        },
        'default_title':    "Board Member",
    },
}

DOC_TYPES_EN = {
    "Pavadzīme":               "Delivery Note",
    "Rēķins":                  "Invoice",
    "Avansa rēķins":           "Advance Invoice",
    "E-rēķins":                "E-Invoice",
    "Proformas pavadzīme":     "Proforma Delivery Note",
    "Proformas rēķins":        "Proforma Invoice",
    "Proformas avansa rēķins": "Proforma Advance Invoice",
}


def labels(lang):
    return LABELS.get(lang, LABELS['lv'])


def doc_type_label(doc_type, lang):
    if lang == 'en':
        return DOC_TYPES_EN.get(doc_type, doc_type)
    return doc_type


def signature_texts(doc_type, lang):
    L = labels(lang)
    dt = doc_type.lower()
    key = 'pavadzīme' if 'pavadzīme' in dt else ('avansa rēķins' if 'avansa rēķins' in dt else 'rēķins')
    return L['prepared'][key], L['received'][key]


def totals_rows(data):
    """Kopsummu rindas [(label, value_str)] — pēdējā ir apmaksājamā summa.
    Ja PVN nav piemērots, PVN rinda paliek ar 0% un 0,00."""
    L = labels(data.get('lang', 'lv'))
    vat_rate = data.get('vat_rate', 21) if data.get('vat_enabled', True) else 0
    subtotal = data.get('subtotal', '0.00')
    total = data.get('total', '0.00')
    vat_row = (f"{L['vat']} ({vat_rate:g}%)", f"{data.get('vat', '0.00')} €")
    if data.get('raw_discount_eur', 0.0) > 0:
        return [
            (L['subtotal_pre'], f"{subtotal} €"),
            (f"{L['discount']} ({data.get('discount_percent', 0):g}%)", f"-{data.get('discount_eur', '0.00')} €"),
            (L['after_discount'], f"{data.get('subtotal_after_discount', '0.00')} €"),
            vat_row,
            (L['total_due'], f"{total} €"),
        ]
    return [
        (L['subtotal'], f"{subtotal} €"),
        vat_row,
        (L['total'], f"{total} €"),
    ]
