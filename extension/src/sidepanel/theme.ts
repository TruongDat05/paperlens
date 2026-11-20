/**
 * Theme & Appearance customization system for PaperLens.
 *
 * Supports two polished presets: Clean White and GitHub-inspired Dark.
 * Provides custom accent colors, text colors, font family choices, and font size adjustment
 * with live preview, persistent preferences via chrome.storage.local, and reset to defaults.
 */

export type ThemePreset = 'light' | 'dark';

export interface AppearancePreferences {
  theme: ThemePreset;
  accentColor: string; // Hex string (e.g. #0969da) or empty string to use preset default
  textColor: string;   // Hex string or empty string to use preset default
  fontFamily: string;  // Identifier: 'system' | 'serif' | 'inter' | 'mono' | 'dyslexic'
  fontSize: number;    // Base font size in px (12 to 18, default 13.5)
}

export const THEME_STORAGE_KEY = 'paperlens_ui_theme';
export const APPEARANCE_STORAGE_KEY = 'paperlens_appearance_prefs';

export const DEFAULT_PRESET_LIGHT: AppearancePreferences = {
  theme: 'light',
  accentColor: '',
  textColor: '',
  fontFamily: 'system',
  fontSize: 13.5,
};

export const DEFAULT_PRESET_DARK: AppearancePreferences = {
  theme: 'dark',
  accentColor: '',
  textColor: '',
  fontFamily: 'system',
  fontSize: 13.5,
};

export interface ColorPresetOption {
  id: string;
  name: string;
  lightValue: string;
  darkValue: string;
}

export const ACCENT_COLOR_OPTIONS: ColorPresetOption[] = [
  { id: 'default', name: 'GitHub Blue', lightValue: '#0969da', darkValue: '#2f81f7' },
  { id: 'purple', name: 'Research Indigo', lightValue: '#8250df', darkValue: '#a371f7' },
  { id: 'emerald', name: 'Academic Green', lightValue: '#1a7f37', darkValue: '#3fb950' },
  { id: 'amber', name: 'Warm Amber', lightValue: '#9a6700', darkValue: '#d29922' },
  { id: 'rose', name: 'Coral Rose', lightValue: '#cf222e', darkValue: '#f85149' },
];

export const TEXT_COLOR_OPTIONS: ColorPresetOption[] = [
  { id: 'default', name: 'Default Contrast', lightValue: '#1f2328', darkValue: '#e6edf3' },
  { id: 'crisp', name: 'Maximum Black / White', lightValue: '#090a0c', darkValue: '#f0f6fc' },
  { id: 'soft', name: 'Soft Slate', lightValue: '#334155', darkValue: '#cbd5e1' },
];

export interface FontOption {
  id: string;
  name: string;
  cssValue: string;
  sample: string;
}

export const FONT_OPTIONS: FontOption[] = [
  {
    id: 'system',
    name: 'System Sans',
    cssValue: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    sample: 'Clean standard UI font',
  },
  {
    id: 'serif',
    name: 'Academic Serif',
    cssValue: "'Crimson Text', 'EB Garamond', Georgia, Cambria, 'Times New Roman', serif",
    sample: 'Classic research paper typography',
  },
  {
    id: 'inter',
    name: 'Modern Grotesk',
    cssValue: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    sample: 'Crisp contemporary sans-serif',
  },
  {
    id: 'mono',
    name: 'Technical Mono',
    cssValue: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
    sample: 'Monospaced engineering font',
  },
  {
    id: 'dyslexic',
    name: 'High Legibility',
    cssValue: "'Atkinson Hyperlegible', -apple-system, BlinkMacSystemFont, sans-serif",
    sample: 'Maximized character distinction',
  },
];

/**
 * Utility: convert 6-digit hex string to rgba with given alpha.
 */
export function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  if (clean.length !== 6) return hex;
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Utility: lighten or darken a hex color by a factor.
 */
export function adjustBrightness(hex: string, factor: number): string {
  const clean = hex.replace('#', '');
  if (clean.length !== 6) return hex;
  const r = Math.min(255, Math.max(0, Math.round(parseInt(clean.substring(0, 2), 16) * factor)));
  const g = Math.min(255, Math.max(0, Math.round(parseInt(clean.substring(2, 4), 16) * factor)));
  const b = Math.min(255, Math.max(0, Math.round(parseInt(clean.substring(4, 6), 16) * factor)));
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

/**
 * Apply appearance preferences directly to documentElement CSS custom properties.
 * This guarantees instantaneous live preview without requiring DOM unmount/remount.
 */
export function applyAppearanceToDOM(prefs: AppearancePreferences): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  // Set data-theme attribute
  root.setAttribute('data-theme', prefs.theme);

  // Accent color override
  if (prefs.accentColor && /^#[0-9a-fA-F]{6}$/.test(prefs.accentColor)) {
    const isDark = prefs.theme === 'dark';
    root.style.setProperty('--color-primary', prefs.accentColor);
    root.style.setProperty('--color-primary-hover', adjustBrightness(prefs.accentColor, isDark ? 1.18 : 0.82));
    root.style.setProperty('--color-primary-subtle', hexToRgba(prefs.accentColor, isDark ? 0.16 : 0.08));
    root.style.setProperty('--color-primary-border', hexToRgba(prefs.accentColor, isDark ? 0.40 : 0.28));
    root.style.setProperty('--color-primary-focus', hexToRgba(prefs.accentColor, 0.35));
  } else {
    root.style.removeProperty('--color-primary');
    root.style.removeProperty('--color-primary-hover');
    root.style.removeProperty('--color-primary-subtle');
    root.style.removeProperty('--color-primary-border');
    root.style.removeProperty('--color-primary-focus');
  }

  // Text color override
  if (prefs.textColor && /^#[0-9a-fA-F]{6}$/.test(prefs.textColor)) {
    root.style.setProperty('--color-text-main', prefs.textColor);
  } else {
    root.style.removeProperty('--color-text-main');
  }

  // Font family override
  const fontOpt = FONT_OPTIONS.find((f) => f.id === prefs.fontFamily);
  if (fontOpt && prefs.fontFamily !== 'system') {
    root.style.setProperty('--font-sans', fontOpt.cssValue);
  } else {
    root.style.removeProperty('--font-sans');
  }

  // Font size override
  if (prefs.fontSize && prefs.fontSize >= 11 && prefs.fontSize <= 20) {
    root.style.setProperty('--font-size-base', `${prefs.fontSize}px`);
    root.style.fontSize = `${prefs.fontSize}px`;
  } else {
    root.style.removeProperty('--font-size-base');
    root.style.removeProperty('font-size');
  }
}

/**
 * Load preferences from storage or initialize with defaults.
 */
export async function loadAppearancePreferences(): Promise<AppearancePreferences> {
  const defaultTheme: ThemePreset =
    typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';

  let savedTheme = defaultTheme;
  let savedPrefs: Partial<AppearancePreferences> = {};

  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    try {
      const data = await chrome.storage.local.get([THEME_STORAGE_KEY, APPEARANCE_STORAGE_KEY]);
      if (data[THEME_STORAGE_KEY] === 'dark' || data[THEME_STORAGE_KEY] === 'light') {
        savedTheme = data[THEME_STORAGE_KEY];
      }
      if (data[APPEARANCE_STORAGE_KEY]) {
        savedPrefs = data[APPEARANCE_STORAGE_KEY];
      }
    } catch {
      // Fallback
    }
  } else if (typeof localStorage !== 'undefined') {
    try {
      const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
      if (storedTheme === 'dark' || storedTheme === 'light') savedTheme = storedTheme;
      const storedPrefs = localStorage.getItem(APPEARANCE_STORAGE_KEY);
      if (storedPrefs) savedPrefs = JSON.parse(storedPrefs);
    } catch {
      // Fallback
    }
  }

  const baseDefault = savedTheme === 'dark' ? DEFAULT_PRESET_DARK : DEFAULT_PRESET_LIGHT;
  return {
    ...baseDefault,
    ...savedPrefs,
    theme: savedPrefs.theme || savedTheme,
  };
}

/**
 * Persist appearance preferences to storage and apply to DOM.
 */
export async function saveAppearancePreferences(prefs: AppearancePreferences): Promise<void> {
  applyAppearanceToDOM(prefs);

  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    try {
      await chrome.storage.local.set({
        [THEME_STORAGE_KEY]: prefs.theme,
        [APPEARANCE_STORAGE_KEY]: prefs,
      });
    } catch {
      // Fallback
    }
  }

  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, prefs.theme);
      localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Fallback
    }
  }
}
