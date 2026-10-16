/**
 * Design tokens — single source: docs/design-theme.md (provisional palette).
 * Components consume token names only; a rebrand is a swap in this file.
 */
import { Platform, TextStyle } from 'react-native';
import { useColorScheme } from './use-color-scheme';

export const palettes = {
  light: {
    primary: '#0D9488',
    primaryPressed: '#0F766E',
    secondary: '#6366F1',
    accent: '#F59E0B',
    recording: '#EF4444',
    bg: '#F8FAFC',
    surface: '#FFFFFF',
    surfaceRaised: '#FFFFFF',
    border: '#E2E8F0',
    text: '#0F172A',
    textMuted: '#64748B',
    textOnPrimary: '#FFFFFF',
    success: '#16A34A',
    warning: '#D97706',
    error: '#DC2626',
  },
  dark: {
    primary: '#2DD4BF',
    primaryPressed: '#14B8A6',
    secondary: '#818CF8',
    accent: '#FBBF24',
    recording: '#F87171',
    bg: '#0F172A',
    surface: '#1E293B',
    surfaceRaised: '#334155',
    border: '#334155',
    text: '#F1F5F9',
    textMuted: '#94A3B8',
    textOnPrimary: '#042F2E',
    success: '#4ADE80',
    warning: '#FBBF24',
    error: '#F87171',
  },
} as const;

export type ThemeColors = (typeof palettes)['light'];

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;

const androidFont: TextStyle =
  Platform.OS === 'android' ? { fontFamily: 'sans-serif', includeFontPadding: false } : {};

export const type = {
  display: { fontSize: 28, fontWeight: '700' as const, ...androidFont },
  title: { fontSize: 20, fontWeight: '600' as const, ...androidFont },
  body: { fontSize: 16, fontWeight: '400' as const, ...androidFont },
  caption: { fontSize: 13, fontWeight: '400' as const, ...androidFont },
};

// Devanagari needs generous line height (design-theme.md usage rule 7).
export const lineHeight = { body: 24, caption: 19 } as const;

export function useTheme() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  return { colors: palettes[scheme], scheme, spacing, type } as const;
}
