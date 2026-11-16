"""SIA Bratus rēķinu MCP serveris — ļauj Claude sagatavot un izrakstīt pavadzīmes/rēķinus.

Darbojas uz Thinkpad blakus Streamlit formai un lieto tos pašus datus (invoice_core).
Palaišana: PAVADZ_DATA_DIR=/opt/pavadzimes/data python mcp_server.py
"""
import datetime
import hashlib
import hmac
import os
import secrets
from typing import Literal

from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import invoice_core as core
from utils import scrape_lursoft

HOST = os.environ.get("PAVADZ_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("PAVADZ_MCP_PORT", "8787"))
PUBLIC_URL = os.environ.get("PAVADZ_PUBLIC_URL", f"http://127.0.0.1:{PORT}").rstrip("/")
ALLOWED_HOSTS = [h for h in os.environ.get("PAVADZ_ALLOWED_HOSTS", "").split(",") if h]
# Publiskā instance (Cloudflare tunelis, claude.ai) prasa OAuth pieteikšanos ar paroli.
PUBLIC_AUTH = os.environ.get("PAVADZ_PUBLIC_AUTH") == "1"

INSTRUCTIONS = """SIA Bratus (Latvija) pavadzīmju un rēķinu izrakstīšana.

Darba kārtība, kad lietotājs lūdz uztaisīt rēķinu/pavadzīmi:
1. Atrodi klientu ar find_clients. Ja tā nav, prasi rekvizītus vai Lursoft saiti (lursoft_company).
2. Cenas un nosaukumus, ja lietotājs tos nedod, meklē find_past_items — bet nekad neizdomā cenu.
3. Izsauc preview_invoice un parādi lietotājam: tipu, klientu, rindas, summas, PVN, valodu, numuru.
4. Tikai pēc lietotāja skaidra apstiprinājuma izsauc create_invoice ar TIEM PAŠIEM parametriem.
create_invoice piešķir nākamo BR numuru un ieraksta grāmatvedības vēsturē — numerācijā
nedrīkst būt caurumu, tāpēc nekad neizsauc to "testam". Testam lieto proforma=true.
Summas ir EUR. Cenas ir bez PVN; PVN 21% tiek pieskaitīts, ja vat_enabled=true."""

security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", *ALLOWED_HOSTS],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", *[f"https://{h}" for h in ALLOWED_HOSTS]],
)

auth_kwargs = {}
oauth = None
if PUBLIC_AUTH:
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    from mcp_auth import PasswordOAuthProvider
    password = os.environ.get("PAVADZ_PASSWORD", "")
    if len(password) < 10:
        raise SystemExit("PAVADZ_PASSWORD nav uzstādīta (vismaz 10 simboli)")
    oauth = PasswordOAuthProvider(core.DATA_DIR, password, PUBLIC_URL)
    auth_kwargs = dict(
        auth_server_provider=oauth,
        auth=AuthSettings(
            issuer_url=PUBLIC_URL,
            resource_server_url=f"{PUBLIC_URL}/mcp",
            validate_token_resource=False,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        ),
    )

mcp = MCPServer("pavadzimes", instructions=INSTRUCTIONS, **auth_kwargs)


def _docs_secret():
    path = os.path.join(core.DATA_DIR, ".docs_secret")
    if not os.path.exists(path):
        os.makedirs(core.DATA_DIR, exist_ok=True)
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    with open(path) as f:
        return f.read().strip().encode()


def _sig(name):
    return hmac.new(_docs_secret(), name.encode(), hashlib.sha256).hexdigest()[:32]


def doc_url(name):
    """Lejupielādes saite ar parakstu — faila nosaukumu (BR numuru) uzminēt nepietiek."""
    return f"{PUBLIC_URL}/docs/{_sig(name)}/{name}"


class Client(BaseModel):
    name: str = Field(description="Uzņēmuma nosaukums, piem. 'SIA Kaktus'")
    address: str = Field("", description="Juridiskā adrese")
    reg_no: str = Field("", description="Reģistrācijas numurs")
    vat_no: str = Field("", description="PVN maksātāja numurs (piem. LV40203628316); '-' ja nav")


class Item(BaseModel):
    name: str = Field(description="Preces/pakalpojuma nosaukums, kā tas būs dokumentā")
    qty: float = Field(gt=0, description="Daudzums")
    price: float = Field(ge=0, description="Vienības cena EUR BEZ PVN")
    unit: str = Field("Gab.", description="Mērvienība, piem. 'Gab.', 'st.', 'pcs'")


class InvoiceRequest(BaseModel):
    doc_type: Literal["Pavadzīme", "Rēķins", "Avansa rēķins"] = "Rēķins"
    client: Client
    items: list[Item] = Field(min_length=1)
    language: Literal["lv", "en"] = Field("lv", description="Dokumenta valoda")
    vat_enabled: bool = Field(True, description="false = PVN 0% (piem. ES reverse charge)")
    vat_note: str = Field("", description="Pamatojums, kāpēc PVN nepiemēro; tiek izdrukāts, ja vat_enabled=false")
    discount_percent: float = Field(0, ge=0, le=100)
    advance_percent: float = Field(50, gt=0, le=100, description="Tikai Avansa rēķinam")
    date: str = Field("", description="dd.mm.yyyy; tukšs = šodien")
    due_days: int = Field(7, ge=0, description="Apmaksas termiņš dienās no datuma")
    comments: str = Field("", description="Papildus informācija dokumentā")
    signatory: Literal["Adrians Stankevičs", "Rihards Ozoliņš", "Ēriks Ušackis", "Aleks Kristiāns Grīnbergs"] = "Adrians Stankevičs"
    signatory_title: str = Field("", description="Amats; tukšs = 'valdes loceklis' / 'Board Member'")
    proforma: bool = Field(False, description="Proformas (testa) dokuments: neiet grāmatvedības vēsturē un Drive")


def _parse_date(s):
    return datetime.datetime.strptime(s.strip(), "%d.%m.%Y").date() if s and s.strip() else None


def _build(req: InvoiceRequest, doc_id: str):
    return core.build_invoice_data(
        doc_type=req.doc_type, doc_id=doc_id, client=req.client.model_dump(),
        items=[i.model_dump() for i in req.items], lang=req.language,
        vat_enabled=req.vat_enabled, vat_note=req.vat_note,
        discount_percent=req.discount_percent, advance_percent=req.advance_percent,
        date=_parse_date(req.date), due_days=req.due_days, comments=req.comments,
        signatory=req.signatory, signatory_title=req.signatory_title, proforma=req.proforma,
    )


def _summary(d):
    out = {
        'numurs': d['doc_id'], 'tips': d['doc_type'], 'valoda': d['lang'],
        'datums': d['date'], 'apmaksat_lidz': d['due_date'],
        'klients': {k: d[f'client_{k}'] for k in ('name', 'address', 'reg_no', 'vat_no')},
        'rindas': [{'nosaukums': i['name'], 'daudzums': i['raw_qty'], 'mervieniba': i['unit'],
                    'cena': i['price'], 'kopa': i['total']} for i in d['items']],
        'kopa_bez_pvn': d['subtotal'],
        'pvn': f"{d['vat']} ({core.VAT_RATE if d['vat_enabled'] else 0}%)",
        'kopuma_apmaksai': d['total'],
        'vardiem': d['amount_words'],
        'parakstitajs': d['signatory'],
    }
    if d['raw_discount_eur'] > 0:
        out['atlaide'] = f"-{d['discount_eur']} ({d['discount_percent']:g}%)"
        out['kopa_ar_atlaidi'] = d['subtotal_after_discount']
    if d['advance_percent']:
        out['avanss'] = f"{core.fmt_curr(d['raw_advance'])} ({d['advance_percent']:g}%)"
    if d['vat_note']:
        out['pvn_piezime'] = d['vat_note']
    return out


def _known_client(name):
    key = core._norm_client_name(name)
    return any(core._norm_client_name(c.get('name', '')) == key for c in core.load_clients())


@mcp.tool()
def find_clients(query: str = "") -> list[dict]:
    """Meklē klientus pēc nosaukuma, reģ. nr. vai PVN nr. daļas. Tukšs query = visi klienti.
    Atgriež rekvizītus, dokumentu skaitu un pēdējo datumu."""
    history = core.load_history(core.LOCAL_HISTORY_PATH)
    q = query.strip().lower()
    out = []
    for c in core.load_clients():
        hay = " ".join(str(c.get(k, '') or '') for k in ('name', 'reg_no', 'vat_no')).lower()
        if q and q not in hay:
            continue
        key = core._norm_client_name(c.get('name', ''))
        docs = [e for e in history if core._norm_client_name(e.get('pr_partneris', '')) == key]
        out.append({
            'name': c.get('name', ''), 'address': c.get('address', '') or '',
            'reg_no': c.get('reg_no', '') or '', 'vat_no': c.get('vat_no', '') or '',
            'dokumenti': len(docs), 'pedejais': docs[-1].get('pr_numurs', '') if docs else '',
        })
    return [{k: ('' if str(v) == 'nan' else v) for k, v in r.items()} for r in out]


@mcp.tool()
def lursoft_company(url: str) -> dict:
    """Nolasa uzņēmuma rekvizītus (nosaukums, adrese, reģ. nr., PVN nr.) no Lursoft lapas URL."""
    data = scrape_lursoft(url)
    if not data:
        return {'kluda': 'Neizdevās nolasīt datus no šīs saites'}
    if not data.get('vat_no') and data.get('reg_no'):
        data['vat_no_piezime'] = 'PVN nr. lapā nav atrasts — jautā lietotājam'
    return data


@mcp.tool()
def find_past_items(query: str = "", limit: int = 20) -> list[dict]:
    """Meklē agrāk izrakstītās preces/pakalpojumus un sagataves pēc nosaukuma daļas,
    lai uzzinātu ierasto nosaukumu, mērvienību un pēdējo cenu (EUR bez PVN)."""
    q = query.strip().lower()
    seen = {}
    for e in core.load_history(core.LOCAL_HISTORY_PATH):
        for it in e.get('items', []):
            name = str(it.get('name', '')).strip()
            if not name or (q and q not in name.lower()):
                continue
            seen[name.lower()] = {
                'nosaukums': name, 'mervieniba': it.get('unit', ''),
                'pedeja_cena': it.get('raw_price'), 'klients': e.get('pr_partneris', ''),
                'dokuments': e.get('pr_numurs', ''), 'datums': e.get('datums', ''),
            }
    presets = core.load_presets()
    for _, p in presets.iterrows():
        name = str(p.get('NOSAUKUMS', '')).strip()
        if name and (not q or q in name.lower()):
            seen.setdefault(name.lower(), {'nosaukums': name, 'mervieniba': p.get('Mērvienība', ''),
                                           'pedeja_cena': float(p.get('CENA (EUR)', 0) or 0),
                                           'avots': 'sagatave'})
    return list(seen.values())[-limit:]


@mcp.tool()
def preview_invoice(invoice: InvoiceRequest) -> dict:
    """Aprēķina dokumentu un parāda, kā tas izskatīsies — NEKO nesaglabā un numuru nerezervē.
    Parādi rezultātu lietotājam un prasi apstiprinājumu pirms create_invoice."""
    history = core.load_history(core.LOCAL_HISTORY_PATH)
    doc_id = f"BR {core.get_next_invoice_number(history):04d}"
    d = _build(invoice, doc_id)
    out = _summary(d)
    out['numurs'] = f"{doc_id} (provizorisks — galīgo piešķir create_invoice)"
    warnings = []
    if not _known_client(invoice.client.name):
        warnings.append("Klients nav sarakstā — tiks pievienots kā jauns. Pārbaudi rekvizītus.")
    if not invoice.client.reg_no and not invoice.client.vat_no:
        warnings.append("Klientam nav ne reģ. nr., ne PVN nr.")
    if not invoice.vat_enabled and not invoice.vat_note:
        warnings.append("PVN 0% bez pamatojuma — vai pievienot vat_note (piem. reverse charge)?")
    if invoice.proforma:
        warnings.append("Proforma: netiks ierakstīts grāmatvedības vēsturē.")
    out['bridinajumi'] = warnings
    return out


@mcp.tool()
def create_invoice(invoice: InvoiceRequest) -> dict:
    """Izraksta dokumentu: piešķir nākamo BR numuru, ieraksta vēsturē, pievieno klientu,
    uzģenerē PDF un Word un atgriež lejupielādes saites.
    Izsauc TIKAI pēc tam, kad lietotājs ir apstiprinājis preview_invoice rezultātu."""
    with core.data_lock():
        history = core.load_history(core.LOCAL_HISTORY_PATH)
        doc_id = f"BR {core.get_next_invoice_number(history):04d}"
        d = _build(invoice, doc_id)
        path, gh = ((core.LOCAL_TEST_HIST_PATH, core.GITHUB_TEST_HIST_PATH) if invoice.proforma
                    else (core.LOCAL_HISTORY_PATH, core.GITHUB_HISTORY_PATH))
        ok, msg = core._save_to_history(d, path, gh)
    if not ok:
        return {'kluda': f"Neizdevās saglabāt vēsturē: {msg}"}
    added = False
    if not invoice.proforma:
        added, _ = core.record_client(d)
    files = core.write_documents(d, upload=not invoice.proforma)
    out = _summary(d)
    out['saglabats'] = 'proformu vēsturē' if invoice.proforma else 'grāmatvedības vēsturē'
    out['jauns_klients'] = added
    out['pdf'] = doc_url(files['pdf']['file'])
    out['word'] = doc_url(files['docx']['file'])
    out['google_drive'] = files['pdf']['drive']
    return out


@mcp.tool()
def list_invoices(client: str = "", limit: int = 15) -> list[dict]:
    """Pēdējie izrakstītie dokumenti (jaunākie pirmie), pēc izvēles filtrēti pēc klienta nosaukuma daļas."""
    q = client.strip().lower()
    rows = []
    for e in reversed(core.load_history(core.LOCAL_HISTORY_PATH)):
        if q and q not in str(e.get('pr_partneris', '')).lower():
            continue
        num = e.get('pr_numurs', '')
        rows.append({
            'numurs': num, 'datums': e.get('datums', ''), 'tips': e.get('doc_type', ''),
            'klients': e.get('pr_partneris', ''), 'apraksts': e.get('darijuma_apraksts', ''),
            'bez_pvn': e.get('vertiba_bez_pvn', ''), 'pvn': e.get('pvn_summa', ''),
            'kopa': e.get('kopeja_summa', ''), 'apmaksat_lidz': e.get('due_date', ''),
        })
        if len(rows) >= limit:
            break
    for r in rows:
        prefix = r['numurs'].replace(' ', '_')
        files = sorted(f for f in os.listdir(core.DOCS_DIR) if f.endswith(f"_{prefix}.pdf")) \
            if os.path.isdir(core.DOCS_DIR) else []
        if files:
            r['pdf'] = doc_url(files[-1])
    return [{k: ('' if str(v) == 'nan' else v) for k, v in r.items()} for r in rows]


@mcp.custom_route("/docs/{sig}/{name}", methods=["GET"])
async def download(request: Request) -> Response:
    name = os.path.basename(request.path_params['name'])
    path = os.path.join(core.DOCS_DIR, name)
    if not hmac.compare_digest(request.path_params['sig'], _sig(name)) or not os.path.isfile(path):
        return JSONResponse({'error': 'nav atrasts'}, status_code=404)
    return FileResponse(path, filename=name)


if oauth:
    mcp.custom_route("/login", methods=["GET", "POST"])(oauth.login)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return JSONResponse({'ok': True, 'data_dir': core.DATA_DIR, 'local_mode': core.LOCAL_MODE})


if __name__ == "__main__":
    mcp.run("streamable-http", host=HOST, port=PORT, transport_security=security)
