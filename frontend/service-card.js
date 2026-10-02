const money = new Intl.NumberFormat('ru-RU');

function node(tag, text = '', className = '') {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

export function serviceContent(service) {
  const content = node('div', '', 'service-copy');
  content.append(node('h3', service.name), node('p', service.description, 'service-description'));
  if (service.scope_items?.length) {
    content.append(node('h4', 'В стоимость входит', 'service-scope-title'));
    const list = node('ul', '', 'service-scope');
    for (const text of service.scope_items) list.append(node('li', text));
    content.append(list);
  }
  const facts = node('dl', '', 'service-facts');
  const price = node('div');
  price.append(node('dt', 'Стоимость'), node('dd',
    Number.isFinite(service.price_min) && Number.isFinite(service.price_max)
      ? `${money.format(service.price_min)}–${money.format(service.price_max)} ₽`
      : 'По запросу'));
  facts.append(price);
  if (service.delivery_time) {
    const term = node('div');
    term.append(node('dt', 'Срок'), node('dd', service.delivery_time));
    facts.append(term);
  }
  content.append(facts);
  if (service.public_note) content.append(node('p', service.public_note, 'service-public-note'));
  return content;
}
