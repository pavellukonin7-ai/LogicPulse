import {language, locale, t} from './i18n.js';
import {projectCopy} from './project-translations.js';

const profileUrl = 'https://github.com/pavellukonin7-ai';
const snapshot = [
  ['LogicPulse', 'Python'],
  ['MindPulse-AI-Docling-Bot', 'Python'],
  ['logicpulse-project-agent', 'Python'],
  ['Dialogue-Report-Service', null],
  ['A-Telegram-bot-with-short-term-and-long-term-memory.', null],
  ['My-Assistant', null],
  ['MindPulse-memory-bot', 'Python'],
  ['text-to-action-assistant', 'Python'],
  ['The-Traveler-s-Currency', null],
  ['VK-AI-Assistant', null],
  ['Telegram-AI-Agent-Bot', null],
  ['AI-Dialogue-Report-Service', null],
  ['-MCP--', null]
].map(([name, language]) => ({name, language, url: `${profileUrl}/${name}`}));

const catalog = document.querySelector('#project-catalog');
const status = document.querySelector('#project-status');
const profile = document.querySelector('#github-profile');
let repositories = snapshot;
let source = 'snapshot';

function safeGitHubUrl(value, fallback = profileUrl) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'github.com' ? url.href : fallback;
  } catch { return fallback; }
}

function updatedLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return '';
  return t('Обновлён {date}', {date: new Intl.DateTimeFormat(locale(), {day: '2-digit', month: 'short', year: 'numeric'}).format(date)});
}

function renderProjects() {
  catalog.replaceChildren();
  repositories.forEach((repo, index) => {
    const copy = projectCopy(repo);
    const link = document.createElement('a');
    link.className = 'lp-project';
    link.href = safeGitHubUrl(repo.url, `${profileUrl}/${encodeURIComponent(repo.name)}`);
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.setAttribute('aria-label', t('Открыть проект {name} на GitHub', {name: copy.title}));

    const number = document.createElement('span'); number.className = 'lp-project-index'; number.textContent = String(index + 1).padStart(2, '0');
    const body = document.createElement('span'); body.className = 'lp-project-copy';
    const title = document.createElement('strong'); title.textContent = copy.title;
    const description = document.createElement('span'); description.className = 'lp-project-description'; description.textContent = copy.description;
    if (!copy.known && language() !== 'ru' && /[А-Яа-яЁё]/u.test(copy.description)) description.lang = 'ru';
    const meta = document.createElement('span'); meta.className = 'lp-project-meta';
    const values = [repo.language || t('Открытый код'), updatedLabel(repo.updated_at)];
    if (repo.archived) values.push(t('Архив'));
    if (repo.fork) values.push('Fork');
    meta.textContent = values.filter(Boolean).join(' · ');
    body.append(title, description, meta);
    const arrow = document.createElement('span'); arrow.className = 'lp-project-arrow'; arrow.setAttribute('aria-hidden', 'true'); arrow.textContent = '↗';
    link.append(number, body, arrow); catalog.append(link);
  });
  const sourceLabel = source === 'github' ? 'Синхронизировано с GitHub' : 'Показана сохранённая копия';
  status.textContent = t('{count} публичных проектов · {source}', {count: repositories.length, source: t(sourceLabel)});
  profile.textContent = t('Все репозитории на GitHub ↗');
  profile.href = profileUrl;
}

async function loadProjects() {
  renderProjects();
  try {
    const response = await fetch('/api/projects', {signal: AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error('portfolio unavailable');
    const data = await response.json();
    if (!Array.isArray(data?.items) || !data.items.length) throw new Error('invalid portfolio');
    repositories = data.items.filter(repo => repo && typeof repo.name === 'string' && !repo.private);
    source = data.source === 'github' ? 'github' : 'snapshot';
    profile.href = safeGitHubUrl(data.profile_url);
    renderProjects();
  } catch {
    source = 'snapshot'; renderProjects();
  }
}

document.addEventListener('lp:language', renderProjects);
loadProjects();
