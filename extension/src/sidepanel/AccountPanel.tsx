import React, { useEffect, useState, useCallback } from 'react';
import { ApiClient } from '../api/client';
import { AccountProfile, ResearchMemory } from '../api/types';
import {
  IconLogo,
  IconSun,
  IconMoon,
  IconPalette,
  IconType,
  IconReset,
  IconCheck,
} from './Icons';
import {
  AppearancePreferences,
  ThemePreset,
  loadAppearancePreferences,
  saveAppearancePreferences,
  applyAppearanceToDOM,
  DEFAULT_PRESET_LIGHT,
  DEFAULT_PRESET_DARK,
  ACCENT_COLOR_OPTIONS,
  TEXT_COLOR_OPTIONS,
  FONT_OPTIONS,
} from './theme';

interface Props {
  client: ApiClient;
  account: AccountProfile;
  onSaved: (account: AccountProfile) => void;
  refresh: () => Promise<void>;
  onboarding?: boolean;
  appearance?: AppearancePreferences;
  onAppearanceChange?: (prefs: AppearancePreferences) => void;
}

export function AccountPanel({
  client,
  account,
  onSaved,
  refresh,
  onboarding = false,
  appearance: propAppearance,
  onAppearanceChange,
}: Props) {
  const [name, setName] = useState(account.name);
  const [area, setArea] = useState(account.research_area);
  const [nationality, setNationality] = useState(account.nationality);
  const [remember, setRemember] = useState(account.memory_enabled);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [memories, setMemories] = useState<ResearchMemory[]>([]);
  const [note, setNote] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState('');

  // Internal appearance state (synchronized with prop if passed, or loaded independently)
  const [prefs, setPrefs] = useState<AppearancePreferences>(
    propAppearance || (document.documentElement.getAttribute('data-theme') === 'dark' ? DEFAULT_PRESET_DARK : DEFAULT_PRESET_LIGHT)
  );

  useEffect(() => {
    if (propAppearance) {
      setPrefs(propAppearance);
    } else {
      void loadAppearancePreferences().then((loaded) => setPrefs(loaded));
    }
  }, [propAppearance]);

  const updatePreferences = useCallback(
    (next: AppearancePreferences) => {
      setPrefs(next);
      applyAppearanceToDOM(next);
      void saveAppearancePreferences(next);
      onAppearanceChange?.(next);
    },
    [onAppearanceChange]
  );

  const handleThemeChange = (theme: ThemePreset) => {
    const defaultForTheme = theme === 'dark' ? DEFAULT_PRESET_DARK : DEFAULT_PRESET_LIGHT;
    const next: AppearancePreferences = {
      ...prefs,
      theme,
      // If colors were unset or default, keep them default for the new theme
      accentColor: prefs.accentColor ? prefs.accentColor : defaultForTheme.accentColor,
      textColor: prefs.textColor ? prefs.textColor : defaultForTheme.textColor,
    };
    updatePreferences(next);
  };

  const handleResetPreferences = () => {
    const defaultForTheme = prefs.theme === 'dark' ? DEFAULT_PRESET_DARK : DEFAULT_PRESET_LIGHT;
    updatePreferences(defaultForTheme);
  };

  const reload = async () => setMemories(await client.getMemories());
  useEffect(() => {
    if (!onboarding) reload().catch((e) => setError(e.message));
  }, [client, account.owner_id, onboarding]);
  useEffect(() => {
    if (account.name) setName(account.name);
  }, [account.name]);

  const action = async (task: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setStatus('');
    try {
      await task();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const isDark = prefs.theme === 'dark';
  const currentAccent = prefs.accentColor || (isDark ? '#2f81f7' : '#0969da');

  return (
    <section
      className={`account-panel ${onboarding ? 'onboarding-panel' : ''}`}
      aria-label={onboarding ? 'Research profile setup' : 'Settings and memory'}
    >
      {onboarding && (
        <div className="onboarding-intro">
          <div className="onboarding-brand-mark">
            <IconLogo size={32} />
          </div>
          <h1>Welcome to PaperLens</h1>
          <p>An evidence-grounded research assistant that reads, cites, and remembers your scientific inquiry.</p>
        </div>
      )}

      <div className="settings-heading">
        <h2>{onboarding ? 'Your research profile' : 'Research profile'}</h2>
        <p className="description">Personalize explanations and keep useful research context across sessions.</p>
      </div>

      <form
        className="profile-form"
        onSubmit={(event) => {
          event.preventDefault();
          void action(async () => {
            const saved = await client.updateProfile({
              name,
              research_area: area,
              nationality,
              memory_enabled: remember,
            });
            onSaved(saved);
            setStatus('Profile saved.');
          });
        }}
      >
        <label className="form-label">
          Name
          <input
            autoFocus={onboarding}
            autoComplete="name"
            required
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="text-input"
          />
        </label>
        <label className="form-label">
          Research area
          <textarea
            required
            maxLength={500}
            rows={2}
            value={area}
            onChange={(e) => setArea(e.target.value)}
            className="text-input"
            placeholder="For example, retrieval-augmented generation and table reasoning"
          />
        </label>
        <label className="form-label">
          Nationality
          <input
            autoComplete="country-name"
            required
            maxLength={100}
            value={nationality}
            onChange={(e) => setNationality(e.target.value)}
            className="text-input"
            placeholder="Enter your nationality"
          />
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          <span>Remember important research context across sessions</span>
        </label>
        <p className="description">
          Session history stays with each chat. Long-term memory keeps important notes with their sources; you can edit or
          delete them in Settings.
        </p>
        <button className="btn btn-primary" disabled={busy} type="submit">
          {busy ? 'Saving…' : onboarding ? 'Start researching' : 'Save profile'}
        </button>
      </form>

      {/* Appearance & Typography Customizer */}
      <section className="settings-section appearance-section" aria-label="Appearance and theme">
        <div className="section-header-row">
          <div>
            <h3>Appearance & Typography</h3>
            <p className="description">Customize presets, accent colors, and readability to match your reading style.</p>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm reset-defaults-btn"
            onClick={handleResetPreferences}
            title="Reset theme and font options to default preset"
            aria-label="Reset appearance to defaults"
          >
            <IconReset size={13} />
            <span>Reset to defaults</span>
          </button>
        </div>

        {/* Preset Theme Selection */}
        <div className="customizer-group">
          <span className="customizer-label" id="preset-theme-label">
            Theme Preset
          </span>
          <div className="preset-toggle-grid" role="radiogroup" aria-labelledby="preset-theme-label">
            <button
              type="button"
              role="radio"
              aria-checked={prefs.theme === 'light'}
              className={`preset-card ${prefs.theme === 'light' ? 'selected' : ''}`}
              onClick={() => handleThemeChange('light')}
            >
              <div className="preset-preview preset-preview-light">
                <span className="preview-accent-dot preview-dot-light" />
                <span className="preview-line" />
              </div>
              <div className="preset-info">
                <div className="preset-name">
                  <IconSun size={14} />
                  <span>Clean White</span>
                </div>
                <small>High contrast, crisp borders</small>
              </div>
            </button>

            <button
              type="button"
              role="radio"
              aria-checked={prefs.theme === 'dark'}
              className={`preset-card ${prefs.theme === 'dark' ? 'selected' : ''}`}
              onClick={() => handleThemeChange('dark')}
            >
              <div className="preset-preview preset-preview-dark">
                <span className="preview-accent-dot preview-dot-dark" />
                <span className="preview-line preview-line-dark" />
              </div>
              <div className="preset-info">
                <div className="preset-name">
                  <IconMoon size={14} />
                  <span>GitHub Dark</span>
                </div>
                <small>Authentic GitHub primer palette</small>
              </div>
            </button>
          </div>
        </div>

        {/* Accent Color Customization */}
        <div className="customizer-group">
          <div className="customizer-label-row">
            <span className="customizer-label" id="accent-color-label">
              Accent Color
            </span>
            <span className="customizer-value-pill" style={{ color: currentAccent }}>
              {prefs.accentColor ? prefs.accentColor : 'Default Preset'}
            </span>
          </div>

          <div className="swatches-row" role="group" aria-labelledby="accent-color-label">
            {ACCENT_COLOR_OPTIONS.map((opt) => {
              const swatchColor = isDark ? opt.darkValue : opt.lightValue;
              const isSelected = (!prefs.accentColor && opt.id === 'default') || prefs.accentColor === swatchColor;
              return (
                <button
                  key={opt.id}
                  type="button"
                  className={`color-swatch-btn ${isSelected ? 'active' : ''}`}
                  style={{ backgroundColor: swatchColor }}
                  title={`${opt.name} (${swatchColor})`}
                  aria-label={`${opt.name} accent`}
                  aria-pressed={isSelected}
                  onClick={() => updatePreferences({ ...prefs, accentColor: opt.id === 'default' ? '' : swatchColor })}
                >
                  {isSelected && <IconCheck size={12} className="swatch-check" />}
                </button>
              );
            })}

            {/* Custom Hex Color Picker */}
            <label className="custom-color-picker-label" title="Choose custom accent hex color">
              <input
                type="color"
                className="custom-color-input"
                aria-label="Custom accent color picker"
                value={prefs.accentColor || (isDark ? '#2f81f7' : '#0969da')}
                onChange={(e) => updatePreferences({ ...prefs, accentColor: e.target.value })}
              />
              <span className="custom-color-text">Custom</span>
            </label>
          </div>
        </div>

        {/* Text Color Customization */}
        <div className="customizer-group">
          <div className="customizer-label-row">
            <span className="customizer-label" id="text-color-label">
              Text Contrast
            </span>
            <span className="customizer-value-pill">
              {prefs.textColor ? prefs.textColor : 'Preset Default'}
            </span>
          </div>

          <div className="swatches-row" role="group" aria-labelledby="text-color-label">
            {TEXT_COLOR_OPTIONS.map((opt) => {
              const textColor = isDark ? opt.darkValue : opt.lightValue;
              const isSelected = (!prefs.textColor && opt.id === 'default') || prefs.textColor === textColor;
              return (
                <button
                  key={opt.id}
                  type="button"
                  className={`color-swatch-btn text-swatch-btn ${isSelected ? 'active' : ''}`}
                  style={{ backgroundColor: textColor || (isDark ? '#e6edf3' : '#1f2328') }}
                  title={`${opt.name}`}
                  aria-label={`${opt.name} text`}
                  aria-pressed={isSelected}
                  onClick={() => updatePreferences({ ...prefs, textColor: opt.id === 'default' ? '' : textColor })}
                >
                  {isSelected && <IconCheck size={12} className="swatch-check" />}
                </button>
              );
            })}

            <label className="custom-color-picker-label" title="Choose custom text hex color">
              <input
                type="color"
                className="custom-color-input"
                aria-label="Custom text color picker"
                value={prefs.textColor || (isDark ? '#e6edf3' : '#1f2328')}
                onChange={(e) => updatePreferences({ ...prefs, textColor: e.target.value })}
              />
              <span className="custom-color-text">Custom</span>
            </label>
          </div>
        </div>

        {/* Font Family Selection */}
        <div className="customizer-group">
          <div className="customizer-label-row">
            <span className="customizer-label" id="font-family-label">
              Font Family
            </span>
            <span className="customizer-value-pill">
              {FONT_OPTIONS.find((f) => f.id === prefs.fontFamily)?.name || 'System Sans'}
            </span>
          </div>
          <div className="font-options-grid" role="radiogroup" aria-labelledby="font-family-label">
            {FONT_OPTIONS.map((f) => (
              <button
                key={f.id}
                type="button"
                role="radio"
                aria-checked={prefs.fontFamily === f.id}
                className={`font-option-btn ${prefs.fontFamily === f.id ? 'active' : ''}`}
                style={{ fontFamily: f.cssValue }}
                onClick={() => updatePreferences({ ...prefs, fontFamily: f.id })}
              >
                <span className="font-option-name">{f.name}</span>
                <span className="font-option-sample">{f.sample}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Font Size Adjustment */}
        <div className="customizer-group">
          <div className="customizer-label-row">
            <span className="customizer-label" id="font-size-label">
              Base Font Size
            </span>
            <span className="customizer-value-pill">{prefs.fontSize}px</span>
          </div>
          <div className="font-size-slider-row">
            <button
              type="button"
              className="btn btn-secondary btn-sm size-step-btn"
              disabled={prefs.fontSize <= 12}
              onClick={() => updatePreferences({ ...prefs, fontSize: Math.max(12, prefs.fontSize - 0.5) })}
              aria-label="Decrease font size"
            >
              A-
            </button>
            <input
              type="range"
              id="font-size-slider"
              min="12"
              max="18"
              step="0.5"
              value={prefs.fontSize}
              onChange={(e) => updatePreferences({ ...prefs, fontSize: parseFloat(e.target.value) })}
              className="size-slider"
              aria-labelledby="font-size-label"
              aria-valuemin={12}
              aria-valuemax={18}
              aria-valuenow={prefs.fontSize}
            />
            <button
              type="button"
              className="btn btn-secondary btn-sm size-step-btn"
              disabled={prefs.fontSize >= 18}
              onClick={() => updatePreferences({ ...prefs, fontSize: Math.min(18, prefs.fontSize + 0.5) })}
              aria-label="Increase font size"
            >
              A+
            </button>
          </div>
        </div>

        {/* Live Preview Card */}
        <div className="live-preview-box" aria-label="Live theme preview">
          <div className="preview-badge-row">
            <span className="badge badge-primary">Citation [1]</span>
            <span className="badge badge-meta">arXiv:2504.01346</span>
          </div>
          <p className="preview-paragraph">
            PaperLens verifies claims directly against document paragraphs with deterministic locators:
            <code className="md-inline-code">accuracy &gt; 94.2%</code>.
          </p>
          <div className="preview-actions-row">
            <button type="button" className="btn btn-primary btn-sm">
              Primary Action
            </button>
            <button type="button" className="btn btn-secondary btn-sm">
              Secondary
            </button>
          </div>
        </div>
      </section>

      <section className="settings-section" aria-label="Account sign-in">
        <h3>Account</h3>
        {account.identities.length ? (
          <div className="account-connected">
            {account.identities.map((identity) => (
              <p key={identity.provider}>
                <strong>{identity.display_name}</strong>
                <span className="badge badge-neutral">{identity.provider === 'google' ? 'Google' : 'GitHub'}</span>
              </p>
            ))}
          </div>
        ) : (
          <p className="description">
            Sign in to access your saved profile, chats and memories from another installation using the same backend.
          </p>
        )}
        <div className="account-actions">
          {(['google', 'github'] as const).map((provider) => (
            <button
              key={provider}
              type="button"
              className="btn btn-secondary"
              disabled={busy || !account.auth_providers[provider]}
              onClick={() =>
                void action(async () => {
                  await client.signIn(provider);
                  await refresh();
                })
              }
            >
              Continue with {provider === 'google' ? 'Google' : 'GitHub'}
            </button>
          ))}
          {!!account.identities.length && (
            <button
              className="btn btn-ghost"
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  await client.signOut();
                  await refresh();
                })
              }
            >
              Sign out
            </button>
          )}
        </div>
        {(!account.auth_providers.google || !account.auth_providers.github) && (
          <p className="description">
            Unavailable sign-in providers need to be configured by the service owner. Your local profile can be used now.
          </p>
        )}
      </section>

      {!onboarding && (
        <section className="settings-section" aria-label="Long-term research memory">
          <h3>
            Long-term memory <span className="badge badge-neutral">{memories.length}</span>
          </h3>
          <p className="description">Only relevant memories are used in a new chat. Paper findings keep their original source.</p>
          <form
            className="memory-add"
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                await client.addMemory(note);
                setNote('');
                await reload();
              });
            }}
          >
            <label className="sr-only" htmlFor="memory-note">
              New research memory
            </label>
            <textarea
              id="memory-note"
              className="text-input"
              rows={2}
              minLength={12}
              maxLength={2000}
              required
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="A research goal, preference or important note…"
            />
            <button className="btn btn-secondary" disabled={busy || note.trim().length < 12}>
              Save memory
            </button>
          </form>
          {!memories.length && (
            <p className="empty-state-copy">No long-term memories yet. Important research context can be saved as you chat.</p>
          )}
          <ul className="memory-list">
            {memories.map((memory) => (
              <li key={memory.memory_id} className="memory-item">
                {editing === memory.memory_id ? (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void action(async () => {
                        await client.updateMemory(memory.memory_id, editText);
                        setEditing(null);
                        await reload();
                      });
                    }}
                  >
                    <label className="sr-only" htmlFor={'edit-' + memory.memory_id}>
                      Edit research memory
                    </label>
                    <textarea
                      id={'edit-' + memory.memory_id}
                      className="text-input"
                      required
                      minLength={12}
                      maxLength={2000}
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                    />
                    <div className="account-actions">
                      <button className="btn btn-secondary btn-sm" disabled={busy}>
                        Save
                      </button>
                      <button className="btn btn-ghost btn-sm" type="button" onClick={() => setEditing(null)}>
                        Cancel
                      </button>
                    </div>
                  </form>
                ) : (
                  <p>{memory.text}</p>
                )}
                <div className="memory-meta">
                  {memory.source_url ? (
                    <a href={memory.source_url} target="_blank" rel="noreferrer">
                      {memory.source_label}
                    </a>
                  ) : (
                    <span>{memory.source_label}</span>
                  )}
                  <span className="memory-item-actions">
                    <button
                      type="button"
                      className="text-action"
                      disabled={busy}
                      onClick={() => {
                        setEditing(memory.memory_id);
                        setEditText(memory.text);
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="text-action danger-action"
                      disabled={busy}
                      onClick={() =>
                        void action(async () => {
                          await client.deleteMemory(memory.memory_id);
                          await reload();
                        })
                      }
                    >
                      Forget
                    </button>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {error && (
        <p className="alert alert-danger" role="alert">
          {error}
        </p>
      )}
      {status && (
        <p className="description" role="status">
          {status}
        </p>
      )}
      {onboarding && (
        <p className="onboarding-privacy">
          Your profile is stored with this backend. Nationality does not determine the language or content of answers.
        </p>
      )}
    </section>
  );
}

export async function claimLegacyStorage(owner: string) {
  if (typeof chrome === 'undefined' || !chrome.storage?.local) return;
  const entries = await chrome.storage.local.get(null);
  if (entries.paperlens_legacy_owner) return;
  const migrated: Record<string, unknown> = { paperlens_legacy_owner: owner };
  for (const [key, value] of Object.entries(entries)) {
    const prefix = ['paperlens_chat_', 'paperlens_paper_'].find((prefix) => key.startsWith(prefix));
    if (prefix && !/^(anon_|account_)/.test(key.slice(prefix.length)))
      migrated[prefix + owner + ':' + key.slice(prefix.length)] = value;
  }
  await chrome.storage.local.set(migrated);
}
