/**
 * In-Page Floating PaperLens AI Research Agent Widget for arXiv pages.
 *
 * Provides:
 * 1. Floating Action Button (FAB) docked on page when hidden/minimized.
 * 2. Draggable & 8-direction resizable floating window (4 corners, 4 edges).
 * 3. Header controls: Minimize (_), Maximize/Restore (▢), Close (✕).
 * 4. Isolated Shadow DOM so arXiv CSS never interferes with PaperLens.
 * 5. Transparent pointer-events shield during drag and resize so iframe never eats mouse events.
 */

export function initOverlay(): void {
  // Only inject once in top frame of arXiv pages
  if (window.top !== window.self) return;
  if (document.getElementById('paperlens-agent-host')) return;

  const host = document.createElement('div');
  host.id = 'paperlens-agent-host';
  document.documentElement.appendChild(host);
  const shadow = host.attachShadow({ mode: 'open' });

  // Styles for FAB, floating modal, header, resizers, and iframe
  const style = document.createElement('style');
  style.textContent = `
    :host {
      all: initial;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    *,*::before,*::after { box-sizing:border-box; }

    /* Floating Action Button (FAB) */
    .paperlens-fab {
      position: fixed;
      right: 24px;
      bottom: 24px;
      z-index: 2147483647;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 10px 16px 10px 12px;
      background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 9999px;
      box-shadow: 0 4px 20px rgba(30, 58, 95, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: -0.01em;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      user-select: none;
    }

    .paperlens-fab:hover {
      transform: translateY(-2px) scale(1.03);
      box-shadow: 0 8px 28px rgba(30, 58, 95, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.2) inset;
      background: linear-gradient(135deg, #2563eb 0%, #1e3a5f 100%);
    }

    .paperlens-fab:active {
      transform: translateY(0) scale(0.98);
    }

    .paperlens-fab.hidden {
      display: none !important;
    }

    .fab-icon-glow {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .fab-dot {
      position: absolute;
      top: -1px;
      right: -1px;
      width: 7px;
      height: 7px;
      background-color: #10b981;
      border: 1.5px solid #0f172a;
      border-radius: 50%;
    }

    .fab-label {
      white-space: nowrap;
    }

    /* Floating Modal Window */
    .paperlens-modal {
      position: fixed;
      right: 24px;
      bottom: 24px;
      width: 460px;
      height: 700px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 32px);
      min-width: 320px;
      min-height: 400px;
      z-index: 2147483646;
      background: #0f172a;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 14px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      transform: scale(0.96) translateY(12px);
      pointer-events: none;
      transition: opacity 0.2s cubic-bezier(0.16, 1, 0.3, 1), transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .paperlens-modal.visible {
      opacity: 1;
      transform: scale(1) translateY(0);
      pointer-events: auto;
    }

    .paperlens-modal.maximized {
      width: min(920px, calc(100vw - 32px)) !important;
      height: min(860px, calc(100vh - 32px)) !important;
    }

    /* Header Bar */
    .modal-header {
      height: 40px;
      min-height: 40px;
      background: #0b1120;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px;
      cursor: grab;
      user-select: none;
    }

    .modal-header:active {
      cursor: grabbing;
    }

    .header-brand-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .header-title {
      font-size: 13px;
      font-weight: 700;
      color: #f8fafc;
      letter-spacing: -0.01em;
    }

    .header-badge {
      font-size: 10px;
      font-weight: 600;
      background: rgba(37, 99, 235, 0.2);
      color: #60a5fa;
      border: 1px solid rgba(37, 99, 235, 0.35);
      padding: 1px 6px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .header-btn {
      width: 26px;
      height: 26px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: transparent;
      border: none;
      border-radius: 6px;
      color: #94a3b8;
      cursor: pointer;
      transition: all 0.15s ease;
      padding: 0;
    }

    .header-btn:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #ffffff;
    }

    .header-btn.btn-close:hover {
      background: rgba(220, 38, 38, 0.2);
      color: #ef4444;
    }

    /* Iframe Container */
    .modal-body {
      flex: 1;
      position: relative;
      width: 100%;
      height: calc(100% - 40px);
      overflow: hidden;
      background: #ffffff;
    }

    .modal-iframe {
      width: 100%;
      height: 100%;
      border: none;
      display: block;
    }

    /* Transparent Drag Shield to prevent iframe capturing mouse events */
    .drag-shield {
      position: absolute;
      inset: 0;
      z-index: 9999;
      display: none;
      background: transparent;
    }

    .drag-shield.active {
      display: block !important;
    }

    /* 8-Way Resizer Handles */
    .resizer {
      position: absolute;
      z-index: 10000;
    }

    /* Corners (12px x 12px) */
    .resizer.nw {
      top: 0;
      left: 0;
      width: 14px;
      height: 14px;
      cursor: nwse-resize;
    }

    .resizer.ne {
      top: 0;
      right: 0;
      width: 14px;
      height: 14px;
      cursor: nesw-resize;
    }

    .resizer.sw {
      bottom: 0;
      left: 0;
      width: 14px;
      height: 14px;
      cursor: nesw-resize;
    }

    .resizer.se {
      bottom: 0;
      right: 0;
      width: 14px;
      height: 14px;
      cursor: nwse-resize;
    }

    .resizer { border:0; padding:0; background:transparent; touch-action:none; }
    .resizer::after { content:''; position:absolute; width:8px; height:8px; border:1.5px solid #93c5fd; border-radius:2px; background:#0f172a; opacity:0; transition:opacity .15s; }
    .paperlens-modal:hover .resizer::after,.paperlens-modal.transform-active .resizer::after,.resizer:focus-visible::after { opacity:1; }
    .resizer:focus-visible { outline:2px solid #60a5fa; outline-offset:-2px; }
    .resizer.nw::after { left:3px;top:3px; } .resizer.ne::after { right:3px;top:3px; }
    .resizer.sw::after { left:3px;bottom:3px; } .resizer.se::after { right:3px;bottom:3px; }
    .resizer.n::after,.resizer.s::after { left:50%;width:16px;height:5px;transform:translateX(-50%); }
    .resizer.n::after { top:1px; } .resizer.s::after { bottom:1px; }
    .resizer.w::after,.resizer.e::after { top:50%;width:5px;height:16px;transform:translateY(-50%); }
    .resizer.w::after { left:1px; } .resizer.e::after { right:1px; }
    .paperlens-modal.transform-active { outline:2px solid #60a5fa; outline-offset:2px; }
    .transform-bar { display:flex;gap:5px;align-items:center;justify-content:center;padding:6px 10px;background:#111c30;color:#cbd5e1;font-size:10px; }
    .transform-bar[hidden] { display:none; } .transform-bar button { padding:4px 7px;border:1px solid #475569;border-radius:4px;background:transparent;color:#f1f5f9;cursor:pointer;font-size:11px; }
    .transform-bar button:focus-visible { outline:2px solid #93c5fd; }
    .paperlens-modal { min-width:min(320px,calc(100vw - 24px));min-height:min(380px,calc(100vh - 24px)); }
    @media(prefers-reduced-motion:reduce) { .paperlens-modal,.resizer::after,.paperlens-fab { transition:none; } }
    /* Edges */
    .resizer.n {
      top: 0;
      left: 14px;
      right: 14px;
      height: 6px;
      cursor: ns-resize;
    }

    .resizer.s {
      bottom: 0;
      left: 14px;
      right: 14px;
      height: 6px;
      cursor: ns-resize;
    }

    .resizer.w {
      left: 0;
      top: 14px;
      bottom: 14px;
      width: 6px;
      cursor: ew-resize;
    }

    .resizer.e {
      right: 0;
      top: 14px;
      bottom: 14px;
      width: 6px;
      cursor: ew-resize;
    }
  `;
  shadow.appendChild(style);

  // 1. Create Floating Action Button (FAB)
  const fab = document.createElement('button');
  fab.className = 'paperlens-fab';
  fab.setAttribute('type', 'button');
  fab.setAttribute('title', 'Open PaperLens AI Scholar (Click to expand)');
  fab.setAttribute('aria-label', 'Open PaperLens Research Assistant');
  fab.innerHTML = `
    <div class="fab-icon-glow">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path>
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>
        <circle cx="12" cy="8" r="2"></circle>
      </svg>
      <span class="fab-dot"></span>
    </div>
    <span class="fab-label">PaperLens</span>
  `;
  shadow.appendChild(fab);

  // 2. Create Floating Modal Window
  const modal = document.createElement('div');
  modal.className = 'paperlens-modal';
  modal.innerHTML = `
    <!-- Header with Drag Handle & Window Controls -->
    <div class="modal-header">
      <div class="header-brand-group">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>
          <circle cx="12" cy="8" r="2"></circle>
        </svg>
        <span class="header-title">PaperLens Scholar</span>
        <span class="header-badge">Agent</span>
      </div>
      <div class="header-actions">
        <!-- Minimize (Thanh ẩn) -->
        <button type="button" class="header-btn btn-minimize" title="Minimize to floating button (_)" aria-label="Minimize">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"></line></svg>
        </button>
        <button type="button" class="header-btn btn-transform" title="Free transform" aria-label="Free transform" aria-pressed="false"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5M7 7h10v10H7z"/></svg></button>
        <!-- Maximize / Expand (Mở rộng) -->
        <button type="button" class="header-btn btn-maximize" title="Expand / Restore window (▢)" aria-label="Expand or Restore">
          <svg class="icon-max" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg>
        </button>
        <!-- Close (✕) -->
        <button type="button" class="header-btn btn-close" title="Close (✕)" aria-label="Close">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
    </div>

    <!-- 8 Resizer Handles for 4 corners and 4 edges -->
    <button type="button" class="resizer nw" aria-label="Resize top left" title="Resize top left; arrow keys resize, Shift for larger steps"></button>
    <button type="button" class="resizer ne" aria-label="Resize top right" title="Resize top right; arrow keys resize, Shift for larger steps"></button>
    <button type="button" class="resizer sw" aria-label="Resize bottom left" title="Resize bottom left; arrow keys resize, Shift for larger steps"></button>
    <button type="button" class="resizer se" aria-label="Resize bottom right" title="Resize bottom right; arrow keys resize, Shift for larger steps"></button>
    <button type="button" class="resizer n" aria-label="Resize top" title="Resize top; arrow keys resize, Shift for larger steps"></button>
    <button type="button" class="resizer s" aria-label="Resize bottom" title="Resize bottom; arrow keys resize, Shift for larger steps"></button>
    <button type="button" class="resizer w" aria-label="Resize left" title="Resize left; arrow keys resize, Shift for larger steps"></button>
    <button type="button" class="resizer e" aria-label="Resize right" title="Resize right; arrow keys resize, Shift for larger steps"></button>

    <div class="transform-bar" hidden><span>Free transform</span><button type="button" data-size="width:-40" aria-label="Decrease width">W−</button><button type="button" data-size="width:40" aria-label="Increase width">W+</button><button type="button" data-size="height:-40" aria-label="Decrease height">H−</button><button type="button" data-size="height:40" aria-label="Increase height">H+</button><button type="button" data-size="reset">Reset</button><button type="button" data-size="done">Done</button></div>
    <!-- Body Container with Iframe and Drag Shield -->
    <div class="modal-body">
      <div class="drag-shield"></div>
      <iframe class="modal-iframe" src="${chrome.runtime.getURL('sidepanel/index.html')}" allow="clipboard-read; clipboard-write"></iframe>
    </div>
  `;
  shadow.appendChild(modal);

  // Element references
  const header = modal.querySelector('.modal-header') as HTMLElement;
  const btnMinimize = modal.querySelector('.btn-minimize') as HTMLButtonElement;
  const btnMaximize = modal.querySelector('.btn-maximize') as HTMLButtonElement;
  const btnClose = modal.querySelector('.btn-close') as HTMLButtonElement;
  const dragShield = modal.querySelector('.drag-shield') as HTMLElement;

  // Toggle Visibility
  function openModal() {
    fab.classList.add('hidden');
    modal.classList.add('visible');
  }

  function closeModal() {
    modal.classList.remove('visible');
    fab.classList.remove('hidden');
  }

  fab.addEventListener('click', openModal);
  btnMinimize.addEventListener('click', closeModal);
  window.addEventListener('paperlens-reveal-source', closeModal);
  btnClose.addEventListener('click', closeModal);

  // Maximize / Restore Toggle
  let isMaximized = false;
  let prevRect = { width: '460px', height: '700px', left: '', top: '', right: '24px', bottom: '24px' };
  const positionMaximized=()=>Object.assign(modal.style,{
    left:`${Math.max(16,(innerWidth-Math.min(920,innerWidth-32))/2)}px`,
    top:`${Math.max(16,(innerHeight-Math.min(860,innerHeight-32))/2)}px`,right:'auto',bottom:'auto'});

  btnMaximize.addEventListener('click', () => {
    setTransform(false);
    isMaximized = !isMaximized;
    if (isMaximized) {
      prevRect = {
        width: modal.style.width || '460px',
        height: modal.style.height || '700px',
        left: modal.style.left,
        top: modal.style.top,
        right: modal.style.right || '24px',
        bottom: modal.style.bottom || '24px',
      };
      modal.classList.add('maximized');
      positionMaximized();
    } else {
      modal.classList.remove('maximized');
      Object.assign(modal.style,prevRect);
    }
  });

  // One geometry path for dragging, eight resize handles, buttons and keyboard.
  const margin = 12;
  const geometryKey = 'paperlens_window_geometry';
  type Rect = {left:number;top:number;width:number;height:number};
  const clamp = (value:number,min:number,max:number) => Math.max(min,Math.min(value,max));
  const readRect = ():Rect => {const r=modal.getBoundingClientRect();return {left:r.left,top:r.top,width:r.width,height:r.height};};
  function apply(rect:Rect) {
    const width=clamp(rect.width,Math.min(320,innerWidth-margin*2),innerWidth-margin*2);
    const height=clamp(rect.height,Math.min(380,innerHeight-margin*2),innerHeight-margin*2);
    Object.assign(modal.style,{width:width+'px',height:height+'px',left:clamp(rect.left,margin,innerWidth-width-margin)+'px',
      top:clamp(rect.top,margin,innerHeight-height-margin)+'px',right:'auto',bottom:'auto'});
  }
  const persist = () => {if(typeof chrome!=='undefined' && chrome.storage?.local) void chrome.storage.local.set({[geometryKey]:readRect()});};
  if(typeof chrome!=='undefined' && chrome.storage?.local) void chrome.storage.local.get(geometryKey).then(saved=>{
    const r=saved[geometryKey]; if(r && ['left','top','width','height'].every(key=>Number.isFinite(r[key]))) apply(r);
  });
  const transformButton=modal.querySelector<HTMLButtonElement>('.btn-transform')!;
  const transformBar=modal.querySelector<HTMLElement>('.transform-bar')!;
  const setTransform=(active:boolean)=>{
    if(active && isMaximized)btnMaximize.click();
    modal.classList.toggle('transform-active',active);transformBar.hidden=!active;
    transformButton.setAttribute('aria-pressed',String(active));
  };
  transformButton.addEventListener('click',()=>setTransform(!modal.classList.contains('transform-active')));
  transformBar.addEventListener('click',event=>{
    const size=(event.target as HTMLElement).closest<HTMLElement>('[data-size]')?.dataset.size;
    if(!size)return;
    if(size==='done'){setTransform(false);transformButton.focus();return;}
    if(size==='reset'){apply({left:innerWidth-484,top:Math.max(margin,innerHeight-724),width:460,height:700});}
    else {const [axis,delta]=size.split(':');const r=readRect();apply({...r,[axis]:r[axis as 'width'|'height']+Number(delta)});}
    persist();
  });
  let operation:{rect:Rect;x:number;y:number;direction:string;target:HTMLElement}|null=null;
  function resized(rect:Rect,direction:string,dx:number,dy:number):Rect {
    let {left,top,width,height}=rect;
    const minW=Math.min(320,innerWidth-margin*2),minH=Math.min(380,innerHeight-margin*2);
    if(direction.includes('e'))width=clamp(rect.width+dx,minW,innerWidth-left-margin);
    if(direction.includes('w')){left=clamp(rect.left+dx,margin,rect.left+rect.width-minW);width=rect.left+rect.width-left;}
    if(direction.includes('s'))height=clamp(rect.height+dy,minH,innerHeight-top-margin);
    if(direction.includes('n')){top=clamp(rect.top+dy,margin,rect.top+rect.height-minH);height=rect.top+rect.height-top;}
    return {left,top,width,height};
  }
  const begin=(event:PointerEvent,direction:string,target:HTMLElement)=>{
    if(event.button!==0 || isMaximized)return;
    operation={rect:readRect(),x:event.clientX,y:event.clientY,direction,target};
    target.setPointerCapture?.(event.pointerId);dragShield.classList.add('active');
    event.preventDefault();event.stopPropagation();
  };
  header.addEventListener('pointerdown',event=>{if(!(event.target as HTMLElement).closest('.header-btn'))begin(event,'move',header);});
  modal.querySelectorAll<HTMLButtonElement>('.resizer').forEach(handle=>{
    const direction=Array.from(handle.classList).find(c=>/^(nw|ne|sw|se|n|s|w|e)$/.test(c))!;
    handle.addEventListener('pointerdown',event=>begin(event,direction,handle));
    handle.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key) || isMaximized)return;
      const step=event.shiftKey ? 40 : 10;
      apply(resized(readRect(),direction,event.key==='ArrowLeft' ? -step : event.key==='ArrowRight' ? step : 0,
        event.key==='ArrowUp' ? -step : event.key==='ArrowDown' ? step : 0));
      persist();event.preventDefault();
    });
  });
  window.addEventListener('pointermove',event=>{
    if(!operation)return;
    const {rect,direction,x,y}=operation,dx=event.clientX-x,dy=event.clientY-y;
    apply(direction==='move' ? {...rect,left:rect.left+dx,top:rect.top+dy} : resized(rect,direction,dx,dy));
  });
  const finish=()=>{if(operation){operation=null;dragShield.classList.remove('active');persist();}};
  window.addEventListener('pointerup',finish);window.addEventListener('pointercancel',finish);window.addEventListener('blur',finish);
  window.addEventListener('resize',()=>{if(modal.classList.contains('visible')){if(isMaximized)positionMaximized();else apply(readRect());}});
  modal.addEventListener('keydown',event=>{if(event.key==='Escape' && modal.classList.contains('transform-active')){setTransform(false);transformButton.focus();}});
}
