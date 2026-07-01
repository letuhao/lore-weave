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
import enGlossaryTranslate from './locales/en/glossaryTranslate.json';
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
import viGlossaryTranslate from './locales/vi/glossaryTranslate.json';
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
import jaGlossaryTranslate from './locales/ja/glossaryTranslate.json';
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
import zhTWGlossaryTranslate from './locales/zh-TW/glossaryTranslate.json';
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
import enComposition from './locales/en/composition.json';
import viComposition from './locales/vi/composition.json';
import jaComposition from './locales/ja/composition.json';
import zhTWComposition from './locales/zh-TW/composition.json';
import enRawSearch from './locales/en/rawSearch.json';
import viRawSearch from './locales/vi/rawSearch.json';
import jaRawSearch from './locales/ja/rawSearch.json';
import zhTWRawSearch from './locales/zh-TW/rawSearch.json';
import enCampaigns from './locales/en/campaigns.json';
import viCampaigns from './locales/vi/campaigns.json';
import jaCampaigns from './locales/ja/campaigns.json';
import zhTWCampaigns from './locales/zh-TW/campaigns.json';
import enWorld from './locales/en/world.json';
import viWorld from './locales/vi/world.json';
import jaWorld from './locales/ja/world.json';
import zhTWWorld from './locales/zh-TW/world.json';
import enOnboarding from './locales/en/onboarding.json';
import viOnboarding from './locales/vi/onboarding.json';
import jaOnboarding from './locales/ja/onboarding.json';
import zhTWOnboarding from './locales/zh-TW/onboarding.json';
import enJobs from './locales/en/jobs.json';
import viJobs from './locales/vi/jobs.json';
import jaJobs from './locales/ja/jobs.json';
import zhTWJobs from './locales/zh-TW/jobs.json';
// G6 glossary-tiering UI — en/vi/ja/zh-TW (G6f).
import enGlossaryTiering from './locales/en/glossaryTiering.json';
import viGlossaryTiering from './locales/vi/glossaryTiering.json';
import jaGlossaryTiering from './locales/ja/glossaryTiering.json';
import zhTWGlossaryTiering from './locales/zh-TW/glossaryTiering.json';
// Per-user glossary standards library — en/vi/ja/zh-TW.
import enStandards from './locales/en/standards.json';
import viStandards from './locales/vi/standards.json';
import jaStandards from './locales/ja/standards.json';
import zhTWStandards from './locales/zh-TW/standards.json';
// KG customizable-ontology UI (adopt/sync/triage) — en/vi/ja/zh-TW.
import enKgOntology from './locales/en/kgOntology.json';
import viKgOntology from './locales/vi/kgOntology.json';
import jaKgOntology from './locales/ja/kgOntology.json';
import zhTWKgOntology from './locales/zh-TW/kgOntology.json';
// P5 public-MCP OAuth consent page — en/vi/ja/zh-TW.
import enOAuth from './locales/en/oauth.json';
import viOAuth from './locales/vi/oauth.json';
import jaOAuth from './locales/ja/oauth.json';
import zhTWOAuth from './locales/zh-TW/oauth.json';
// Writing Studio (v2) — the dockable book-level workspace — en/vi/ja/zh-TW.
import enStudio from './locales/en/studio.json';
import viStudio from './locales/vi/studio.json';
import jaStudio from './locales/ja/studio.json';
import zhTWStudio from './locales/zh-TW/studio.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: enCommon, auth: enAuth, books: enBooks, leaderboard: enLeaderboard, profile: enProfile, notifications: enNotifications, glossaryEditor: enGlossaryEditor, wiki: enWiki, extraction: enExtraction, glossaryTranslate: enGlossaryTranslate, knowledge: enKnowledge, editor: enEditor, reader: enReader, chat: enChat, settings: enSettings, entityEditor: enEntityEditor, catalog: enCatalog, translation: enTranslation, usage: enUsage, enrichment: enEnrichment, composition: enComposition, rawSearch: enRawSearch, campaigns: enCampaigns, world: enWorld, onboarding: enOnboarding, jobs: enJobs, glossaryTiering: enGlossaryTiering, standards: enStandards, kgOntology: enKgOntology, oauth: enOAuth, studio: enStudio },
      vi: { common: viCommon, auth: viAuth, books: viBooks, leaderboard: viLeaderboard, profile: viProfile, notifications: viNotifications, glossaryEditor: viGlossaryEditor, wiki: viWiki, extraction: viExtraction, glossaryTranslate: viGlossaryTranslate, knowledge: viKnowledge, editor: viEditor, reader: viReader, chat: viChat, settings: viSettings, entityEditor: viEntityEditor, catalog: viCatalog, translation: viTranslation, usage: viUsage, enrichment: viEnrichment, composition: viComposition, rawSearch: viRawSearch, campaigns: viCampaigns, world: viWorld, onboarding: viOnboarding, jobs: viJobs, glossaryTiering: viGlossaryTiering, standards: viStandards, kgOntology: viKgOntology, oauth: viOAuth, studio: viStudio },
      ja: { common: jaCommon, auth: jaAuth, books: jaBooks, leaderboard: jaLeaderboard, profile: jaProfile, notifications: jaNotifications, glossaryEditor: jaGlossaryEditor, wiki: jaWiki, extraction: jaExtraction, glossaryTranslate: jaGlossaryTranslate, knowledge: jaKnowledge, editor: jaEditor, reader: jaReader, chat: jaChat, settings: jaSettings, entityEditor: jaEntityEditor, catalog: jaCatalog, translation: jaTranslation, usage: jaUsage, enrichment: jaEnrichment, composition: jaComposition, rawSearch: jaRawSearch, campaigns: jaCampaigns, world: jaWorld, onboarding: jaOnboarding, jobs: jaJobs, glossaryTiering: jaGlossaryTiering, standards: jaStandards, kgOntology: jaKgOntology, oauth: jaOAuth, studio: jaStudio },
      'zh-TW': { common: zhTWCommon, auth: zhTWAuth, books: zhTWBooks, leaderboard: zhTWLeaderboard, profile: zhTWProfile, notifications: zhTWNotifications, glossaryEditor: zhTWGlossaryEditor, wiki: zhTWWiki, extraction: zhTWExtraction, glossaryTranslate: zhTWGlossaryTranslate, knowledge: zhTWKnowledge, editor: zhTWEditor, reader: zhTWReader, chat: zhTWChat, settings: zhTWSettings, entityEditor: zhTWEntityEditor, catalog: zhTWCatalog, translation: zhTWTranslation, usage: zhTWUsage, enrichment: zhTWEnrichment, composition: zhTWComposition, rawSearch: zhTWRawSearch, campaigns: zhTWCampaigns, world: zhTWWorld, onboarding: zhTWOnboarding, jobs: zhTWJobs, glossaryTiering: zhTWGlossaryTiering, standards: zhTWStandards, kgOntology: zhTWKgOntology, oauth: zhTWOAuth, studio: zhTWStudio },
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
