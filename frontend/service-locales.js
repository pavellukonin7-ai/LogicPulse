import {language,t} from './i18n.js';
import {serviceTranslations} from './service-translations.js';
// Match complete original phrases, never substitute a template by service ID.
// Administrator edits and price approvals remain authoritative.
export function serviceText(value='') {
  if (typeof value!=='string' || language()==='ru') return value;
  const translated=serviceTranslations[value]?.[language()];
  if(translated) return translated;
  const weeks=value.match(/^(\d+\s*[–—-]\s*\d+|\d+)\s+(?:неделя|недели|недель)$/u);
  if(weeks) return language()==='en'?weeks[1]+' weeks':weeks[1]+' 周';
  const days=value.match(/^(\d+\s*[–—-]\s*\d+|\d+)\s+(?:день|дня|дней)$/u);
  if(days) return language()==='en'?days[1]+' days':days[1]+' 天';
  return t(value);
}
export function isOriginalRussian(value) {
  return language()!=='ru' && typeof value==='string' && /[А-Яа-яЁё]/u.test(value) && serviceText(value)===value;
}
export function localizeService(source) {
  const result={...source};
  for(const field of ['name','description','delivery_time','public_note','button_text','pricing_note']) {
    result[field]=serviceText(source[field]||'');
  }
  result.scope_items=Array.isArray(source.scope_items)?source.scope_items.map(serviceText):[];
  result.needsTranslation=['name','description','delivery_time','public_note','button_text'].some(key=>isOriginalRussian(source[key])) ||
    (source.scope_items||[]).some(isOriginalRussian);
  return result;
}
