import React from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { I18nProvider, LOCALES, useTranslation } from '@/i18n';

function Probe({ keyToRender }: { keyToRender: string }) {
  const { locale, setLocale, t } = useTranslation();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="translated">{t(keyToRender)}</span>
      <button onClick={() => setLocale('tr')} data-testid="to-tr">Türkçe</button>
    </div>
  );
}

describe('I18nProvider - Gökdoğan Türkçe dağıtım profili', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it('yalnızca Türkçe dil kaydını yayımlar', () => {
    expect(LOCALES).toEqual([{ code: 'tr', label: 'Türkçe' }]);
  });

  it('tarayıcı dili İngilizce olsa da Türkçe başlar', () => {
    Object.defineProperty(navigator, 'language', { value: 'en-US', configurable: true });
    render(
      <I18nProvider>
        <Probe keyToRender="settings.title" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('locale').textContent).toBe('tr');
    expect(screen.getByTestId('translated').textContent).toBe('Ayarlar');
  });

  it('tarayıcı dili Çince olsa da Türkçe başlar', () => {
    Object.defineProperty(navigator, 'language', { value: 'zh-CN', configurable: true });
    render(
      <I18nProvider>
        <Probe keyToRender="settings.title" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('locale').textContent).toBe('tr');
  });

  it('eski çok-dilli localStorage seçimini Türkçeye normalleştirir', () => {
    localStorage.setItem('sb_locale', 'en');
    localStorage.setItem('gokdogan_locale', 'zh-CN');
    render(
      <I18nProvider>
        <Probe keyToRender="settings.title" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('locale').textContent).toBe('tr');
    expect(localStorage.getItem('gokdogan_locale')).toBe('tr');
    expect(localStorage.getItem('sb_locale')).toBeNull();
  });

  it('setLocale çağrısında yalnız Türkçe tercihini kalıcılaştırır', () => {
    render(
      <I18nProvider>
        <Probe keyToRender="settings.title" />
      </I18nProvider>,
    );
    act(() => {
      screen.getByTestId('to-tr').click();
    });
    expect(localStorage.getItem('gokdogan_locale')).toBe('tr');
    expect(localStorage.getItem('sb_locale')).toBeNull();
  });

  it('eksik çeviri anahtarında anahtarın kendisine düşer', () => {
    render(
      <I18nProvider>
        <Probe keyToRender="this.key.intentionally.does.not.exist" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('translated').textContent).toBe(
      'this.key.intentionally.does.not.exist',
    );
  });
});
