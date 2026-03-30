import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import enCommon from './locales/en/common.json';
import enAuth from './locales/en/auth.json';
import viCommon from './locales/vi/common.json';
import viAuth from './locales/vi/auth.json';
import jaCommon from './locales/ja/common.json';
import jaAuth from './locales/ja/auth.json';
import zhTWCommon from './locales/zh-TW/common.json';
import zhTWAuth from './locales/zh-TW/auth.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: enCommon, auth: enAuth },
      vi: { common: viCommon, auth: viAuth },
      ja: { common: jaCommon, auth: jaAuth },
      'zh-TW': { common: zhTWCommon, auth: zhTWAuth },
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
