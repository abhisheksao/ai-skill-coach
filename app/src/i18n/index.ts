/**
 * i18n init (Constitution X): device locale before the profile step,
 * profile language after. Launch set: en, hi, es, fr, de.
 */
import * as Localization from 'expo-localization';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import de from './locales/de.json';
import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import hi from './locales/hi.json';

export const SUPPORTED_LANGUAGES = ['en', 'hi', 'es', 'fr', 'de'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

export function deviceLanguage(): SupportedLanguage {
  const code = Localization.getLocales()[0]?.languageCode ?? 'en';
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(code)
    ? (code as SupportedLanguage)
    : 'en';
}

// eslint-disable-next-line import/no-named-as-default-member
i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi }, es: { translation: es }, fr: { translation: fr }, de: { translation: de } },
  lng: deviceLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export function setAppLanguage(language: SupportedLanguage) {
  // eslint-disable-next-line import/no-named-as-default-member
  void i18n.changeLanguage(language);
}

export default i18n;
