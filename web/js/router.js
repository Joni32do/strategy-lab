/* Hash router: #/ (gallery), #/game/<id>, #/history.
 * Pages are classes with mount(el, params) and optional unmount(). */

const routes = [];
let current = null;
let outlet = null;

export function route(pattern, Page) {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/?]+)'; }) + '$');
  routes.push({ re, keys, Page });
}

export function go(path) {
  if (location.hash === '#' + path) render();
  else location.hash = path;
}

function parse() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  return { path, query: Object.fromEntries(new URLSearchParams(query)) };
}

async function render() {
  const { path, query } = parse();
  for (const r of routes) {
    const m = path.match(r.re);
    if (!m) continue;
    const params = { ...query };
    r.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); });
    if (current?.unmount) current.unmount();
    outlet.replaceChildren();
    window.scrollTo(0, 0);
    current = new r.Page();
    await current.mount(outlet, params);
    return;
  }
  go('/');
}

export function startRouter(el) {
  outlet = el;
  window.addEventListener('hashchange', render);
  return render();
}

export function currentPage() { return current; }
