import {translations} from './i18n-strings.js';
const codes=['ru','en','zh'];
const locales={ru:'ru-RU',en:'en-GB',zh:'zh-CN'};
let selected='ru';
try {
  const query=new URLSearchParams(location.search).get('lang'), saved=localStorage.getItem('lp_language');
  selected=codes.includes(query)?query:codes.includes(saved)?saved:'ru';
} catch {
  const query=new URLSearchParams(location.search).get('lang');
  if(codes.includes(query)) selected=query;
}
export const language=()=>selected;
export const locale=()=>locales[selected];
export const number=value=>new Intl.NumberFormat(locale()).format(value);
export function t(source,params={}) {
  const message=selected==='ru'?source:translations[source]?.[selected]||source;
  return message.replace(/\{(\w+)\}/g,(match,key)=>Object.hasOwn(params,key)?String(params[key]):match);
}
export function errorSource(error,fallback='Сервис временно недоступен.') {
  return translations[error?.message]?error.message:fallback;
}
export function translatedError(error,fallback) {return t(errorSource(error,fallback));}
function translateDocument() {
  document.documentElement.lang=selected==='zh'?'zh-CN':selected;
  for(const el of document.querySelectorAll('[data-i18n]')) el.textContent=t(el.dataset.i18n);
  for(const attr of ['placeholder','aria-label','content']) {
    for(const el of document.querySelectorAll('[data-i18n-'+attr+']')) {
      el.setAttribute(attr,t(el.getAttribute('data-i18n-'+attr)));
    }
  }
  for(const group of document.querySelectorAll('[data-language-switch]')) {
    group.setAttribute('aria-label',t('Язык интерфейса'));
    for(const button of group.querySelectorAll('[data-language]')) button.setAttribute('aria-pressed',String(button.dataset.language===selected));
  }
}
export function setLanguage(code) {
  if(!codes.includes(code)) return;
  selected=code;
  try{localStorage.setItem('lp_language',code);}catch{}
  try {
    const url=new URL(location.href);
    if(url.searchParams.has('lang')) {url.searchParams.set('lang',code);history.replaceState(history.state,'',url);}
  } catch {}
  translateDocument();
  document.dispatchEvent(new Event('lp:language'));
}
for(const group of document.querySelectorAll('[data-language-switch]')) {
  group.setAttribute('role','group');
  for(const [code,label,name] of [['ru','RU','Русский'],['en','EN','English'],['zh','中文','简体中文']]) {
    const button=document.createElement('button');
    button.type='button';button.dataset.language=code;button.textContent=label;
    button.lang=code==='zh'?'zh-CN':code;button.title=name;button.setAttribute('aria-label',name);
    button.addEventListener('click',()=>setLanguage(code));group.append(button);
  }
}
translateDocument();
// App-owned validation keeps messages consistent across all three languages.
const invalidFields=new Set();
function messageFor(field) {
  field.setCustomValidity('');
  const v=field.validity;
  if(v.valueMissing)return field.type==='checkbox'?'Подтвердите согласие на обработку данных.':'Заполните это поле.';
  if(v.typeMismatch)return 'Введите корректный email.';
  if(v.tooShort)return 'Минимум {min} символов.';
  if(v.rangeUnderflow||v.rangeOverflow)return 'Введите число от {min} до {max}.';
  return v.valid?'':'Проверьте значение поля.';
}
function errorElement(field) {
  let error=document.getElementById(field.id+'-error');
  if(!error){error=document.createElement('span');error.id=field.id+'-error';error.className='lp-field-error';error.setAttribute('role','alert');field.insertAdjacentElement('afterend',error);}
  return error;
}
function renderFieldError(field) {
  const source=messageFor(field),error=errorElement(field);
  error.textContent=source?t(source,{min:field.minLength,max:field.max}):'';
  error.hidden=!source;field.setAttribute('aria-invalid',String(Boolean(source)));
  if(source)field.setAttribute('aria-describedby',error.id);else if(field.getAttribute('aria-describedby')===error.id)field.removeAttribute('aria-describedby');
  return !source;
}
export function validateForm(form) {
  const fields=[...form.elements].filter(field=>typeof field.checkValidity==='function'&&!field.disabled);
  const valid=fields.map(field=>{const ok=renderFieldError(field);if(!ok)invalidFields.add(field);return ok;}).every(Boolean);
  if(!valid){const first=fields.find(field=>field.getAttribute('aria-invalid')==='true');first?.focus({preventScroll:true});first?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});}
  return valid;
}
for(const form of document.querySelectorAll('#request-form,#account-form')) {
  form.noValidate=true;
  const clear=event=>{const field=event.target;if(invalidFields.has(field)&&renderFieldError(field))invalidFields.delete(field);};
  form.addEventListener('input',clear);form.addEventListener('change',clear);
}
document.addEventListener('lp:language',()=>invalidFields.forEach(renderFieldError));
