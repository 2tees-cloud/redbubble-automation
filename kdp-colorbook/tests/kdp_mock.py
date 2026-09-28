"""Макет KDP для офлайн-теста робота: те же id/подписи, что в kdp_selectors.yaml, простая валидация.
Проверяет логику робота (шаги, продолжение, отладка), а не совместимость с настоящим сайтом."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"saves": {"details": 0, "content": 0, "pricing": 0}, "data": {}, "login_challenge": False,
         "break_cover": False}

BOOKSHELF = """<html><body><h1 id="bookshelf-title">Bookshelf</h1></body></html>"""
LOGIN = """<html><body><form><input id="ap_email" name="email"><input id="continue" type="submit">
<img id="auth-captcha-image" src=""></form></body></html>"""

JS_SAVE = """
async function save(tab, data, next) {
  await fetch('/api/save/' + tab, {method: 'POST', body: JSON.stringify(data)});
  location.href = next;
}"""

DETAILS = """<html><body><script>""" + JS_SAVE + """
function openCats(){ document.getElementById('cats').style.display='block'; }
function saveCats(){ window.cat = document.getElementById('c0').value + '>' + document.getElementById('c1').value
  + '>' + (document.getElementById('place').checked ? 'Coloring Books' : '');
  document.getElementById('cats').style.display='none'; }
async function go(){
  const v = id => document.getElementById(id).value;
  const desc = document.querySelector('iframe.cke_wysiwyg_frame').contentDocument.body.innerHTML;
  if (!v('data-title') || !v('data-primary-author-last-name') || !desc || !document.getElementById('non-public-domain').checked
      || !v('data-keywords-0') || !window.cat) { document.body.insertAdjacentHTML('beforeend','<p id=err>missing</p>'); return; }
  const kws = [...Array(7).keys()].map(i => v('data-keywords-' + i)).filter(Boolean);
  await save('details', {title: v('data-title'), subtitle: v('data-subtitle'), first: v('data-primary-author-first-name'),
    last: v('data-primary-author-last-name'), description: desc, keywords: kws, category: window.cat},
    '/en_US/title-setup/paperback/T123/content');
}</script>
<label for="data-title">Book Title</label><input id="data-title">
<input id="data-subtitle"><input id="data-primary-author-first-name"><input id="data-primary-author-last-name">
<iframe class="cke_wysiwyg_frame" srcdoc="<body contenteditable=true></body>"></iframe>
<input type="radio" name="rights" id="non-public-domain"><input type="radio" name="adult" id="data-is-adult-content-false">
""" + "".join(f'<input id="data-keywords-{i}">' for i in range(7)) + """
<button id="categories-modal-button" onclick="openCats()">Choose categories</button>
<div role="dialog" id="cats" style="display:none">
 <select id="c0"><option>Choose</option><option>Children's Books</option><option>Crafts, Hobbies &amp; Home</option></select>
 <select id="c1"><option>Choose</option><option>Activities, Crafts &amp; Games</option><option>Coloring Books for Grown-Ups</option></select>
 <label><input type="checkbox" id="place">Coloring Books</label>
 <button onclick="saveCats()">Save categories</button>
</div>
<button id="save-and-continue-announce" onclick="go()">Save and Continue</button></body></html>"""

CONTENT = """<html><body><script>""" + JS_SAVE + """
const S = {}; const show = (id, html) => document.getElementById(id).innerHTML = html;
function isbn(){ show('isbnbox', '<button id="free-print-isbn-accept-button-announce" onclick="assign()">Assign ISBN</button>'); }
function assign(){ S.isbn = 1; show('isbnbox', '<span id="free-print-isbn-assigned">Your ISBN is 979-8-0000</span>'); }
function trims(){ document.getElementById('trims').style.display='block'; }
function up(kind, input){ S[kind] = input.files[0].name;
  if (kind === 'cover' && BREAK_COVER) return;
  show(kind + 'ok', '<span id="data-print-book-publisher-' + (kind === 'cover' ? 'cover' : 'interior')
       + '-file-upload-success">' + kind + ' uploaded successfully</span>'); }
function preview(){ setTimeout(() => show('prev', '<button id="printpreview_approve_button_enabled" onclick="S.approved=1">Approve</button>'), 700); }
async function go(){
  const r = n => (document.querySelector('input[name=' + n + ']:checked') || {}).value;
  const d = {isbn: S.isbn, ink: r('ink'), trim: S.trim, bleed: r('bleed'), finish: r('finish'), interior: S.interior,
    cover: S.cover, ai: r('ai'), ai_images: document.getElementById('generative-ai-questionnaire-images').value,
    ai_tool: document.getElementById('generative-ai-questionnaire-images-tool').value, approved: S.approved};
  if (Object.values(d).some(x => !x)) { document.body.insertAdjacentHTML('beforeend','<p id=err>' + JSON.stringify(d) + '</p>'); return; }
  await save('content', d, '/en_US/title-setup/paperback/T123/pricing');
}</script>
<div id="isbnbox"><button id="free-print-isbn-btn-announce" onclick="isbn()">Get a free KDP ISBN</button></div>
<label><input type="radio" name="ink" value="bw-white">Black &amp; white interior with white paper</label>
<label><input type="radio" name="ink" value="bw-cream">Black &amp; white interior with cream paper</label>
<button id="trim-size-btn-announce" onclick="trims()">Select a different size</button>
<div id="trims" style="display:none"><button onclick="S.trim='8.5x11'">8.5 x 11 in</button>
<button onclick="S.trim='8.5x8.5'">8.5 x 8.5 in</button><button onclick="S.trim='6x9'">6 x 9 in</button></div>
<label><input type="radio" name="bleed" value="no">No Bleed</label><label><input type="radio" name="bleed" value="yes">Bleed</label>
<label><input type="radio" name="finish" value="matte">Matte</label><label><input type="radio" name="finish" value="glossy">Glossy</label>
<input type="file" style="display:none" id="data-print-book-publisher-interior-file-upload-AjaxInput" onchange="up('interior', this)">
<div id="interiorok"></div>
<label><input type="radio" name="cover" id="data-print-book-publisher-cover-choice-upload">Upload a cover you already have</label>
<input type="file" style="display:none" id="data-print-book-publisher-cover-file-upload-AjaxInput" onchange="up('cover', this)">
<div id="coverok"></div>
<input type="radio" name="ai" value="yes" id="generative-ai-questionnaire-yes"><input type="radio" name="ai" value="no">
<select id="generative-ai-questionnaire-text"><option>None</option><option>Some sections, with extensive editing</option></select>
<select id="generative-ai-questionnaire-images"><option>None</option><option>Entire work, with minimal or no editing</option></select>
<select id="generative-ai-questionnaire-translations"><option>None</option></select>
<input id="generative-ai-questionnaire-images-tool">
<button id="print-preview-noconfirm-announce" onclick="preview()">Launch Previewer</button><div id="prev"></div>
<button id="save-and-continue-announce" onclick="go()">Save and Continue</button></body></html>"""

PRICING = """<html><body><script>""" + JS_SAVE + """
async function done(kind){
  const price = document.querySelector('#data-pricing-print-us-price-input input').value;
  await fetch('/api/save/pricing', {method: 'POST', body: JSON.stringify({price: price, kind: kind})});
  document.body.insertAdjacentHTML('beforeend', kind === 'publish'
    ? '<h2>Your paperback is being published</h2>' : '<p>Draft saved</p>'); }</script>
<label><input type="radio" id="data-pricing-print-worldwide-rights">All territories (worldwide rights)</label>
<div id="data-pricing-print-us-price-input"><input></div>
<button id="save-announce" onclick="done('draft')">Save as Draft</button>
<button id="save-and-publish-announce" onclick="done('publish')">Publish Your Paperback Book</button></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: str, code: int = 200, ctype: str = "text/html"):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.endswith("/bookshelf"):
            return self._send(LOGIN if STATE["login_challenge"] else BOOKSHELF)
        if path.endswith("/details"):
            return self._send(DETAILS)
        if path.endswith("/content"):
            return self._send(CONTENT.replace("BREAK_COVER", "true" if STATE["break_cover"] else "false"))
        if path.endswith("/pricing"):
            return self._send(PRICING)
        self._send("not found", 404)

    def do_POST(self):
        tab = self.path.rsplit("/", 1)[-1]
        n = int(self.headers.get("Content-Length", 0))
        STATE["saves"][tab] += 1
        STATE["data"][tab] = json.loads(self.rfile.read(n) or b"{}")
        self._send("{}", ctype="application/json")


def start() -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/en_US"
