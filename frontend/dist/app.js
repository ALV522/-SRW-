const {$,esc,fmt,api,toast,modal,closeModal}=window;
const state={page:'dashboard',projects:[],projectId:null,projectTab:'overview',candidateId:null,candidateSection:'evidence',candidateReturnTab:'candidates',providers:null,health:false,candidateQuery:'',candidateArchive:'active',candidateMaterial:'all',candidateStage:'all',candidatePage:0,candidateLimit:25,candidateRows:[],taskStatus:'',taskType:'',taskPage:0,taskLimit:50,cockpitPage:0,cockpitLimit:25,auditOffset:0,flowQuery:'',handoffPayload:null,jobSetupStep:1,jobSetupDraft:null,jobSetupSuggestions:[],criteriaStageDefs:[],criteriaRecruitmentContext:{},criteriaDecisionPolicy:{},criteriaBrief:{},criteriaOriginalByKey:{},criteriaDraftToken:'',decisionContextHash:''};
// Ephemeral drafts survive in-flight workbench redraws but never leave this browser session.
const materialDrafts=new Map();
window.state=state;window.materialDrafts=materialDrafts;
// Inline event-handler attributes (onclick/onchange) resolve in global scope, but these page
// entry points are module-scoped. Expose them explicitly so injected handlers resolve;
// scripts/check_frontend_contract.py fails the source gate if a handler reference is unassigned.
window.renderPage=renderPage;window.shell=shell;
// Inline handlers also mutate module state; the wrappers below own that mutation so the
// attributes stay global-scope-safe. scripts/check_frontend_contract.py fails the gate
// on any handler that still references a module-scope binding directly.
window.selectFlowCandidate=el=>{state.candidateId=el.value;return projectWorkspace()};
window.filterCandidatesByStage=k=>{state.candidateStage=k;return setProjectTab('candidates')};
function statusClass(s){if(['succeeded','confirmed','published','ready','active','open','hired','accepted','completed','approved'].includes(s))return'good';if(['failed','rejected','conflict','declined','withdrawn','cancelled','closed'].includes(s))return'bad';if(['waiting_provider','draft','missing','partial','paused','offer','scheduled','shortlisted'].includes(s))return'warn';return'info'}
const stageLabels={new:'新候选人',screening:'简历筛选',shortlisted:'短名单',phone_screen:'电话筛选',interview:'面试',offer:'Offer',hired:'录用',rejected:'拒绝',talent_pool:'人才池',withdrawn:'候选人退出'};const projectStatusLabels={draft:'草案',open:'招聘中',paused:'暂停招聘',filled:'已招满',closed:'已关闭',archived:'已归档'};const offerLabels={draft:'草案',approved:'已批准',sent:'已发送',accepted:'已接受',declined:'已拒绝',withdrawn:'已撤回'};function stageLabel(s){return stageLabels[s]||s||'—'};const workbenchActionLabels={RESOLVE_CONFLICT:'处理证据冲突',VERIFY_CRITERION:'核实评价标准',RUN_SCREEN:'完成简历筛选',PREPARE_INTERVIEW:'准备结构化面试',REVIEW_REEVALUATION:'复核重新评价',MAKE_DECISION:'提交人工决定'};function workbenchActionLabel(s){return workbenchActionLabels[s]||s||'待处理'}
const icons={dashboard:'▦',projects:'▣',templates:'▤',knowledge:'⌕',tasks:'⟳',settings:'⚙'};
function shell(){return `<div class="app-shell"><aside class="sidebar"><div class="logo"><div class="logo-mark">SRW</div><div><strong>智能招聘工作台</strong><small>v1.0 Convergence 11 · Business Workflow Closure</small></div></div><div class="nav-group">Recruitment OS</div>${[['dashboard','工作台总览'],['projects','招聘项目'],['templates','岗位模板'],['knowledge','知识库'],['tasks','后台任务'],['settings','系统设置']].map(([k,l])=>`<button class="nav-item ${state.page===k?'active':''}" onclick="go('${k}')"><span class="nav-icon">${icons[k]}</span><span>${l}</span></button>`).join('')}<div class="side-footer">本地优先 · 业务闭环 · 证据可追溯<br>AI 建议 ≠ 人工决定<br><span id="side-health">正在检查服务…</span></div></aside><main class="main"><header class="topbar"><div class="top-title" id="top-title"></div><div class="top-right"><span id="service-health-badge" class="badge" role="status" aria-live="polite"><span id="service-health-dot" class="dot ${state.health?'good':''}"></span><span id="service-health-text">${state.health?'服务正常':'服务检查中'}</span></span><span class="badge">v1_0014</span></div></header><div class="content" id="content"></div></main></div>`}
window.go=async p=>{state.page=p;state.candidateId=null;state.candidateSection='evidence';document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;await renderPage()};window.openWorkbenchItem=async(pid,cid,type)=>{state.page='projects';state.projectId=pid;state.candidateReturnTab=type==='PREPARE_INTERVIEW'?'flow':'cockpit';state.projectTab=state.candidateReturnTab;state.candidateId=type==='PREPARE_INTERVIEW'?null:cid;state.candidateSection='evidence';document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;await renderPage()};window.openOperationalItem=async(kind,pid,cid,eid)=>{state.page='projects';state.projectId=pid;state.candidateReturnTab='overview';state.projectTab=kind==='pending_interview_feedback'?'flow':'overview';state.candidateId=['overdue_contact','today_contact'].includes(kind)?(cid||null):null;state.candidateSection='process';document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;await renderPage();if(['overdue_contact','today_contact'].includes(kind)&&cid)await openActionPlan(cid);if(kind==='pending_interview_feedback'&&eid)await openScorecards(eid)};window.openReviewItem=async(kind,pid,cid,reviewId='',claimId='')=>{
  state.page='projects';state.projectId=pid;state.candidateReturnTab='quality';
  state.projectTab=kind==='unreviewed_claim'?'candidates':'quality';
  state.candidateId=kind==='unreviewed_claim'?(cid||null):null;
  state.candidateSection='evidence';
  document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;
  await renderPage();
  const focusId=kind==='unreviewed_claim'?(claimId?'srw-claim-'+claimId:''):(reviewId?'srw-review-'+reviewId:'');
  if(!focusId)return;
  const target=document.getElementById(focusId);
  if(!target){toast('该复核项可能已处理或不在当前页面，请核对队列。',true);return}
  target.classList.add('review-item-focused');
  target.scrollIntoView({block:'center',behavior:'auto'});
  const button=target.querySelector('button');
  if(button)button.focus({preventScroll:true});
};
async function init(){await ensureCarrierSession();document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;try{await api('/health/ready');state.health=true}catch{}await renderPage();}
async function renderPage(){const t={dashboard:'工作台总览',projects:'招聘项目',templates:'岗位模板',knowledge:'知识库',tasks:'后台任务',settings:'系统设置'}[state.page]||'工作台';$('#top-title').textContent=t;if($('#side-health'))$('#side-health').textContent=state.health?'服务已就绪 · 本地数据':'服务状态待确认';const healthText=$('#service-health-text'),healthDot=$('#service-health-dot');if(healthText)healthText.textContent=state.health?'服务正常':'服务检查中';if(healthDot)healthDot.classList.toggle('good',Boolean(state.health));const fn={dashboard:window.dashboardPage,projects:projectsPage,templates:window.templatesPage,knowledge:window.knowledgePage,tasks:window.tasksPage,settings:window.settingsPage}[state.page];try{await fn()}catch(e){$('#content').innerHTML=`<div class="panel"><div class="panel-body empty"><strong>页面加载失败</strong>${esc(e.message)}</div></div>`}}
function head(title,desc,actions=''){return `<div class="page-head"><div><h1>${title}</h1><p>${desc}</p></div><div class="actions">${actions}</div></div>`}



init();

/* Core helpers published for the extracted domain modules (ADR-0002 split). */
window.head=head;window.statusClass=statusClass;window.stageLabel=stageLabel;window.workbenchActionLabel=workbenchActionLabel;window.stageLabels=stageLabels;window.offerLabels=offerLabels;window.projectStatusLabels=projectStatusLabels;window.icons=icons;