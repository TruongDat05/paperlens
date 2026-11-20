/**
 * Store reading history and source notes locally in Chrome.
 *
 * Manage saved answers, saved evidence, and history by owner and paper
 * version in chrome.storage.local. Provide save, delete, and Markdown export
 * actions.
 *
 * Keep the title, arXiv ID and version, section, source link, and save date.
 * Label verbatim quotes and model-generated explanations separately.
 */

export interface SavedNote {
  id: string;
  paperId: string;
  arxivId: string;
  version: string;
  title: string;
  canonicalUrl: string;
  text: string;
  type: 'answer' | 'quote';
  sectionPath?: string;
  evidenceId?: string;
  savedAt: string;
}

const STORAGE_KEY = 'paperlens_saved_notes';

// In-memory fallback storage for tests
let _mockNotesStore: SavedNote[] = [];

export async function saveNote(
  noteInput: Omit<SavedNote, 'id' | 'savedAt'>
): Promise<SavedNote> {
  const note: SavedNote = {
    ...noteInput,
    id: `note_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    savedAt: new Date().toISOString(),
  };

  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    const data = await chrome.storage.local.get(STORAGE_KEY);
    const notes: SavedNote[] = data[STORAGE_KEY] || [];
    notes.push(note);
    await chrome.storage.local.set({ [STORAGE_KEY]: notes });
  } else {
    _mockNotesStore.push(note);
  }

  return note;
}

export async function getNotes(arxivId?: string): Promise<SavedNote[]> {
  let notes: SavedNote[] = [];
  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    const data = await chrome.storage.local.get(STORAGE_KEY);
    notes = data[STORAGE_KEY] || [];
  } else {
    notes = [..._mockNotesStore];
  }

  if (arxivId) {
    return notes.filter((n) => n.arxivId === arxivId);
  }
  return notes;
}

export async function deleteNote(id: string): Promise<void> {
  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    const data = await chrome.storage.local.get(STORAGE_KEY);
    const notes: SavedNote[] = data[STORAGE_KEY] || [];
    const filtered = notes.filter((n) => n.id !== id);
    await chrome.storage.local.set({ [STORAGE_KEY]: filtered });
  } else {
    _mockNotesStore = _mockNotesStore.filter((n) => n.id !== id);
  }
}

export function exportNotesToMarkdown(
  notes: SavedNote[],
  paperTitle: string,
  canonicalUrl: string
): string {
  const lines: string[] = [];
  lines.push(`# PaperLens Notes: ${paperTitle}`);
  lines.push(`Source: [${canonicalUrl}](${canonicalUrl})`);
  lines.push(`Exported on: ${new Date().toLocaleDateString()}`);
  lines.push('');

  const answers = notes.filter((n) => n.type === 'answer');
  if (answers.length > 0) {
    lines.push('## Saved Explanations & Answers');
    for (const ans of answers) {
      lines.push(`- **Answer** (Saved ${new Date(ans.savedAt).toLocaleString()}):`);
      lines.push(`  > ${ans.text.replace(/\n/g, '\n  > ')}`);
      lines.push('');
    }
  }

  const quotes = notes.filter((n) => n.type === 'quote');
  if (quotes.length > 0) {
    lines.push('## Saved Evidence Quotes');
    for (const q of quotes) {
      const sec = q.sectionPath ? ` [${q.sectionPath}]` : '';
      lines.push(`- **Quote**${sec} (Saved ${new Date(q.savedAt).toLocaleString()}):`);
      lines.push(`  > "${q.text.replace(/\n/g, '\n  > ')}"`);
      lines.push('');
    }
  }

  return lines.join('\n');
}
