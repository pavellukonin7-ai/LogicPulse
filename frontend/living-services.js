import {t,number} from './i18n.js';
import {localizeService,isOriginalRussian} from './service-locales.js';
function node(tag,text='',className='') {
  const el=document.createElement(tag);el.textContent=text;
  if(className)el.className=className;
  if(isOriginalRussian(text))el.lang='ru';
  return el;
}
export function serviceRow(source,index,choose) {
  const service=localizeService(source);
  const row=node('details','','lp-service');row.dataset.serviceId=String(source.id);
  const summary=node('summary','','lp-service-summary');
  const ordinal=node('span',String(index+1).padStart(2,'0'),'lp-service-number');
  const heading=node('div','','lp-service-heading');
  heading.append(node('h3',service.name));
  const scope=service.scope_items;
  const teaser=scope.length?scope.slice(0,3).join(' · '):service.description;
  heading.append(node('p',teaser,'lp-service-teaser'));
  const approved=Number.isFinite(service.price_min)&&Number.isFinite(service.price_max);
  const price=node('span',approved?number(service.price_min)+'–'+number(service.price_max)+' '+t('₽'):t('По запросу'),'lp-service-price');
  const term=node('span',service.delivery_time||t('Срок после оценки'),'lp-service-term');
  const more=node('span','+','lp-service-more');more.setAttribute('aria-hidden','true');
  summary.append(ordinal,heading,price,term,more);
  const body=node('div','','lp-service-body');
  body.append(node('p',service.description,'lp-service-description'));
  if(scope.length){
    body.append(node('h4',t('В стоимость входит')));
    const list=node('ul');scope.forEach(item=>list.append(node('li',item)));body.append(list);
  }
  if(service.public_note)body.append(node('p',service.public_note,'lp-service-note'));
  if(service.needsTranslation)body.append(node('p',t('Часть описания пока доступна на русском языке.'),'lp-language-fallback'));
  const link=node('a',(service.button_text||t('Обсудить проект'))+' ↗','button lp-service-cta');
  link.href='#brief';link.addEventListener('click',()=>choose(source));
  body.append(link);row.append(summary,body);return row;
}
