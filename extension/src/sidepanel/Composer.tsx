import React, { useState, useRef, useEffect } from 'react';
import { IconSend, IconStop, IconImage, IconX } from './Icons';
import { ComposerAttachment } from './useAgentRun';
import { ResearchLevel, CHAT_TOKEN_LIMIT } from '../api/types';

export interface ComposerProps {
  onSend: (text: string, images?: ComposerAttachment[], level?: ResearchLevel) => void;
  onStop: () => void;
  isBusy: boolean;
  disabled?: boolean;
  draftText?: string;
  onDraftChange?: (text: string) => void;
  placeholder?: string;
  tokensUsed?: number;
  tokenLimit?: number;
  exhausted?: boolean;
  usageEstimated?: boolean;
  level?: ResearchLevel;
  onLevelChange?: (level: ResearchLevel) => void;
}

export async function prepareImage(file: File): Promise<ComposerAttachment> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new Error('Only PNG, JPEG and WebP research images are supported.');
  if (file.size > 10 * 1024 * 1024) throw new Error('Choose an image smaller than 10 MB.');
  const bitmap = await createImageBitmap(file);
  try {
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    let dataUrl = canvas.toDataURL('image/jpeg', 0.9);
    if (dataUrl.length > 699000) dataUrl = canvas.toDataURL('image/jpeg', 0.65);
    if (dataUrl.length > 699000) throw new Error('This image is too detailed. Crop the relevant figure and attach it again.');
    return { id: crypto.randomUUID(), name: file.name.slice(0, 200), type: 'image/jpeg', size: Math.floor(dataUrl.length * 0.75), dataUrl };
  } finally { bitmap.close(); }
}

export const Composer: React.FC<ComposerProps> = ({ onSend, onStop, isBusy, disabled = false,
  draftText, onDraftChange, placeholder = 'Ask about the paper or an attached research image…',
  tokensUsed = 0, tokenLimit = CHAT_TOKEN_LIMIT, exhausted = false, usageEstimated = false, level: selectedLevel, onLevelChange,
}) => {
  const [internal, setInternal] = useState('');
  const [images, setImages] = useState<ComposerAttachment[]>([]);
  const [internalLevel, setLevel] = useState<ResearchLevel>('low');
  const level = selectedLevel ?? internalLevel;
  const [error, setError] = useState('');
  const [preparing, setPreparing] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const composing = useRef(false);
  const value = draftText ?? internal;
  const update = (text: string) => { setInternal(text); onDraftChange?.(text); };
  useEffect(() => { if (textarea.current) { textarea.current.style.height = 'auto'; textarea.current.style.height = `${Math.min(150, Math.max(42, textarea.current.scrollHeight))}px`; } }, [value]);

  const attach = async (files: File[]) => {
    if (disabled || exhausted || isBusy || preparing) return;
    setError(''); setPreparing(true);
    try {
      if (images.length + files.length > 3) throw new Error('Attach up to 3 research images per question.');
      const prepared = await Promise.all(files.map(prepareImage));
      setImages(previous => [...previous, ...prepared].slice(0, 3));
    } catch (err) { setError((err as Error).message); }
    finally { setPreparing(false); if (input.current) input.current.value = ''; }
  };
  const send = () => {
    if (isBusy) { onStop(); return; }
    if (disabled || exhausted || preparing || (!value.trim() && !images.length)) return;
    onSend(value.trim() || 'Analyze this research image and explain its relationship to the current paper where relevant.', images, level);
    update(''); setImages([]); setError('');
  };
  const used = Math.min(tokenLimit, Math.max(0, tokensUsed));
  const nearFull = used / tokenLimit >= 0.9;
  const label = exhausted ? 'Context is full. Start a new session.' : nearFull ? 'Context is almost full. Start a new session soon.' : 'Session context usage';
  return <footer className="composer-container" aria-label="Message Composer"
    onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); void attach(Array.from(event.dataTransfer.files)); }}>
    <input type="file" ref={input} accept="image/png,image/jpeg,image/webp" multiple hidden
      onChange={event => void attach(Array.from(event.target.files || []))} aria-label="Attach research images" />
    <div className="composer-box">
      <div className="composer-mode-bar" role="group" aria-label="Reasoning level">
        <span className="mode-label">Level</span>
        {(['low', 'medium', 'high'] as ResearchLevel[]).map(item => <button type="button" key={item}
          className={`mode-chip ${item === level ? 'active' : ''}`} aria-pressed={level === item}
          disabled={isBusy} onClick={() => { setLevel(item); onLevelChange?.(item); }}>{item[0].toUpperCase() + item.slice(1)}</button>)}
        <div className={`token-meter ${nearFull ? 'token-meter-warning' : ''}`} role="meter" aria-label="Session context" aria-valuemin={0} aria-valuemax={tokenLimit} aria-valuenow={used} aria-valuetext={label} title={label}>
          <svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="12" className="token-track" />
            <circle cx="16" cy="16" r="12" className="token-progress" pathLength="100" strokeDasharray={`${used / tokenLimit * 100} 100`} /></svg>
        </div>
      </div>
      {!!images.length && <div className="composer-attachments-row" aria-label="Attached research images">{images.map(image => <div key={image.id} className="attachment-chip">
        <img src={image.dataUrl} alt={image.name} className="attachment-thumb" /><span className="attachment-name">{image.name}</span>
        <button type="button" className="attachment-remove-btn" aria-label={`Remove ${image.name}`} onClick={() => setImages(previous => previous.filter(item => item.id !== image.id))}><IconX size={12} /></button>
      </div>)}</div>}
      <div className="composer-input-row">
        <label htmlFor="paperlens-composer-input" className="sr-only">Ask a research question</label>
        <textarea id="paperlens-composer-input" ref={textarea} className="composer-textarea" value={value} onChange={event => update(event.target.value)} onInput={event => update(event.currentTarget.value)}
          onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
          onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current) { event.preventDefault(); send(); } }}
          onPaste={event => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); void attach(files); } }}
          placeholder={placeholder} rows={1} maxLength={1024} disabled={disabled || exhausted} aria-label="Ask a question about this paper" />
        <div className="composer-actions">
          <button type="button" className="composer-icon-action-btn" onClick={() => input.current?.click()} disabled={disabled || isBusy || exhausted || preparing} aria-label="Upload figure or diagram" title="Attach research image"><IconImage size={16} /></button>
          <button type="button" className={`composer-btn ${isBusy ? 'composer-btn-stop' : 'composer-btn-send'}`} onClick={send}
            disabled={!isBusy && (disabled || exhausted || preparing || (!value.trim() && !images.length))} aria-label={isBusy ? 'Stop generating response' : 'Send question'}>
            {isBusy ? <IconStop size={15} /> : <IconSend size={15} />}<span>{isBusy ? 'Stop' : 'Send'}</span>
          </button>
        </div>
      </div>
    </div>
    {error && <p className="description text-warning" role="alert">{error}</p>}
    {exhausted || nearFull ? <p className="context-notice" role="status">{exhausted ? 'Context đã hết. Vui lòng tạo session mới.' : 'Context sắp hết. Vui lòng tạo session mới.'}</p> : <div className="composer-hint">{preparing ? 'Preparing image…' : 'Enter sends · Shift+Enter adds a line · Paste an image'}</div>}
  </footer>;
};
