import './service-cards.css';
import {serviceRow} from './living-services.js';
import './portal.css';
import './analytics.js';
import {session,logout} from './session.js';
import './styles.css';
import './living-pulse.css';
import './living-motion.js';
import './projects.js';
import './language.css';
import {t, number, errorSource, validateForm} from './i18n.js';
import {localizeService, serviceText} from './service-locales.js';

const menu = document.querySelector('.menu-toggle');
const nav = document.querySelector('#navigation');
function closeMenu() { menu.setAttribute('aria-expanded', 'false'); nav.classList.remove('open'); }
menu.addEventListener('click', () => {
  const open = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(open)); nav.classList.toggle('open', open);
});
nav.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });
document.querySelector('#year').textContent = new Date().getFullYear();

const form = document.querySelector('#request-form');
const select = document.querySelector('#service');
const status = document.querySelector('#form-status');
const submit = document.querySelector('#submit-request');
const catalog = document.querySelector('#service-catalog');
const catalogStatus = document.querySelector('#catalog-status');
const retry = document.querySelector('#retry-services');
const pricing = document.querySelector('#pricing-note');
let cataloguePhase = 'loading';
let feedback = null;
function setFeedback(source, params = {}, state = '') {
  feedback = {source, params, state};
  status.textContent = t(source, params); status.dataset.state = state;
}
function renderFeedback() {
  if (feedback) { status.textContent = t(feedback.source, feedback.params); status.dataset.state = feedback.state; }
  submit.textContent = t(submitting ? 'Отправляем…' : 'Отправить заявку ↗');
}
let services = [];
let submitting = false;
let requestId = null;
let lastPayload = null;

function showPrice() {
  const service = services.find(s => s.id === Number(select.value));
  pricing.textContent = service ? (Number.isFinite(service.price_min) && Number.isFinite(service.price_max)
    ? t('Ориентир: {min}–{max} {currency}.', {min:number(service.price_min),max:number(service.price_max),currency:t('₽')}) + ' ' : '')
    + serviceText(service.pricing_note || '') : '';
}
function renderServices() {
  const previousSelection = select.value;
  const openRows = new Set([...catalog.querySelectorAll('details[open]')].map(row=>row.dataset.serviceId));
  catalog.replaceChildren();
  select.replaceChildren(new Option(t(cataloguePhase==='loading'?'Загружаем услуги…':'Выберите направление'),'',true,true));
  services.forEach((service,i)=>{
    select.add(new Option(localizeService(service).name,String(service.id)));
    const row = serviceRow(service,i,selected=>{select.value=String(selected.id);showPrice();});
    row.open=openRows.has(String(service.id)); catalog.append(row);
  });
  if (services.some(service=>String(service.id)===previousSelection)) select.value=previousSelection;
  const labels = {
    loading:'Загружаем направления…',
    empty:'Каталог готовится к публикации. Пожалуйста, зайдите позже.',
    error:'Не удалось загрузить направления. Проверьте соединение и повторите попытку.',
    ready:'{count} направлений · Нажмите на услугу, чтобы посмотреть состав работ'
  };
  catalogStatus.textContent=t(labels[cataloguePhase],{count:services.length}); showPrice();
}
document.addEventListener('lp:language',()=>{renderServices();renderFeedback();});
async function fetchJSON(url, options = {}) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(20000) });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail :
      response.status === 429 ? 'Слишком много запросов. Подождите минуту и попробуйте снова.' :
      response.status === 422 ? 'Проверьте выбранную услугу, email и заполнение полей.' :
      'Не удалось отправить заявку. Попробуйте ещё раз.';
    throw new Error(message);
  }
  return data;
}
async function loadServices() {
  const previousSelection = select.value;
  retry.hidden = true; submit.disabled = true; select.disabled = true;
  cataloguePhase = 'loading'; renderServices();
  try {
    const data = await fetchJSON('/api/services');
    if (!Array.isArray(data)) throw new Error('Некорректный ответ сервера.');
    services = data;

    if (!services.length) {
      cataloguePhase = 'empty'; renderServices();
      setFeedback('Приём заявок откроется после публикации направлений.');
      return;
    }
    cataloguePhase = 'ready'; renderServices();
    if (services.some(s => String(s.id) === previousSelection)) select.value = previousSelection;
    showPrice(); select.disabled = false; submit.disabled = submitting;
    if (!feedback || feedback.state === '') setFeedback('');
  } catch {
    cataloguePhase = 'error'; renderServices();
    setFeedback('Выбор услуг временно недоступен.');
    retry.hidden = false;
  }
}
retry.addEventListener('click', loadServices);
select.addEventListener('change', showPrice);
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submitting || !validateForm(form)) return;
  const fields = new FormData(form);
  const payload = {
    service_id: Number(fields.get('service_id')),
    name: String(fields.get('name')).trim(), email: String(fields.get('email')).trim(),
    company: String(fields.get('company')).trim(), message: String(fields.get('message')).trim(),
    urgency: fields.get('urgency') || null, budget: fields.get('budget') === '' ? null : Number(fields.get('budget')),
    consent: fields.get('consent') === 'on', website: String(fields.get('website') || '')
  };
  if (payload.name.length < 2 || payload.message.length < 20) {
    setFeedback('Укажите имя и опишите задачу минимум в 20 символах.',{},'error'); return;
  }
  const serialized = JSON.stringify(payload);
  // Same request ID is retained for a retry after a lost network response.
  if (!requestId || lastPayload !== serialized) { requestId = crypto.randomUUID(); lastPayload = serialized; }
  submitting = true; submit.disabled = true; submit.textContent = t('Отправляем…');
  form.setAttribute('aria-busy', 'true'); status.dataset.state = 'pending';
  setFeedback('Сохраняем вашу заявку…',{},'pending');
  try {
    const result = await fetchJSON('/api/requests', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, request_id: requestId })
    });
    if (!result?.id || result.message !== 'Заявка отправлена!') throw new Error('Не удалось подтвердить сохранение. Повторите попытку.');
    setFeedback('Заявка отправлена! Номер: {id}. Сохранили вашу задачу и контакт для ответа.', {id:result.id.slice(0,8)}, 'success'); form.reset(); showPrice(); requestId = null; lastPayload = null;
  } catch (error) {
    const source = error.name === 'TimeoutError' || error instanceof TypeError
      ? 'Нет подтверждения от сервера. Данные остались в форме — повторите отправку.' : errorSource(error,'Не удалось отправить заявку. Попробуйте ещё раз.');
    setFeedback(source,{},'error');
  } finally {
    submitting = false; submit.disabled = false; submit.textContent = t('Отправить заявку ↗');
    form.removeAttribute('aria-busy');
  }
});
loadServices();

session().then(s=>{if(s){document.querySelector('#nav-login').hidden=true;document.querySelector('#nav-register').hidden=true;document.querySelector('#nav-logout').hidden=false;document.querySelector('#nav-admin').hidden=s.user.role!=='admin';}}).catch(()=>{});
document.querySelector('#nav-logout').addEventListener('click',()=>logout().catch(e=>{setFeedback(errorSource(e),{},'error')}));
let lastRefresh=Date.now();addEventListener('focus',()=>{if(Date.now()-lastRefresh>15000&&!submitting){lastRefresh=Date.now();loadServices();}});
