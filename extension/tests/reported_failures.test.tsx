/** @vitest-environment jsdom */
import React,{act} from 'react';import {createRoot} from 'react-dom/client';import {it,expect,vi} from 'vitest';
import {Answer} from '../src/sidepanel/Answer';import {MarkdownRenderer} from '../src/sidepanel/MarkdownRenderer';
import {parseArxivDocument} from '../src/content/parser';import {verifyParagraphTarget} from '../src/content/navigation';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
it('renders actual LaTeX fractions, sums and subscripts instead of raw source',async()=>{
 const el=document.createElement('div');const root=createRoot(el);
 await act(async()=>root.render(<MarkdownRenderer content={String.raw`Inline \(\alpha_i\).\n\n$$\pi_{t+1}=\alpha P^T\pi_t+(1-\alpha)q,\quad \frac{a}{b}=\sum_{i=1}^{n}x_i$$`.replaceAll('\\n','\n')} />));
 expect(el.querySelector('.katex .mfrac')).not.toBeNull();expect(el.querySelector('.katex .msupsub')).not.toBeNull();
 await act(async()=>root.unmount());
});
it('keeps identifier underscores from swallowing a later inline formula',async()=>{
 const el=document.createElement('div');const root=createRoot(el);
 await act(async()=>root.render(<MarkdownRenderer content={String.raw`The figure img_1 shows the local nodes \(\mathcal{V}_{\text{local}}\), with _emphasis_.`} />));
 expect(el.querySelector('.katex annotation')?.textContent).toBe(String.raw`\mathcal{V}_{\text{local}}`);
 expect(el.textContent).toContain('img_1');expect(el.querySelector('em')?.textContent).toBe('emphasis');
 await act(async()=>root.unmount());
});
it('jumps using the cited answer’s own evidence rather than the latest turn',async()=>{
 const el=document.createElement('div');const root=createRoot(el);const jump=vi.fn();const select=vi.fn();
 const evidence:any={passage_id:'old-p',parent_passage_id:'old-p',rank:1,score:1,section_heading:'Old method',section_path:'Method',text:'Original source',fingerprint:'fp',locator:{element_id:'old-source'}};
 await act(async()=>root.render(<Answer answerBlocks={[{text:'An earlier answer.',evidence_ids:['old-p']}]} evidence={[evidence]} onSelectEvidence={select} onJump={jump}/>));
 await act(async()=>el.querySelector<HTMLButtonElement>('.citation-link')!.click());
 expect(jump).toHaveBeenCalledWith(evidence);expect(el.querySelector('.citation-link')?.textContent).toBe('1');
 await act(async()=>root.unmount());
});
it('produces unique paragraph locators whose fingerprints match multi-paragraph wrappers',async()=>{
 document.body.innerHTML='<article class="ltx_document"><section id="S1" class="ltx_section"><h2>Method</h2><div id="S1.p1" class="ltx_para"><p class="ltx_p">First scientific paragraph with sufficient content.</p><p class="ltx_p">Second scientific paragraph in the same wrapper.</p></div></section></article>';
 const paper=await parseArxivDocument(document,'https://arxiv.org/html/2504.01346v4');
 expect(new Set(paper.paragraphs.map(p=>p.id)).size).toBe(paper.paragraphs.length);
 for(const p of paper.paragraphs){const result=await verifyParagraphTarget(document,{...p.locator,arxivId:'2504.01346',version:'v4',fingerprint:p.fingerprint});expect(result.verified).toBe(true);}
});

it('keeps literal code and rejects unsafe math commands without losing the answer',async()=>{
 const el=document.createElement('div');const root=createRoot(el);
 await act(async()=>root.render(<MarkdownRenderer content={String.raw`Code: \`$x_i$\`. Math: \(\href{javascript:alert(1)}{x}\). More: \(\frac{1}{2}\).`.replaceAll('\\`','`')} />));
 expect(el.querySelector('a[href^="javascript:"]')).toBeNull();expect(el.querySelector('.katex .mfrac')).not.toBeNull();
 await act(async()=>root.unmount());
});

it('recovers an older wrapper citation by exact leaf fingerprint',async()=>{
 const {computeParagraphFingerprint}=await import('../src/content/parser');
 document.body.innerHTML='<section id="legacy"><div id="legacy-p"><p>Earlier paragraph with exact original wording.</p><p>A different paragraph in the same wrapper.</p></div></section>';
 const fingerprint=await computeParagraphFingerprint('Earlier paragraph with exact original wording.');
 const result=await verifyParagraphTarget(document,{elementId:'legacy-p',arxivId:'2504.01346',version:'v4',fingerprint});
 expect(result.verified).toBe(true);expect(result.element?.tagName).toBe('P');
});

it('extracts standalone equation groups once with readable TeX and precise locators',async()=>{
 document.body.innerHTML='<article class="ltx_document"><section id="S1"><h2>Method</h2><div class="ltx_para" id="S1.p1"><table id="S1.E1" class="ltx_equationgroup"><tbody><tr class="ltx_equation"><td><math alttext="r_{t+1}=P^T r_t"><mi>r</mi></math></td></tr></tbody></table></div></section></article>';
 const paper=await parseArxivDocument(document,'https://arxiv.org/html/2504.01346v4');
 expect(paper.paragraphs).toHaveLength(1);expect(paper.paragraphs[0].id).toBe('S1.E1');
 expect(paper.paragraphs[0].text).toContain('$r_{t+1}=P^T r_t$');
});
