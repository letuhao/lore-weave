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
import viCommon from './locales/vi/common.json';
import viAuth from './locales/vi/auth.json';
import viLeaderboard from './locales/vi/leaderboard.json';
import viProfile from './locales/vi/profile.json';
import viNotifications from './locales/vi/notifications.json';
import viGlossaryEditor from './locales/vi/glossaryEditor.json';
import viWiki from './locales/vi/wiki.json';
import viExtraction from './locales/vi/extraction.json';
import jaCommon from './locales/ja/common.json';
import jaAuth from './locales/ja/auth.json';
import jaLeaderboard from './locales/ja/leaderboard.json';
import jaProfile from './locales/ja/profile.json';
import jaNotifications from './locales/ja/notifications.json';
import jaGlossaryEditor from './locales/ja/glossaryEditor.json';
import jaWiki from './locales/ja/wiki.json';
import jaExtraction from './locales/ja/extraction.json';
import zhTWCommon from './locales/zh-TW/common.json';
import zhTWAuth from './locales/zh-TW/auth.json';
import zhTWLeaderboard from './locales/zh-TW/leaderboard.json';
import zhTWProfile from './locales/zh-TW/profile.json';
import zhTWNotifications from './locales/zh-TW/notifications.json';
import zhTWGlossaryEditor from './locales/zh-TW/glossaryEditor.json';
import zhTWWiki from './locales/zh-TW/wiki.json';
import zhTWExtraction from './locales/zh-TW/extraction.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: enCommon, auth: enAuth, books: enBooks, leaderboard: enLeaderboard, profile: enProfile, notifications: enNotifications, glossaryEditor: enGlossaryEditor, wiki: enWiki, extraction: enExtraction },
      vi: { common: viCommon, auth: viAuth, leaderboard: viLeaderboard, profile: viProfile, notifications: viNotifications, glossaryEditor: viGlossaryEditor, wiki: viWiki, extraction: viExtraction },
      ja: { common: jaCommon, auth: jaAuth, leaderboard: jaLeaderboard, profile: jaProfile, notifications: jaNotifications, glossaryEditor: jaGlossaryEditor, wiki: jaWiki, extraction: jaExtraction },
      'zh-TW': { common: zhTWCommon, auth: zhTWAuth, leaderboard: zhTWLeaderboard, profile: zhTWProfile, notifications: zhTWNotifications, glossaryEditor: zhTWGlossaryEditor, wiki: zhTWWiki, extraction: zhTWExtraction },
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
