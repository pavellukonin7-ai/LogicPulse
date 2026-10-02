import './styles.css';import './portal.css';import './remember-me.css';import './language.css';
import {api,session} from './session.js';
import {t,errorSource,validateForm} from './i18n.js';
let mode=new URLSearchParams(location.search).get('mode')==='register'?'register':'login';
let statusSource='',busy=false;
const form=document.querySelector('#account-form'),status=document.querySelector('#account-status'),submit=document.querySelector('#account-submit');
const password=document.querySelector('#account-password');
const passwordWrap=document.createElement('div');passwordWrap.className='password-control';password.before(passwordWrap);passwordWrap.append(password);
const reveal=document.createElement('button');reveal.type='button';reveal.className='password-toggle';passwordWrap.append(reveal);
function renderReveal(){const shown=password.type==='text';reveal.textContent=t(shown?'Скрыть пароль':'Показать пароль');reveal.setAttribute('aria-label',reveal.textContent);reveal.setAttribute('aria-pressed',String(shown));}
reveal.addEventListener('click',()=>{password.type=password.type==='password'?'text':'password';renderReveal();password.focus();});
function render(){
  document.querySelector('#account-title').textContent=t(mode==='register'?'Создать аккаунт':'Вход в аккаунт');
  submit.textContent=t(mode==='register'?'Зарегистрироваться ↗':'Войти ↗');
  document.querySelector('#account-password').autocomplete=mode==='register'?'new-password':'current-password';
  for(const m of ['login','register'])document.querySelector('#mode-'+m).setAttribute('aria-pressed',String(m===mode));
  status.textContent=t(statusSource);renderReveal();
}
for(const m of ['login','register'])document.querySelector('#mode-'+m).addEventListener('click',()=>{if(!busy){mode=m;statusSource='';render();}});
document.addEventListener('lp:language',render);
form.addEventListener('submit',async e=>{
  e.preventDefault();if(!validateForm(form)||busy)return;
  busy=true;submit.disabled=true;statusSource='Проверяем…';render();
  try{
    await api('/api/auth/'+mode,{method:'POST',body:JSON.stringify({
      email:document.querySelector('#account-email').value,
      password:document.querySelector('#account-password').value,
      remember_me:document.querySelector('#account-remember').checked
    })});
    location.href='/';
  }catch(error){statusSource=errorSource(error);}
  finally{busy=false;submit.disabled=false;render();}
});
render();session().then(s=>{
  if(s){form.hidden=true;document.querySelector('.account-tabs').hidden=true;statusSource='Вы уже вошли. Перейдите на главную страницу.';render();}
}).catch(e=>{statusSource=errorSource(e);render();});
