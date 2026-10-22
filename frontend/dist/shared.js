/* SRW shared frontend infrastructure (ADR-0002 consolidation).
 * Loaded first; every symbol is published on window so ES-module scopes and
 * inline handlers resolve the same implementation. Behavior union:
 * - toast guards a missing #toast-root and uses the 3600ms shim timing;
 * - modal escapes its title (shim behavior) and modalWide keeps the wide
 *   variant (min(1120px,94vw)) the convergence shims rendered with.
 */
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('zh-CN').format(Number(n||0));
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});const ct=r.headers.get('content-type')||'';const body=ct.includes('json')?await r.json():await r.text();if(!r.ok)throw new Error(body?.detail||body?.error?.code||String(body));return body}
function toast(msg,err=false){const root=$('#toast-root');if(!root)return;root.innerHTML=`<div class="toast ${err?'error':''}">${esc(msg)}</div>`;setTimeout(()=>root.innerHTML='',3600)}
function modal(title,body,foot=''){const root=$('#modal-root');if(!root)return;root.innerHTML=`<div class="modal-backdrop"><div class="modal"><div class="modal-head"><h3>${esc(title)}</h3><button class="x" onclick="closeModal()">×</button></div><div class="modal-body">${body}</div>${foot?`<div class="modal-foot">${foot}</div>`:''}</div></div>`}
function modalWide(title,body,foot=''){const root=$('#modal-root');if(!root)return;root.innerHTML=`<div class="modal-backdrop"><div class="modal" style="width:min(1120px,94vw);max-width:1120px"><div class="modal-head"><h3>${esc(title)}</h3><button class="x" onclick="closeModal()">×</button></div><div class="modal-body">${body}</div>${foot?`<div class="modal-foot">${foot}</div>`:''}</div></div>`}
window.$=$;window.esc=esc;window.fmt=fmt;window.api=api;window.toast=toast;window.modal=modal;window.modalWide=modalWide;
window.closeModal=()=>{const root=$('#modal-root');if(root)root.innerHTML=''};
