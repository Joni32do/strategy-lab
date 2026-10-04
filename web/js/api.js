/* The JSON API (see strategy_lab/web/app.py). */

export class ApiError extends Error {}

async function req(method, url, body) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let r;
  try {
    r = await fetch(url, init);
  } catch (e) {
    throw new ApiError('The lab server is not reachable. Is it running?');
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(data.error || `${r.status} ${r.statusText}`);
  return data;
}

export const api = {
  catalog: () => req('GET', '/api/catalog'),
  game: (id) => req('GET', `/api/games/${encodeURIComponent(id)}`),
  play: (body) => req('POST', '/api/play', body),
  lens: (id, body) => req('POST', `/api/lens/${encodeURIComponent(id)}`, body),
  simulate: (body) => req('POST', '/api/simulate', body),
  concepts: () => req('GET', '/api/concepts'),
  profile: () => req('GET', '/api/profile'),
  patchProfile: (patch) => req('PATCH', '/api/profile', patch),
  seeConcept: (concept) => req('POST', '/api/profile/concept', { concept }),
  resetProfile: () => req('POST', '/api/profile/reset', {}),
  history: (params = {}) => req('GET', `/api/history?${new URLSearchParams(params)}`),
  devVersion: () => req('GET', '/api/dev/version'),
};
