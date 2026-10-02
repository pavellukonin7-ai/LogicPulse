export let currentSession = null;
export async function api(url, options = {}) {
  const headers = {'Content-Type':'application/json', ...options.headers};
  if (currentSession?.csrf_token) headers['X-CSRF-Token'] = currentSession.csrf_token;
  const response = await fetch(url, {credentials:'same-origin', ...options, headers, signal:AbortSignal.timeout(20000)});
  if (response.status === 204) return null;
  const data = await response.json().catch(()=>null);
  if (!response.ok) {
    const error = new Error(typeof data?.detail === 'string' ? data.detail : response.status === 422 ? 'Проверьте поля: пароль — от 12 символов, цены и описание должны быть корректны.' : response.status === 429 ? 'Слишком много попыток. Подождите минуту.' : 'Сервис временно недоступен.');
    error.status = response.status; throw error;
  }
  return data;
}
export async function session() {
  try { currentSession = await api('/api/auth/me'); }
  catch(e) { if (e.status !== 401) throw e; currentSession = null; }
  return currentSession;
}
export async function logout() { await api('/api/auth/logout',{method:'POST'}); currentSession=null; location.href='/'; }
export function node(tag,text='',cls='') {const el=document.createElement(tag);el.textContent=text;el.className=cls;return el;}
