import {language, t} from './i18n.js';

const projects = {
  'LogicPulse': {
    title: 'LogicPulse',
    ru: 'Многоязычная платформа IT-компании: FastAPI, PostgreSQL, Docker и автоматизированный деплой.',
    en: 'A multilingual IT company platform built with FastAPI, PostgreSQL, Docker and automated deployment.',
    zh: '基于 FastAPI、PostgreSQL、Docker 和自动化部署构建的多语言 IT 公司平台。'
  },
  'MindPulse-AI-Docling-Bot': {
    title: 'MindPulse AI Docling',
    ru: 'Telegram-ассистент с RAG-поиском и анализом PDF и DOCX через Docling и Pinecone.',
    en: 'A Telegram assistant for RAG search and PDF/DOCX analysis with Docling and Pinecone.',
    zh: '基于 Docling 和 Pinecone 的 Telegram 助手，支持 RAG 检索及 PDF、DOCX 分析。'
  },
  'logicpulse-project-agent': {
    title: 'LogicPulse Project Agent',
    ru: 'AI-агент для анализа программных проектов, оценки сроков, вызова инструментов и истории диалога.',
    en: 'An AI agent for software-project analysis, delivery estimates, tool calls and conversation history.',
    zh: '用于软件项目分析、交付周期评估、工具调用和对话记录的 AI 智能体。'
  },
  'Dialogue-Report-Service': {
    title: 'Dialogue Report Service',
    ru: 'Сервис преобразования рабочих диалогов в структурированные отчёты.',
    en: 'A service that turns working conversations into structured reports.',
    zh: '将工作对话转换为结构化报告的服务。'
  },
  'A-Telegram-bot-with-short-term-and-long-term-memory.': {
    title: 'Telegram Memory Bot',
    ru: 'Telegram-бот с краткосрочной и долговременной памятью.',
    en: 'A Telegram bot with short-term and long-term memory.',
    zh: '具备短期和长期记忆能力的 Telegram 机器人。'
  },
  'My-Assistant': {
    title: 'My Assistant',
    ru: 'Мультимодальный Telegram-ассистент с поддержкой OpenAI и Anthropic через ProxyAPI.',
    en: 'A multimodal Telegram assistant using OpenAI and Anthropic through ProxyAPI.',
    zh: '通过 ProxyAPI 接入 OpenAI 与 Anthropic 的多模态 Telegram 助手。'
  },
  'MindPulse-memory-bot': {
    title: 'MindPulse Memory Bot',
    ru: 'AI-ассистент для Telegram с долговременной памятью Pinecone и семантическим поиском.',
    en: 'A Telegram AI assistant with Pinecone long-term memory and semantic search.',
    zh: '具备 Pinecone 长期记忆和语义检索能力的 Telegram AI 助手。'
  },
  'text-to-action-assistant': {
    title: 'Text-to-Action Assistant',
    ru: 'AI-система, которая превращает свободный текст в проверяемые задачи, заметки и отчёты.',
    en: 'An AI system that turns free-form text into reviewable tasks, notes and reports.',
    zh: '将自由文本转换为可审核任务、笔记和报告的 AI 系统。'
  },
  'The-Traveler-s-Currency': {
    title: "Traveler's Currency",
    ru: 'Помощник для быстрого пересчёта валют и работы с курсами в поездках.',
    en: 'An assistant for quick currency conversion and exchange-rate checks while travelling.',
    zh: '用于旅行中快速换算货币和查询汇率的助手。'
  },
  'VK-AI-Assistant': {
    title: 'VK AI Assistant',
    ru: 'AI-ассистент для пользовательских сценариев и автоматизации во ВКонтакте.',
    en: 'An AI assistant for user workflows and automation on VK.',
    zh: '面向 VK 用户场景与自动化流程的 AI 助手。'
  },
  'Telegram-AI-Agent-Bot': {
    title: 'Telegram AI Agent Bot',
    ru: 'Telegram-бот с агентной логикой и подключаемыми AI-инструментами.',
    en: 'A Telegram bot with agent workflows and connected AI tools.',
    zh: '具备智能体工作流和可连接 AI 工具的 Telegram 机器人。'
  },
  'AI-Dialogue-Report-Service': {
    title: 'AI Dialogue Report Service',
    ru: 'AI-сервис для анализа диалогов и подготовки структурированных отчётов.',
    en: 'An AI service for conversation analysis and structured report generation.',
    zh: '用于对话分析和生成结构化报告的 AI 服务。'
  },
  '-MCP--': {
    title: 'MCP Integration',
    ru: 'Проект интеграции Model Context Protocol и внешних инструментов для AI-систем.',
    en: 'A project for integrating Model Context Protocol and external tools into AI systems.',
    zh: '将模型上下文协议（MCP）和外部工具集成到 AI 系统中的项目。'
  }
};

export function projectCopy(repo) {
  const known = projects[repo.name];
  if (known) return {title: known.title, description: known[language()], known: true};
  return {
    title: repo.name.replace(/[-_.]+/g, ' ').trim(),
    description: repo.description || t('Открытый проект в GitHub.'),
    known: false
  };
}
