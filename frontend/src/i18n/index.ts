import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import enCommon from './locales/en/common.json';
import enAuth from './locales/en/auth.json';
import enBooks from './locales/en/books.json';
import enLeaderboard from './locales/en/leaderboard.json';
import enProfile from './locales/en/profile.json';
import enNotifications from './locales/en/notifications.json';
import enGlossaryEditor from './locales/en/glossaryEditor.json';
import enWiki from './locales/en/wiki.json';
import enExtraction from './locales/en/extraction.json';
import enKnowledge from './locales/en/knowledge.json';
import enEditor from './locales/en/editor.json';
import enReader from './locales/en/reader.json';
import enChat from './locales/en/chat.json';
import enSettings from './locales/en/settings.json';
import enEntityEditor from './locales/en/entityEditor.json';
import enCatalog from './locales/en/catalog.json';
import enTranslation from './locales/en/translation.json';
import enUsage from './locales/en/usage.json';
import viCommon from './locales/vi/common.json';
import viAuth from './locales/vi/auth.json';
import viBooks from './locales/vi/books.json';
import viLeaderboard from './locales/vi/leaderboard.json';
import viProfile from './locales/vi/profile.json';
import viNotifications from './locales/vi/notifications.json';
import viGlossaryEditor from './locales/vi/glossaryEditor.json';
import viWiki from './locales/vi/wiki.json';
import viExtraction from './locales/vi/extraction.json';
import viKnowledge from './locales/vi/knowledge.json';
import viEditor from './locales/vi/editor.json';
import viReader from './locales/vi/reader.json';
import viChat from './locales/vi/chat.json';
import viSettings from './locales/vi/settings.json';
import viEntityEditor from './locales/vi/entityEditor.json';
import viCatalog from './locales/vi/catalog.json';
import viTranslation from './locales/vi/translation.json';
import viUsage from './locales/vi/usage.json';
import jaCommon from './locales/ja/common.json';
import jaAuth from './locales/ja/auth.json';
import jaBooks from './locales/ja/books.json';
import jaLeaderboard from './locales/ja/leaderboard.json';
import jaProfile from './locales/ja/profile.json';
import jaNotifications from './locales/ja/notifications.json';
import jaGlossaryEditor from './locales/ja/glossaryEditor.json';
import jaWiki from './locales/ja/wiki.json';
import jaExtraction from './locales/ja/extraction.json';
import jaKnowledge from './locales/ja/knowledge.json';
import jaEditor from './locales/ja/editor.json';
import jaReader from './locales/ja/reader.json';
import jaChat from './locales/ja/chat.json';
import jaSettings from './locales/ja/settings.json';
import jaEntityEditor from './locales/ja/entityEditor.json';
import jaCatalog from './locales/ja/catalog.json';
import jaTranslation from './locales/ja/translation.json';
import jaUsage from './locales/ja/usage.json';
import zhTWCommon from './locales/zh-TW/common.json';
import zhTWAuth from './locales/zh-TW/auth.json';
import zhTWBooks from './locales/zh-TW/books.json';
import zhTWLeaderboard from './locales/zh-TW/leaderboard.json';
import zhTWProfile from './locales/zh-TW/profile.json';
import zhTWNotifications from './locales/zh-TW/notifications.json';
import zhTWGlossaryEditor from './locales/zh-TW/glossaryEditor.json';
import zhTWWiki from './locales/zh-TW/wiki.json';
import zhTWExtraction from './locales/zh-TW/extraction.json';
import zhTWKnowledge from './locales/zh-TW/knowledge.json';
import zhTWEditor from './locales/zh-TW/editor.json';
import zhTWReader from './locales/zh-TW/reader.json';
import zhTWChat from './locales/zh-TW/chat.json';
import zhTWSettings from './locales/zh-TW/settings.json';
import zhTWEntityEditor from './locales/zh-TW/entityEditor.json';
import zhTWCatalog from './locales/zh-TW/catalog.json';
import zhTWTranslation from './locales/zh-TW/translation.json';
import zhTWUsage from './locales/zh-TW/usage.json';
import enEnrichment from './locales/en/enrichment.json';
import viEnrichment from './locales/vi/enrichment.json';
import jaEnrichment from './locales/ja/enrichment.json';
import zhTWEnrichment from './locales/zh-TW/enrichment.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: enCommon, auth: enAuth, books: enBooks, leaderboard: enLeaderboard, profile: enProfile, notifications: enNotifications, glossaryEditor: enGlossaryEditor, wiki: enWiki, extraction: enExtraction, knowledge: enKnowledge, editor: enEditor, reader: enReader, chat: enChat, settings: enSettings, entityEditor: enEntityEditor, catalog: enCatalog, translation: enTranslation, usage: enUsage, enrichment: enEnrichment },
      vi: { common: viCommon, auth: viAuth, books: viBooks, leaderboard: viLeaderboard, profile: viProfile, notifications: viNotifications, glossaryEditor: viGlossaryEditor, wiki: viWiki, extraction: viExtraction, knowledge: viKnowledge, editor: viEditor, reader: viReader, chat: viChat, settings: viSettings, entityEditor: viEntityEditor, catalog: viCatalog, translation: viTranslation, usage: viUsage, enrichment: viEnrichment },
      ja: { common: jaCommon, auth: jaAuth, books: jaBooks, leaderboard: jaLeaderboard, profile: jaProfile, notifications: jaNotifications, glossaryEditor: jaGlossaryEditor, wiki: jaWiki, extraction: jaExtraction, knowledge: jaKnowledge, editor: jaEditor, reader: jaReader, chat: jaChat, settings: jaSettings, entityEditor: jaEntityEditor, catalog: jaCatalog, translation: jaTranslation, usage: jaUsage, enrichment: jaEnrichment },
      'zh-TW': { common: zhTWCommon, auth: zhTWAuth, books: zhTWBooks, leaderboard: zhTWLeaderboard, profile: zhTWProfile, notifications: zhTWNotifications, glossaryEditor: zhTWGlossaryEditor, wiki: zhTWWiki, extraction: zhTWExtraction, knowledge: zhTWKnowledge, editor: zhTWEditor, reader: zhTWReader, chat: zhTWChat, settings: zhTWSettings, entityEditor: zhTWEntityEditor, catalog: zhTWCatalog, translation: zhTWTranslation, usage: zhTWUsage, enrichment: zhTWEnrichment },
    },
    defaultNS: 'common',
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'lw_language',
    },
  });

export default i18n;
