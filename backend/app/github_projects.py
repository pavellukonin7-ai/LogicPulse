import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter


logger = logging.getLogger('logicpulse.github')
router = APIRouter()
GITHUB_USER = os.getenv('GITHUB_PORTFOLIO_USER', 'pavellukonin7-ai')
PROFILE_URL = f'https://github.com/{GITHUB_USER}'
CACHE_SECONDS = 30 * 60

# Public, non-secret snapshot. It keeps the portfolio useful during GitHub outages
# and is refreshed from the public GitHub API whenever the cache expires.
SNAPSHOT = [
    {'name': 'LogicPulse', 'description': 'Профессиональная многоязычная платформа для ИТ-компании на базе FastAPI, PostgreSQL и Docker с интерфейсом на русском, английском и китайском языках.', 'language': 'Python'},
    {'name': 'MindPulse-AI-Docling-Bot', 'description': 'Профессиональный Telegram-ассистент с технологией RAG для анализа документов на базе Docling, Pinecone и ProxyAPI.', 'language': 'Python'},
    {'name': 'logicpulse-project-agent', 'description': 'ИИ-агент для структурированного анализа программных проектов, оценки сроков, вызова инструментов и сохранения истории диалога.', 'language': 'Python'},
    {'name': 'Dialogue-Report-Service', 'description': None, 'language': None},
    {'name': 'A-Telegram-bot-with-short-term-and-long-term-memory.', 'description': None, 'language': None},
    {'name': 'My-Assistant', 'description': 'Мультимодальный Telegram-бот через ProxyAPI с поддержкой OpenAI и Anthropic (Claude).', 'language': None},
    {'name': 'MindPulse-memory-bot', 'description': 'Профессиональный AI-ассистент для Telegram с долговременной памятью Pinecone и семантическим поиском.', 'language': 'Python'},
    {'name': 'text-to-action-assistant', 'description': 'AI-веб-приложение, которое преобразует неструктурированный текст в задачи и заметки с проверкой и журналом аудита.', 'language': 'Python'},
    {'name': 'The-Traveler-s-Currency', 'description': None, 'language': None},
    {'name': 'VK-AI-Assistant', 'description': None, 'language': None},
    {'name': 'Telegram-AI-Agent-Bot', 'description': None, 'language': None},
    {'name': 'AI-Dialogue-Report-Service', 'description': None, 'language': None},
    {'name': '-MCP--', 'description': None, 'language': None},
]


def _safe_url(value, fallback):
    return value if isinstance(value, str) and value.startswith('https://') else fallback


def _normalise(row):
    name = str(row.get('name', '')).strip()[:160]
    fallback = f'{PROFILE_URL}/{name}'
    description = row.get('description')
    return {
        'name': name,
        'description': str(description).strip()[:500] if description else None,
        'language': str(row.get('language')).strip()[:80] if row.get('language') else None,
        'url': _safe_url(row.get('html_url'), fallback),
        'homepage': _safe_url(row.get('homepage'), None),
        'updated_at': row.get('updated_at'),
        'archived': bool(row.get('archived', False)),
        'fork': bool(row.get('fork', False)),
    }


def _snapshot():
    return [_normalise({**row, 'html_url': f'{PROFILE_URL}/{row["name"]}'}) for row in SNAPSHOT]


_cache = {'expires': 0.0, 'items': _snapshot(), 'updated_at': None, 'source': 'snapshot'}
_lock = threading.Lock()


def _response():
    return {
        'items': _cache['items'],
        'source': _cache['source'],
        'updated_at': _cache['updated_at'],
        'profile_url': PROFILE_URL,
    }


def _fetch_public_repositories():
    url = f'https://api.github.com/users/{GITHUB_USER}/repos?per_page=100&sort=updated&type=public'
    request = Request(url, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'LogicPulse-Portfolio',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError('GitHub returned an unexpected response')
    return [_normalise(row) for row in payload if isinstance(row, dict) and row.get('name')]


@router.get('/api/projects', tags=['Проекты'])
def projects():
    now = time.monotonic()
    if _cache['expires'] > now:
        return _response()
    with _lock:
        now = time.monotonic()
        if _cache['expires'] > now:
            return _response()
        try:
            items = _fetch_public_repositories()
            if not items:
                raise ValueError('GitHub portfolio is empty')
            _cache.update({
                'items': items,
                'source': 'github',
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'expires': now + CACHE_SECONDS,
            })
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            logger.warning('GitHub portfolio refresh failed: %s', type(error).__name__)
            _cache['source'] = 'cache' if _cache['updated_at'] else 'snapshot'
            _cache['expires'] = now + 5 * 60
    return _response()
