import './api-client.js'; // Explicit dependency: the global client must initialize before the workbench.
import {ensureBusinessSession} from './session-entry.js';
import {createReevaluationFeature} from './reevaluation.js';
import {createJobSetupFeature} from './jobsetup.js';
import {mountProjectResume} from './task-resume-ui.js';
const state={page:'dashboard',projects:[],projectId:null,projectTab:'overview',overviewSection:null,candidateView:'all',flowCandidateId:null,candidateId:null,candidateSection:'evidence',candidateReturnTab:'candidates',providers:null,health:false,candidateQuery:'',candidateArchive:'active',candidateMaterial:'all',candidateStage:'all',candidatePage:0,candidateLimit:25,candidateRows:[],taskStatus:'',taskType:'',taskPage:0,taskLimit:50,cockpitPage:0,cockpitLimit:25,auditOffset:0,flowQuery:'',handoffPayload:null,jobSetupStep:1,jobSetupDraft:null,jobSetupSuggestions:[],criteriaStageDefs:[],criteriaRecruitmentContext:{},criteriaDecisionPolicy:{},criteriaBrief:{},criteriaOriginalByKey:{}};
// Ephemeral drafts survive in-flight workbench redraws but never leave this browser session.
const materialDrafts=new Map();
const $=s=>document.querySelector(s); const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat('zh-CN').format(Number(n||0));
const api=(path,opts)=>window.srwApi(path,opts); /* R4: implementation lives in api-client.js */
function toast(msg,err=false){const root=$('#toast-root');root.innerHTML=`<div class="toast ${err?'error':''}">${esc(msg)}</div>`;setTimeout(()=>root.innerHTML='',3200)}
function modal(title,body,foot=''){state.modalGeneration=(state.modalGeneration||0)+1;const root=$('#modal-root');root.innerHTML=`<div class="modal-backdrop"><div class="modal"><div class="modal-head"><h3>${title}</h3><button class="x" onclick="closeModal()">×</button></div><div class="modal-body">${body}</div>${foot?`<div class="modal-foot">${foot}</div>`:''}</div></div>`}
window.closeModal=()=>{state.modalGeneration=(state.modalGeneration||0)+1;state.eventDraft=null;$('#modal-root').innerHTML=''};
function statusClass(s){if(['succeeded','confirmed','published','ready','active','open','hired','accepted','completed','approved'].includes(s))return'good';if(['failed','rejected','conflict','declined','withdrawn','cancelled','closed'].includes(s))return'bad';if(['waiting_provider','draft','missing','partial','paused','offer','scheduled','shortlisted'].includes(s))return'warn';return'info'}
const stageLabels={new:'新候选人',screening:'简历筛选',shortlisted:'短名单',phone_screen:'电话筛选',interview:'面试',offer:'Offer',hired:'录用',rejected:'拒绝',talent_pool:'人才池',withdrawn:'候选人退出'};const projectStatusLabels={draft:'草案',open:'招聘中',paused:'暂停招聘',filled:'已招满',closed:'已关闭',archived:'已归档'};const offerLabels={draft:'草案',approved:'已批准',sent:'已发送',accepted:'已接受',declined:'已拒绝',withdrawn:'已撤回'};const offerNextStatuses={draft:['approved','withdrawn'],approved:['sent','withdrawn'],sent:['accepted','declined','withdrawn'],accepted:[],declined:[],withdrawn:[]};function stageLabel(s){return stageLabels[s]||s||'—'};const workbenchActionLabels={RESOLVE_CONFLICT:'处理证据冲突',VERIFY_CRITERION:'核实评价标准',RUN_SCREEN:'完成简历筛选',PREPARE_INTERVIEW:'准备结构化面试',REVIEW_REEVALUATION:'复核重新评价',MAKE_DECISION:'提交人工决定'};function workbenchActionLabel(s){return workbenchActionLabels[s]||s||'待处理'}
const icons={dashboard:'▦',projects:'▣',templates:'▤',knowledge:'⌕',tasks:'⟳',settings:'⚙'};
function shell(){return `<div class="app-shell"><aside class="sidebar"><div class="logo"><div class="logo-mark">SRW</div><div><strong>智能招聘工作台</strong><small>v1.0 Convergence 11 · Business Workflow Closure</small></div></div><div id="restore-banner-host">${restoreBannerHtml()}</div><div class="nav-group">Recruitment OS</div>${[['dashboard','今日待办'],['projects','招聘项目'],['settings','设置']].map(([k,l])=>`<button class="nav-item ${(state.page===k||(k==='settings'&&['settings','templates','knowledge','tasks'].includes(state.page)))?'active':''}" onclick="go('${k}')"><span class="nav-icon">${icons[k]}</span><span>${l}</span></button>`).join('')}<div class="side-footer">本地优先 · 业务闭环 · 证据可追溯<br>AI 建议 ≠ 人工决定<br><span id="side-health">正在检查服务…</span></div></aside><main class="main"><header class="topbar"><div class="top-left"><button type="button" class="top-back" id="top-back" onclick="topBack()" hidden>&larr; 返回</button><span class="top-title" id="top-title"></span><span class="crumb-tail" id="top-crumb"></span></div><div class="top-right"><span id="service-health-badge" class="badge" role="status" aria-live="polite"><span id="service-health-dot" class="dot ${state.health?'good':''}"></span><span id="service-health-text">${state.health?'服务正常':'服务检查中'}</span></span><span class="badge">v1_0014</span></div></header><div class="content" id="content"></div></main></div>`}
window.go=async p=>{state.page=p;if(p!=='projects'){state.projectId=null;state.flowCandidateId=null;state.overviewSection=null;}state.candidateId=null;state.currentCandidateId=null;state.currentCandidateName=null;state.candidateSection='evidence';document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;await renderPage()};window.openWorkbenchItem=async(pid,cid,type)=>{state.page='projects';state.projectId=pid;state.candidateReturnTab=type==='PREPARE_INTERVIEW'?'flow':'cockpit';state.projectTab=state.candidateReturnTab;state.flowCandidateId=type==='PREPARE_INTERVIEW'?(cid||null):null;state.candidateId=type==='PREPARE_INTERVIEW'?null:cid;state.candidateSection='evidence';document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;await renderPage()};window.openOperationalItem=async(kind,pid,cid,eid)=>{
  // #253: a dashboard item is a Core-authored hint, not durable authority.
  // Revalidate the exact completed-interview target before leaving home.
  const seq=(state.operationalOpenSeq||0)+1;
  state.operationalOpenSeq=seq;
  const modalGeneration=state.modalGeneration||0;
  const stillOnDashboard=()=>state.page==='dashboard'
    &&state.operationalOpenSeq===seq&&(state.modalGeneration||0)===modalGeneration;
  if(kind==='pending_interview_feedback'){
    if(!stillOnDashboard()||!pid||!cid||!eid){
      toast('待反馈面试缺少准确对象，请刷新今日待办。',true);return;
    }
    try{
      const latest=await api('/api/v1/dashboard');
      if(!stillOnDashboard())return;
      const current=(latest.operational_queue?.items||[]).some(item=>
        item.kind==='pending_interview_feedback'&&item.project_id===pid
        &&item.candidate_id===cid&&item.event_id===eid);
      if(!current){toast('待反馈面试已变化，请刷新今日待办。',true);return}
    }catch(e){
      if(stillOnDashboard())toast('无法重新核验待反馈面试，请刷新今日待办。',true);
      return;
    }
  }
  if(state.operationalOpenSeq!==seq||state.page!=='dashboard')return;
  state.page='projects';state.projectId=pid;state.candidateReturnTab='overview';
  state.projectTab=kind==='pending_interview_feedback'?'flow':'overview';
  state.flowCandidateId=kind==='pending_interview_feedback'?(cid||null):null;
  state.candidateId=['overdue_contact','today_contact'].includes(kind)?(cid||null):null;
  state.candidateSection='process';
  document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;
  await renderPage();
  if(state.operationalOpenSeq!==seq||state.page!=='projects'||state.projectId!==pid)return;
  if(['overdue_contact','today_contact'].includes(kind)&&cid)await openActionPlan(cid);
  if(kind==='pending_interview_feedback'&&eid&&cid)await openScorecards(cid,eid);
};window.openReviewItem=async(kind,pid,cid,reviewId='',claimId='')=>{
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
async function init(){try{await ensureBusinessSession()}catch(e){document.getElementById('app').textContent=e.message;return}try{await api('/health/ready');state.health=true}catch{}await refreshRestoreStatus();document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;await renderPage();}

function syncTopbar(){
  const host=$('#top-crumb'),back=$('#top-back');
  if(!host&&!back)return;
  const inProject=state.page==='projects'&&Boolean(state.projectId);
  const p=inProject?(state.projects||[]).find(x=>x.project_id===state.projectId):null;
  const name=inProject&&state.candidateId&&state.currentCandidateId===state.candidateId?state.currentCandidateName:null;
  const parts=[];
  if(inProject){
    parts.push('<button type="button" class="crumb-link" onclick="go(\'dashboard\')">工作台</button>');
    parts.push('<button type="button" class="crumb-link" onclick="closeProject()">'+esc((p&&p.title)||'项目')+'</button>');
    if(state.candidateId)parts.push('<span class="crumb-current">'+esc(name||'候选人')+'</span>');
  }
  if(host)host.innerHTML=parts.join('<span class="crumb-sep">/</span>');
  if(back)back.hidden=!inProject;
}
window.topBack=async()=>{
  if(state.page!=='projects')return window.go('dashboard');
  if(state.candidateId)return window.closeCandidateWorkspace();
  if(state.projectId)return window.closeProject();
  return window.go('dashboard');
};
async function renderPage(){syncTopbar();const t={dashboard:'今日待办',projects:'招聘项目',templates:'设置 · 岗位模板',knowledge:'设置 · 知识库',tasks:'设置 · 后台任务',settings:'设置'}[state.page]||'工作台';$('#top-title').textContent=t;if($('#side-health'))$('#side-health').textContent=state.health?'服务已就绪 · 本地数据':'服务状态待确认';const healthText=$('#service-health-text'),healthDot=$('#service-health-dot');if(healthText)healthText.textContent=state.health?'服务正常':'服务检查中';if(healthDot)healthDot.classList.toggle('good',Boolean(state.health));const fn={dashboard:dashboardPage,projects:projectsPage,templates:templatesPage,knowledge:knowledgePage,tasks:tasksPage,settings:settingsPage}[state.page];try{await fn()}catch(e){$('#content').innerHTML=`<div class="panel"><div class="panel-body empty"><strong>页面加载失败</strong>${esc(e.message)}</div></div>`}}
function head(title,desc,actions=''){return `<div class="page-head"><div><h1>${title}</h1><p>${desc}</p></div><div class="actions">${actions}</div></div>`}
async function dashboardPage(){const d=await api('/api/v1/dashboard');let providers;try{providers=await api('/api/v1/settings/providers')}catch{};const req=d.requisitions_by_status||{},st=d.candidates_by_stage||{},offers=d.offers_by_status||{};const wb=d.decision_workbench||{items:[],total:0,conflict_count:0,verify_count:0,ready_count:0};const oq=d.operational_queue||{items:[],total:0};const rq=d.review_queue||{items:[],total:0,identity_count:0,judgment_count:0,claim_count:0};$('#content').innerHTML=head('今日待办','按优先级汇总今天要处理的候选人、面试、证据核实与 Offer，点一下直达对应动作。',`<button class="btn primary" onclick="openNewProject()">＋ 新建招聘项目</button>`)+`<div class="grid kpi">${[['逾期联系',d.operational_todos?.overdue_contacts||0,'今天优先处理的联系待办'],['待提交反馈',d.operational_todos?.pending_interview_feedback||0,'已完成面试但尚未提交独立 Scorecard'],['身份复核',d.operational_todos?.pending_identity_reviews||0,'可能重复候选人等待人工判定'],['判断纠错',d.operational_todos?.open_judgment_reviews||0,'标准执行偏差与纠错队列'],['招聘中职位',req.open||0,'当前 open requisition'],['待确认事实',d.evidence_review_backlog||0,'AI / Source Claim 等待人工确认']].map(x=>`<div class="kpi-card"><div class="kpi-label">${x[0]}</div><div class="kpi-value">${fmt(x[1])}</div><div class="kpi-note">${x[2]}</div></div>`).join('')}</div><section class="panel" style="margin-bottom:16px"><div class="panel-head"><div><h2>今日业务队列</h2><span class="subtle">每位候选人只显示当前最高优先级动作，避免被低价值待办淹没。</span></div><div class="pill-row"><span class="status bad">冲突 ${fmt(wb.conflict_count||0)}</span><span class="status warn">待核实 ${fmt(wb.verify_count||0)}</span><span class="status good">可决定 ${fmt(wb.ready_count||0)}</span><span class="status info">共 ${fmt(wb.total||0)} 人</span></div></div><div class="panel-body">${wb.items.length?`<div class="quick-list">${wb.items.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.candidate_name)} · ${esc(x.project_title)}</div><div class="quick-note">${esc(workbenchActionLabel(x.action_type))}${x.criterion_name?` · ${esc(x.criterion_name)}`:''}${x.reason?` · ${esc(x.reason)}`:''}</div></div><button class="btn small primary" onclick="openWorkbenchItem('${x.project_id}','${x.candidate_id}','${x.action_type}')">处理</button></div>`).join('')}</div>`:'<div class="empty"><strong>当前没有决策待办</strong>新候选人进入评价流程后，这里会自动汇总每人的下一步。</div>'}</div></section><section class="panel" style="margin-bottom:16px"><div class="panel-head"><div><h2>运营执行队列</h2><span class="subtle">把逾期联系、今日联系和已完成面试的待反馈项直接带回业务动作。</span></div><span class="status info">${fmt(oq.total||0)} 项</span></div><div class="panel-body">${oq.items.length?`<div class="quick-list">${oq.items.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.title)} · ${esc(x.candidate_name)}</div><div class="quick-note">${esc(x.project_title)}${x.detail?` · ${esc(x.detail)}`:''}</div></div><button class="btn small primary" onclick="openOperationalItem('${x.kind}','${x.project_id}','${x.candidate_id||''}','${x.event_id||''}')">处理</button></div>`).join('')}</div>`:'<div class="empty"><strong>当前没有今日/逾期联系或待反馈面试</strong>运营待办会在这里自动出现。</div>'}</div></section><section class="panel" style="margin-bottom:16px"><div class="panel-head"><div><h2>复核中心</h2><span class="subtle">把身份、判断纠错和 AI / Source Claim 的人工复核集中到一个入口。</span></div><div class="pill-row"><span class="status warn">身份 ${fmt(rq.identity_count||0)}</span><span class="status info">纠错 ${fmt(rq.judgment_count||0)}</span><span class="status">事实 ${fmt(rq.claim_count||0)}</span><span class="status good">共 ${fmt(rq.total||0)} 项</span></div></div><div class="panel-body">${rq.items.length?`<div class="quick-list">${rq.items.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.title)}${x.candidate_name?` · ${esc(x.candidate_name)}`:''}</div><div class="quick-note">${esc(x.project_title)}${x.detail?` · ${esc(x.detail)}`:''}</div></div><button class="btn small primary" onclick="openReviewItem('${x.kind}','${x.project_id}','${x.candidate_id||''}','${x.review_id||''}','${x.claim_id||''}')">复核</button></div>`).join('')}</div>`:'<div class="empty"><strong>当前没有人工复核积压</strong>身份、判断纠错与待确认事实都会汇总到这里。</div>'}</div></section><div class="two"><section class="panel"><div class="panel-head"><h2>招聘漏斗</h2><button class="btn small" onclick="go('projects')">进入项目</button></div><div class="panel-body"><div class="funnel-grid">${['new','screening','shortlisted','phone_screen','interview','offer','hired'].map(k=>`<div class="funnel-step"><strong>${fmt(st[k]||0)}</strong><span>${stageLabel(k)}</span></div>`).join('')}</div><div class="divider"></div><div class="pill-row"><span class="status info">人才池 ${fmt(st.talent_pool||0)}</span><span class="status bad">拒绝 ${fmt(st.rejected||0)}</span><span class="status">退出 ${fmt(st.withdrawn||0)}</span></div></div></section><section class="panel"><div class="panel-head"><h2>Offer 管理</h2></div><div class="panel-body"><div class="quick-list">${['draft','approved','sent','accepted','declined','withdrawn'].map(k=>`<div class="quick-item"><span>${offerLabels[k]}</span><strong>${fmt(offers[k]||0)}</strong></div>`).join('')}</div></div></section></div><div class="split"><section class="panel"><div class="panel-head"><h2>近期活动</h2><button class="btn small" onclick="renderPage()">刷新</button></div><div class="panel-body">${(d.recent_activity||d.recent||[]).length?`<div class="timeline">${(d.recent_activity||d.recent).map(x=>`<div class="timeline-item"><strong>${esc(x.event_type)}</strong><small>${esc(x.actor||x.entity_type)} · ${new Date(x.created_at).toLocaleString()}</small></div>`).join('')}</div>`:'<div class="empty"><strong>暂无活动</strong>创建项目后，这里会显示关键操作时间线。</div>'}</div></section><section class="panel"><div class="panel-head"><h2>Provider / 任务</h2></div><div class="panel-body"><div class="quick-list">${providers?Object.values(providers.profiles).map(p=>`<div class="quick-item"><div><div class="quick-title">${p.name==='text_ai'?'文本 AI':p.name.toUpperCase()}</div><div class="quick-note">${esc(p.model)}</div></div><span class="status ${p.api_key_configured?'good':'warn'}">${p.api_key_configured?'已配置':'待配置'}</span></div>`).join(''):''}<div class="quick-item"><div><div class="quick-title">开放后台任务</div><div class="quick-note">等待 Provider、失败与运行中</div></div><strong>${fmt(d.metrics?.open_tasks||0)}</strong></div></div></div></section></div>`;const dashboardKpis=$('#content > .grid.kpi');const dashboardQueuePanels=[...document.querySelectorAll('#content > section.panel')];if(dashboardKpis&&dashboardQueuePanels.length===3){dashboardQueuePanels.forEach(panel=>$('#content').insertBefore(panel,dashboardKpis));const resumeHost=document.createElement('div');resumeHost.id='dashboard-project-resume';$('#content').insertBefore(resumeHost,dashboardKpis);void mountProjectResume(resumeHost,()=>api('/api/v1/projects'),pid=>window.openProject(pid),()=>state.page==='dashboard'&&resumeHost.isConnected,e=>toast(e?.message||'项目暂时无法打开',true));}}
window.openNewProject=()=>modal('新建招聘项目',`<div class="form-grid"><div class="field"><label>项目名称</label><input id="np-title" class="input" placeholder="例如：2026 产品经理招聘"></div><div class="field"><label>岗位名称</label><input id="np-role" class="input" placeholder="产品经理"></div><div class="field full"><label>岗位摘要</label><textarea id="np-summary" class="textarea" placeholder="业务目标、团队背景、关键职责"></textarea></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="createProject()">创建并进入项目</button>`);
window.createProject=async()=>{try{const r=await api('/api/v1/projects',{method:'POST',body:JSON.stringify({title:$('#np-title').value,role_title:$('#np-role').value,brief_summary:$('#np-summary').value})});closeModal();state.projectId=r.project_id;state.page='projects';state.projectTab='criteria';toast('项目已创建');await go('projects')}catch(e){toast(e.message,true)}};
async function projectsPage(){syncTopbar();const d=await api('/api/v1/projects');if(state.page!=='projects')return;state.projects=d.projects||[];syncTopbar();if(state.projectId){return projectWorkspace()}$('#content').innerHTML=head('招聘项目','把每个招聘项目作为一条职位生命周期管理：草案 → 招聘中 → 暂停 / 招满 / 关闭。',`<button class="btn" onclick="c08OpenProjectImport()">导入完整项目包</button><button class="btn primary" onclick="openNewProject()">＋ 新建项目</button>`)+`<section class="panel"><div class="panel-head"><h2>职位生命周期</h2><span class="subtle">${state.projects.length} 个项目</span></div><div class="table-wrap"><table class="table"><thead><tr><th>项目 / 职位</th><th>招聘状态</th><th>标准</th><th>候选人</th><th>待办</th><th></th></tr></thead><tbody>${state.projects.length?state.projects.map(p=>`<tr><td><strong>${esc(p.title)}</strong><div class="subtle">${esc(p.protocol_title||'—')}</div></td><td><span class="status ${statusClass(p.status)}">${esc(projectStatusLabels[p.status]||p.status)}</span></td><td><span class="status ${statusClass(p.protocol_state)}">${esc(p.protocol_state)}</span></td><td>${p.candidate_count}</td><td>${p.open_work_count}</td><td class="right"><button class="btn small primary" onclick="openProject('${p.project_id}')">进入工作区</button></td></tr>`).join(''):`<tr><td colspan="6"><div class="empty"><strong>还没有招聘项目</strong>先新建职位，再发布招聘标准。</div></td></tr>`}</tbody></table></div></section>`}
// #235: only a server-scoped, still-scheduled interview can be opened here.
window.openScheduledInterview=async(pid,cid,eid,openIndependentScorecard=false)=>{
  // A delayed Core pipeline response must not select an older candidate after
  // the operator switches tabs, opens another form or clicks a newer event.
  const requestedTab=state.projectTab,requestedCandidateId=state.candidateId;
  const requestedModalGeneration=state.modalGeneration||0;
  const seq=(state.scheduledInterviewOpenSeq||0)+1;
  state.scheduledInterviewOpenSeq=seq;
  const stillOnSource=()=>state.page==='projects'&&state.projectId===pid
    &&state.projectTab===requestedTab&&state.candidateId===requestedCandidateId
    &&(state.modalGeneration||0)===requestedModalGeneration
    &&state.scheduledInterviewOpenSeq===seq;
  if(!stillOnSource()||!cid||!eid){toast('请先进入对应招聘项目。',true);return}
  try{
    const scoped=await api(`/api/v1/projects/${encodeURIComponent(pid)}/pipeline`);
    if(!stillOnSource())return;
    const scheduledEvent=(scoped.scheduled_events||[]).find(x=>x.candidate_id===cid&&x.event_id===eid);
    if(!scheduledEvent){
      toast('面试已变化或不属于当前项目，请刷新后重新选择。',true);return;
    }
    if(openIndependentScorecard&&scheduledEvent.event_type!=='interview'){
      toast('电话筛选不适用独立面评，请查看筛选记录。',true);return;
    }
    state.candidateReturnTab='overview';
    state.candidateId=cid;
    state.candidateSection='process';
    await candidateDrawer(cid);
    if(state.page!=='projects'||state.projectId!==pid||state.candidateId!==cid
       ||state.scheduledInterviewOpenSeq!==seq
       ||(state.modalGeneration||0)!==requestedModalGeneration)return;
    const target=[...document.querySelectorAll('.timeline-item[data-event-id]')].find(x=>x.dataset.eventId===eid);
    if(!target){toast('面试记录已变化，请重新选择。',true);await window.closeCandidateWorkspace();return}
    target.classList.add('review-item-focused');
    target.scrollIntoView({block:'center',behavior:'auto'});
    target.querySelector('button')?.focus({preventScroll:true});
    // Open only after Core revalidates this project/candidate/event tuple.
    // The scoped Scorecard reader independently checks ownership and revision.
    if(openIndependentScorecard)await window.openScorecards(cid,eid);
  }catch(e){toast(e.message,true)}
};
window.openProject=async id=>{const fromOtherPage=state.page!=='projects';state.page='projects';state.projectId=id;state.projectTab='overview';state.overviewSection=null;state.candidateView='all';state.candidateId=null;state.candidateSection='evidence';if(fromOtherPage){document.body.innerHTML=shell()+`<div id="modal-root"></div><div id="toast-root"></div>`;await renderPage()}else await projectsPage()};window.closeProject=async()=>{state.page='projects';state.projectId=null;state.candidateId=null;state.currentCandidateId=null;state.currentCandidateName=null;state.flowCandidateId=null;state.candidateSection='evidence';await projectsPage()};window.setProjectTab=async t=>{state.projectTab=t;state.overviewSection=null;state.candidateView='all';state.flowCandidateId=null;state.candidateId=null;state.candidateSection='evidence';await projectWorkspace()};
const CANDIDATE_VIEWS=[['all','全部'],['flow','面试'],['ops','待办'],['quality','数据质量']];
window.setCandidateView=v=>{state.candidateView=v;state.candidateId=null;state.overviewSection=null;projectWorkspace()};
async function candidatesHubTab(el,p){
  const v=state.candidateView||'all';
  el.innerHTML=`<div class="pill-row" style="margin-bottom:12px">${CANDIDATE_VIEWS.map(([k,l])=>`<button class="btn small ${v===k?'primary':''}" onclick="setCandidateView('${k}')">${l}</button>`).join('')}<span class="subtle" style="margin-left:6px">面试 / 待办 / 数据质量 已并入候选人，不再各占一个页签</span></div><div id="cand-view-body"><div class="empty">加载中…</div></div>`;
  const fn={all:candidatesTab,flow:flowTab,ops:(e,pp)=>window.operationsLearningTab(e,pp),quality:qualityTab}[v]||candidatesTab;
  const host=el.querySelector('#cand-view-body');
  await fn(host,p);
}
async function overviewTab(el,p){
  await projectOverview(el,p);
  el.insertAdjacentHTML('beforeend',`<section class="panel" id="ov-cockpit"><div class="panel-head"><div><h2>决策漏斗与候选池</h2><span class="subtle">原「筛选与决策」页，已并入概览</span></div></div><div class="panel-body" id="ov-cockpit-body"><div class="empty">加载中…</div></div></section><section class="panel" id="ov-audit"><div class="panel-head"><div><h2>版本与审计</h2><span class="subtle">原「版本与审计」页，协议版本与最近审计事件</span></div></div><div class="panel-body" id="ov-audit-body"><div class="empty">加载中…</div></div></section>`);
  const cockpitHost=el.querySelector('#ov-cockpit-body'),auditHost=el.querySelector('#ov-audit-body');
  if(cockpitHost){try{await cockpitTab(cockpitHost,p)}catch(e){cockpitHost.innerHTML=`<div class="empty">决策漏斗加载失败：${esc(e.message)}</div>`}}
  if(auditHost){try{await auditTab(auditHost,p)}catch(e){auditHost.innerHTML=`<div class="empty">审计加载失败：${esc(e.message)}</div>`}}
  if(state.overviewSection){const t=document.getElementById('ov-'+state.overviewSection);if(t)t.scrollIntoView({block:'start'})}
}
function settingsNavHtml(){return `<section class="panel"><div class="panel-head"><div><h2>工作台设置</h2><span class="subtle">岗位模板、知识库、后台任务与诊断从这里进入（原侧栏 6 项已收拢为 3 项）</span></div></div><div class="panel-body"><div class="four">${[['templates','岗位模板','沉淀可复用的岗位标准'],['knowledge','知识库','检索并应用到当前项目'],['tasks','后台任务','查看提取/复评等异步任务']].map(([k,t,d])=>`<div class="provider-card"><div class="provider-title"><h3>${t}</h3></div><div class="provider-sub">${d}</div><div class="actions" style="margin-top:10px"><button class="btn small primary" onclick="go('${k}')">进入${t}</button></div></div>`).join('')}<div class="provider-card"><div class="provider-title"><h3>运行诊断</h3></div><div class="provider-sub">数据库、对象存储与版本自检</div><div class="actions" style="margin-top:10px"><button class="btn small" onclick="showDiagnostics()">打开诊断</button></div></div></div></div></section>`}
function projectTabs(){return [['overview','概览'],['criteria','岗位与标准'],['candidates','候选人']].map(([k,l])=>`<button class="tab ${state.projectTab===k?'active':''}" onclick="setProjectTab('${k}')">${l}</button>`).join('')}
async function projectWorkspace(){syncTopbar();const LEGACY={cockpit:['overview','cockpit'],audit:['overview','audit'],flow:['candidates','flow'],ops:['candidates','ops'],quality:['candidates','quality']};if(LEGACY[state.projectTab]){const m=LEGACY[state.projectTab];state.projectTab=m[0];if(m[0]==='overview'){state.overviewSection=m[1]}else{state.candidateView=m[1]}}const p=state.projects.find(x=>x.project_id===state.projectId)||{};if(state.candidateId){await candidateDrawer(state.candidateId,p);return}$('#content').innerHTML=`<div class="project-banner"><div><h2>${esc(p.title||'项目工作区')}</h2><div class="project-meta"><span class="badge">岗位：${esc(p.protocol_title||'—')}</span><span class="badge">状态：${esc(projectStatusLabels[p.status]||p.status||'—')}</span><span class="badge">协议：${esc(p.protocol_state||'—')}</span><span class="badge">候选人：${p.candidate_count||0}</span></div></div><div class="actions"><button class="btn" onclick="openProjectStatus('${p.status||'draft'}')">职位生命周期</button><button class="btn" onclick="archiveProject('${state.projectId}')">归档项目</button></div></div><div class="panel"><div class="tabs">${projectTabs()}</div><div class="panel-body" id="project-tab-body"><div class="empty">加载中…</div></div></div>`;const fn={overview:overviewTab,criteria:criteriaTab,candidates:candidatesHubTab}[state.projectTab]||projectOverview;try{await fn($('#project-tab-body'),p)}catch(e){$('#project-tab-body').innerHTML=`<div class="empty"><strong>加载失败</strong>${esc(e.message)}</div>`}}
window.openProjectStatus=current=>modal('职位生命周期',`<div class="field"><label>职位状态</label><select id="project-status" class="select">${[['draft','草案'],['open','招聘中'],['paused','暂停招聘'],['filled','已招满'],['closed','关闭职位']].map(([v,l])=>`<option value="${v}" ${v===current?'selected':''}>${l}</option>`).join('')}</select></div><div class="field" style="margin-top:10px"><label>变更理由</label><textarea id="project-status-reason" class="textarea" placeholder="例如：HC 已批准 / 暂停招聘 / 已完成录用"></textarea></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveProjectStatus()">确认变更</button>`);window.saveProjectStatus=async()=>{try{await api(`/api/v1/projects/${state.projectId}/status`,{method:'POST',body:JSON.stringify({status:$('#project-status').value,reason:$('#project-status-reason').value||'人工更新职位状态',actor:'human'})});closeModal();toast('职位状态已更新');await refreshProjects();await projectWorkspace()}catch(e){toast(e.message,true)}};
window.archiveProject=async id=>{if(!confirm('归档该项目？数据不会删除。'))return;try{await api(`/api/v1/projects/${id}/archive`,{method:'POST'});state.projectId=null;toast('项目已归档');await projectsPage()}catch(e){toast(e.message,true)}};
async function projectOverview(el,p){const [pipe,proto]=await Promise.all([api(`/api/v1/projects/${state.projectId}/pipeline`),api(`/api/v1/projects/${state.projectId}/protocol-workspace`).catch(()=>null)]);const s=pipe.stages||{},o=pipe.offers_by_status||{};const w=pipe.workflow_summary||{next_action:{tab:'candidates',label:'继续推进候选人',reason:''}};if(state.page!=='projects'||state.projectId!==p.project_id)return;const next=w.next_action||{},nextTarget=next.target||{};const exactTarget=Boolean(nextTarget.candidate_id)&&(['complete_materials','review_evidence'].includes(next.key)||(['submit_feedback','advance_interviews'].includes(next.key)&&Boolean(nextTarget.event_id)));const nextDisabled=Boolean(next.disabled)||pipe.project_status==='archived';const nextButtonLabel=exactTarget?({complete_materials:'补齐材料',review_evidence:'核实证据',submit_feedback:'填写面评',advance_interviews:nextTarget.event_type==='phone_screen'?'查看电话筛选':'查看面试'}[next.key]+' · '+esc(nextTarget.candidate_name||'候选人')):esc(next.label||'查看相关列表');el.innerHTML=`<section class="next-action-card"><div class="nac-main"><div class="nac-kicker">下一项待办</div><div class="nac-title">${esc(w.next_action?.label||'继续推进候选人')}</div><div class="nac-reason">${esc(w.next_action?.reason||'')}</div><div class="nac-meta"><span class="nac-meta-label">项目推进</span><span>决策待办 ${fmt(w.decision_work_candidates||0)} · 待确认事实 ${fmt(w.unreviewed_claims||0)} · 待反馈面试 ${fmt(w.pending_interview_feedback||0)} · Offer 跟进 ${fmt(w.offer_followups||0)}</span></div></div><button class="btn primary" id="project-next-action" ${nextDisabled?'disabled aria-disabled="true"':''}>${nextButtonLabel}</button></section><div class="actions tool-row" style="margin-bottom:12px"><button class="btn primary" onclick="openContactWorkbench()">联系工作台</button><button class="btn" onclick="openRankedShortlist('${state.projectId}')">证据短名单</button><button class="btn" onclick="openProjectAiRuns('${state.projectId}')">AI 运行账本</button><button class="btn" onclick="openHandoff()">项目交接摘要</button><button class="btn" onclick="c08ExportProjectPackage('${state.projectId}')">完整项目包</button><a class="btn" href="/api/v1/projects/${state.projectId}/contact-list.csv">电话联系清单</a></div><div class="grid kpi">${[['候选人',pipe.total_candidates,'当前项目全部在库候选人'],['短名单',s.shortlisted||0,'待电话筛选 / 面试'],['近期排期',pipe.upcoming_interviews||0,'电话筛选与面试的未来安排'],['Offer',Object.values(o).reduce((a,b)=>a+Number(b||0),0),'草案到接受的完整状态']].map(x=>`<div class="kpi-card"><div class="kpi-label">${x[0]}</div><div class="kpi-value">${x[1]}</div><div class="kpi-note">${x[2]}</div></div>`).join('')}</div><section class="panel"><div class="panel-head"><h3>招聘漏斗</h3><span class="status ${statusClass(pipe.project_status)}">${esc(projectStatusLabels[pipe.project_status]||pipe.project_status)}</span></div><div class="panel-body"><div class="funnel-grid">${['new','screening','shortlisted','phone_screen','interview','offer','hired'].map(k=>`<button class="funnel-step clickable" onclick="state.candidateStage='${k}';setProjectTab('candidates')"><strong>${s[k]||0}</strong><span>${stageLabel(k)}</span></button>`).join('')}</div><div class="pill-row" style="margin-top:12px"><span class="status info">人才池 ${s.talent_pool||0}</span><span class="status bad">拒绝 ${s.rejected||0}</span><span class="status">退出 ${s.withdrawn||0}</span></div></div></section><div class="two"><section class="panel"><div class="panel-head"><h3>近期排期</h3><button class="btn small" onclick="setProjectTab('flow')">招聘流程</button></div><div class="panel-body">${pipe.scheduled_events?.length?`<div class="quick-list">${pipe.scheduled_events.slice(0,6).map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.candidate_name)} · ${esc(x.title||x.event_type)}</div><div class="quick-note">${new Date(x.scheduled_at).toLocaleString()} · ${esc(x.interviewer||'待指定面试官')} · ${esc(x.location||'待指定地点')}</div></div><span class="status warn">已排期</span>${x.candidate_id&&x.event_id?`<button type="button" class="btn small" data-scheduled-candidate="${esc(x.candidate_id)}" data-scheduled-event="${esc(x.event_id)}">${x.event_type==='phone_screen'?'查看电话筛选':'查看该面试'}</button>${x.event_type==='interview'?'<button type="button" class="btn small primary" data-scorecard-candidate="'+esc(x.candidate_id)+'" data-scorecard-event="'+esc(x.event_id)+'">独立面评</button>':''}`:''} </div>`).join('')}</div>`:'<div class="empty">近期没有已排期面试</div>'}</div></section></div>`;
  el.querySelector("#project-next-action")?.addEventListener("click",async()=>{
    if(nextDisabled)return;
    const pid=state.projectId,cid=nextTarget.candidate_id||'',eid=nextTarget.event_id||'';
    // The Core recheck is asynchronous. An older CTA must not select A after
    // HR has moved to B, switched tabs, or opened a newer unsaved dialog.
    const requestedTab=state.projectTab,requestedCandidateId=state.candidateId;
    const requestedModalGeneration=state.modalGeneration||0;
    const seq=(state.projectNextActionSeq||0)+1;
    state.projectNextActionSeq=seq;
    const stillOnSource=()=>state.page==='projects'&&state.projectId===pid
      &&state.projectTab===requestedTab&&state.candidateId===requestedCandidateId
      &&(state.modalGeneration||0)===requestedModalGeneration
      &&state.projectNextActionSeq===seq;
    const stillOnTarget=()=>state.page==='projects'&&state.projectId===pid
      &&state.candidateId===cid
      &&(state.modalGeneration||0)===requestedModalGeneration
      &&state.projectNextActionSeq===seq;
    if(!stillOnSource())return;
    try{
      // Recheck *all* cards, including generic list links, before navigation.
      // An archived project must not retain an actionable stale primary CTA.
      const fresh=await api(`/api/v1/projects/${encodeURIComponent(pid)}/pipeline`);
      if(!stillOnSource())return;
      const current=fresh.workflow_summary?.next_action||{},target=current.target||{};
      if(current.disabled||fresh.project_status==='archived'||current.key!==next.key||(exactTarget&&(target.candidate_id!==cid||(target.event_id||'')!==eid))){
        toast('项目待办已变化，请重新查看最新任务。',true);
        await projectWorkspace();return;
      }
      if(!exactTarget){await setProjectTab(current.tab||'candidates');return}
      const owner=await api(`/api/v1/candidates/${encodeURIComponent(cid)}/summary`);
      if(!stillOnSource())return;
      if(owner?.project_id!==pid){toast('候选人不属于当前项目，已阻止跳转。',true);return}
      if(next.key==='advance_interviews'){
        await window.openScheduledInterview(pid,cid,eid);return;
      }
      state.candidateReturnTab='overview';
      state.candidateId=cid;
      state.candidateSection=next.key==='submit_feedback'?'process':'evidence';
      await candidateDrawer(cid);
      if(!stillOnTarget())return;
      if(next.key==='submit_feedback'){
        const row=[...document.querySelectorAll('.timeline-item[data-event-id]')].find(x=>x.dataset.eventId===eid);
        if(!row){toast('面试记录已变化，请刷新后重新选择。',true);await window.closeCandidateWorkspace();return}
        await window.openScorecards(cid,eid);
      }
    }catch(e){if(stillOnSource()||stillOnTarget())toast(e.message||'无法打开当前待办',true)}
  });
  el.querySelectorAll("[data-scheduled-event]").forEach(button=>button.addEventListener("click",()=>window.openScheduledInterview(state.projectId,button.dataset.scheduledCandidate,button.dataset.scheduledEvent)));
  el.querySelectorAll("[data-scorecard-event]").forEach(button=>button.addEventListener("click",()=>window.openScheduledInterview(state.projectId,button.dataset.scorecardCandidate,button.dataset.scorecardEvent,true)));
}
const defaultAssessmentStages=[
  {stage_key:'resume',name:'简历筛选',criteria:[]},
  {stage_key:'phone_screen',name:'电话筛选',criteria:[]},
  {stage_key:'interview',name:'面试',criteria:[]}
];













function collectAssessmentStages(criteria){
  const valid=new Set(criteria.map(x=>x.criterion_key));
  const defs=(state.criteriaStageDefs?.length?state.criteriaStageDefs:defaultAssessmentStages).map(s=>({...s,criteria:[]}));
  const byKey=new Map(defs.map(s=>[s.stage_key,s]));
  for(const row of document.querySelectorAll('.criterion-row')){
    const key=ensureCriterionKey(row);
    if(!valid.has(key))continue;
    for(const input of row.querySelectorAll('.c-stage:checked')){
      const stage=byKey.get(input.value);
      if(stage&&!stage.criteria.includes(key))stage.criteria.push(key)
    }
  }
  return defs
}




window.forkDraft=async()=>{try{await api(`/api/v1/projects/${state.projectId}/protocol-drafts`,{method:'POST'});toast('已创建新草案');await projectWorkspace()}catch(e){toast(e.message,true)}};

async function cockpitTab(el,p){const d=await api(`/api/v1/projects/${state.projectId}/cockpit?limit=${state.cockpitLimit}&offset=${state.cockpitPage*state.cockpitLimit}`);const pages=Math.max(1,Math.ceil(d.total/state.cockpitLimit));el.innerHTML=`<div class="panel-head" style="padding:0 0 12px;border:0"><div><h3>决策驾驶舱 <span class="subtle">${d.total} 人</span></h3><span class="subtle">服务端分页聚合；流程阶段与证据记录分开呈现。</span></div><button class="btn primary" onclick="openRankedShortlist('${state.projectId}')">生成证据短名单</button></div><div class="table-wrap"><table class="table"><thead><tr><th>候选人</th><th>阶段</th><th>岗位匹配</th><th>证据覆盖</th><th>材料</th><th>已确认事实</th><th>待确认</th><th>当前判断项</th><th></th></tr></thead><tbody>${d.candidates.map(c=>`<tr><td><strong>${esc(c.display_name)}</strong></td><td><span class="status ${statusClass(c.pipeline_stage)}">${stageLabel(c.pipeline_stage)}</span></td><td>${c.assessment?.fit_score==null?'<span class="subtle">待证据闭合</span>':`<strong>${c.assessment.fit_score}%</strong>`}</td><td>${c.assessment?`${Math.round(Number(c.assessment.evidence_coverage||0)*100)}%`:'—'}</td><td>${c.has_material?'已导入':'待上传'}</td><td>${c.confirmed_claims}</td><td>${c.unreviewed_claims}</td><td>${c.judgments}</td><td><button class="btn small primary" onclick="openCandidate('${c.candidate_id}')">查看工作区</button></td></tr>`).join('')}</tbody></table></div><div class="actions" style="justify-content:flex-end;margin-top:12px"><button class="btn small" ${state.cockpitPage<=0?'disabled':''} onclick="cockpitPage(-1)">上一页</button><span class="subtle">第 ${state.cockpitPage+1} / ${pages} 页</span><button class="btn small" ${(state.cockpitPage+1)>=pages?'disabled':''} onclick="cockpitPage(1)">下一页</button></div>`}
window.cockpitPage=d=>{state.cockpitPage=Math.max(0,state.cockpitPage+d);projectWorkspace()};
async function candidatesTab(el,p){const qs=new URLSearchParams({archived:state.candidateArchive,material:state.candidateMaterial,stage:state.candidateStage,limit:String(state.candidateLimit),offset:String(state.candidatePage*state.candidateLimit)});if(state.candidateQuery.trim())qs.set('q',state.candidateQuery.trim());const d=await api(`/api/v1/projects/${state.projectId}/candidates?${qs.toString()}`);state.candidateRows=d.candidates;const pages=Math.max(1,Math.ceil(d.total/state.candidateLimit));el.innerHTML=`<div class="panel-head" style="padding:0 0 12px;border:0"><h3>候选人 Pipeline <span class="subtle">${d.total} 人</span></h3><div class="actions"><button class="btn" onclick="bulkImport()">批量导入简历</button><a class="btn" href="/api/v1/projects/${state.projectId}/candidates.csv" download>导出 CSV</a><button class="btn" onclick="compareSelected()">对比 2–5 人</button><button class="btn primary" onclick="openAddCandidate()">＋ 新增候选人</button></div></div><div class="searchbar"><div class="field"><label>搜索候选人</label><input id="cand-q" class="input" value="${esc(state.candidateQuery)}" placeholder="姓名 / 显示名称"></div><div class="field"><label>候选人阶段</label><select id="cand-stage" class="select"><option value="all">全部阶段</option>${Object.entries(stageLabels).map(([v,l])=>`<option value="${v}" ${state.candidateStage===v?'selected':''}>${l}</option>`).join('')}</select></div><div class="field"><label>归档筛选</label><select id="cand-archive" class="select"><option value="active" ${state.candidateArchive==='active'?'selected':''}>在库</option><option value="archived" ${state.candidateArchive==='archived'?'selected':''}>已归档</option><option value="all" ${state.candidateArchive==='all'?'selected':''}>全部</option></select></div><div class="field"><label>材料筛选</label><select id="cand-material" class="select"><option value="all" ${state.candidateMaterial==='all'?'selected':''}>全部</option><option value="with" ${state.candidateMaterial==='with'?'selected':''}>已有材料</option><option value="without" ${state.candidateMaterial==='without'?'selected':''}>待导入材料</option></select></div><div class="actions" style="align-self:end"><button class="btn primary" onclick="applyCandidateFilters()">应用筛选</button></div></div><div class="pipeline-toolbar"><span>批量推进：</span>${[['shortlisted','短名单'],['phone_screen','电话筛选'],['interview','面试'],['rejected','拒绝'],['talent_pool','人才池']].map(([v,l])=>`<button class="btn small" onclick="bulkStage('${v}')">${l}</button>`).join('')}</div><div class="table-wrap"><table class="table"><thead><tr><th></th><th>候选人</th><th>阶段</th><th>材料</th><th>创建时间</th><th></th></tr></thead><tbody>${d.candidates.length?d.candidates.map(c=>`<tr data-candidate-id="${c.candidate_id}"><td><input type="checkbox" class="cand-check" value="${c.candidate_id}" ${c.archived?'disabled':''}></td><td><strong>${esc(c.display_name)}</strong><div class="subtle">${esc(stageLabel(c.pipeline_stage))}${c.has_material?'':' · 待导入材料'}</div></td><td><span class="status ${statusClass(c.pipeline_stage)}">${stageLabel(c.pipeline_stage)}</span></td><td><span class="status ${c.has_material?'good':'warn'}">${c.has_material?'当前材料已发布':'待导入'}</span></td><td>${new Date(c.created_at).toLocaleString()}</td><td class="right"><button class="btn small primary" onclick="openCandidateNext('${c.candidate_id}')">打开工作台</button> ${c.archived?'':`<button class="btn small" data-quick-action="verify" onclick="openCandidateQuickAction('${c.candidate_id}','verify')">核实材料</button> <button class="btn small" data-quick-action="schedule" onclick="openCandidateQuickAction('${c.candidate_id}','schedule')">安排面试</button> <button class="btn small" data-quick-action="scorecard" onclick="openCandidateQuickAction('${c.candidate_id}','scorecard')">填写面评</button>`} ${c.archived?(c.merged_into_candidate_id?`<span class="status info">已并入 canonical identity</span>`:`<button class="btn small" onclick="restoreCandidate('${c.candidate_id}')">恢复</button>`):`<button class="btn small" onclick="archiveCandidate('${c.candidate_id}')">归档</button>`}</td></tr>`).join(''):`<tr><td colspan="6"><div class="empty"><strong>没有符合条件的候选人</strong>调整筛选条件，或批量导入新的简历材料。</div></td></tr>`}</tbody></table></div><div class="actions" style="justify-content:flex-end;margin-top:12px"><button class="btn small" ${state.candidatePage<=0?'disabled':''} onclick="candidatePage(-1)">上一页</button><span class="subtle">第 ${state.candidatePage+1} / ${pages} 页</span><button class="btn small" ${(state.candidatePage+1)>=pages?'disabled':''} onclick="candidatePage(1)">下一页</button></div><input id="bulk-files" type="file" multiple hidden accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.png,.jpg,.jpeg,.mp3,.wav,.m4a,.mp4,.webm">`}
window.applyCandidateFilters=()=>{state.candidateQuery=$('#cand-q')?.value||'';state.candidateArchive=$('#cand-archive')?.value||'active';state.candidateMaterial=$('#cand-material')?.value||'all';state.candidateStage=$('#cand-stage')?.value||'all';state.candidatePage=0;projectWorkspace()};window.candidatePage=delta=>{state.candidatePage=Math.max(0,state.candidatePage+delta);projectWorkspace()};window.openAddCandidate=()=>modal('新增候选人',`<div class="field"><label>候选人姓名 / 显示名称</label><input id="cand-name" class="input" placeholder="例如：张三"></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="createCandidate()">创建</button>`);
window.bulkStage=async stage=>{const ids=[...document.querySelectorAll('.cand-check:checked')].map(x=>x.value);if(!ids.length){toast('请先选择候选人',true);return}const reason=prompt(`批量推进到“${stageLabel(stage)}”的理由：`,'人工批量推进');if(reason===null)return;try{const r=await api(`/api/v1/projects/${state.projectId}/candidates/stage`,{method:'POST',body:JSON.stringify({candidate_ids:ids,stage,reason,actor:'human'})});toast(`批量推进：成功 ${r.updated}，失败 ${r.failed}`,r.failed>0);await projectWorkspace()}catch(e){toast(e.message,true)}};
window.createCandidate=async()=>{try{const r=await api(`/api/v1/projects/${state.projectId}/candidates`,{method:'POST',body:JSON.stringify({display_name:$('#cand-name').value})});closeModal();toast('候选人已创建');await openCandidate(r.candidate_id)}catch(e){toast(e.message,true)}};
window.archiveCandidate=async id=>{await api(`/api/v1/candidates/${id}/archive`,{method:'POST'});toast('候选人已归档');await projectWorkspace()};window.restoreCandidate=async id=>{await api(`/api/v1/candidates/${id}/restore`,{method:'POST'});toast('候选人已恢复');await projectWorkspace()};
window.bulkImport=()=>{const i=$('#bulk-files');i.onchange=async()=>{const files=[...i.files];if(!files.length)return;if(files.length>50){toast(`一次最多提交 50 份材料；当前选择 ${files.length} 份，请分批提交。`,true);i.value='';return}try{toast(`正在收件并创建后台任务：${files.length} 份材料…`);const items=[];for(const f of files){items.push({display_name:f.name.replace(/\.[^.]+$/,''),filename:f.name,media_type:f.type||'application/octet-stream',base64:await fileToBase64(f)})}const r=await api(`/api/v1/projects/${state.projectId}/candidates/batch-intake`,{method:'POST',body:JSON.stringify({items})});toast(`后台任务已提交：${r.item_count} 份材料 · Task ${String(r.task_id).slice(0,8)}…`);state.candidatePage=0;await projectWorkspace()}catch(e){toast(e.message,true)}finally{i.value=''}};i.click()};
window.compareSelected=async()=>{const ids=[...document.querySelectorAll('.cand-check:checked')].map(x=>x.value);if(ids.length<2||ids.length>5){toast('请选择 2–5 位候选人',true);return}try{const d=await api(`/api/v1/candidates/compare?ids=${encodeURIComponent(ids.join(','))}`);const heads=d.candidates.map(x=>`<th>${esc(x.display_name)}<small>${stageLabel(x.pipeline_stage)} · ${esc(offerLabels[x.offer_status]||x.offer_status||'无 Offer')} · Fit ${x.assessment?.fit_score==null?'待证据闭合':x.assessment.fit_score+'%'} · Evidence ${Math.round(Number(x.assessment?.evidence_coverage||0)*100)}%</small></th>`).join('');const body=d.criteria.map(cr=>`<tr><td><strong>${esc(cr.name)}</strong>${cr.decision_critical?'<div class="subtle">硬条件/关键项</div>':''}</td>${d.candidates.map(x=>{const j=x.criteria.find(v=>v.criterion_key===cr.criterion_key)||{};return `<td><span class="status ${statusClass(j.status)}">${esc(j.status||'missing')}</span><div>${esc(j.evidence_level||'none')}</div><div class="subtle">${esc(j.gap||j.reason||'—')}</div></td>`}).join('')}</tr>`).join('');modal('同岗位 · 当前标准版本候选人对比',`<p class="subtle">Protocol ${esc(d.protocol_revision_id)}。仅比较当前评价上下文，不按历史记录数量排名。</p><table class="table"><thead><tr><th>评价标准</th>${heads}</tr></thead><tbody>${body}</tbody></table><div class="divider"></div><div class="grid">${d.candidates.map(x=>`<div class="quick-item"><div><strong>${esc(x.display_name)}</strong><div class="quick-note">${esc(x.contact.email||'未录邮箱')} · ${esc(x.contact.phone||'未录电话')}</div></div></div>`).join('')}</div>`)}catch(e){toast(e.message,true)}};
window.openCandidate=async id=>{state.candidateReturnTab=state.projectTab||'candidates';state.candidateId=id;state.candidateSection='evidence';await candidateDrawer(id)};window.closeCandidateWorkspace=async()=>{state.candidateId=null;state.candidateSection='evidence';state.projectTab=state.candidateReturnTab||'candidates';await projectWorkspace()};window.setCandidateSection=async section=>{state.candidateSection=section;await candidateDrawer(state.candidateId)};window.setFlowCandidate=v=>{state.flowCandidateId=v||null;projectWorkspace()};window.openCandidateProjectFlow=async()=>{const cid=state.candidateId;state.candidateId=null;state.flowCandidateId=cid||state.flowCandidateId;state.projectTab='flow';await projectWorkspace()};
async function fileToBase64(file){return await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(file)})}
async function uploadFile(cid,file){const b64=await fileToBase64(file);return api(`/api/v1/candidates/${cid}/files`,{method:'POST',body:JSON.stringify({filename:file.name,media_type:file.type||'application/octet-stream',base64:b64,source_kind:'resume'})})}
function candidateEventsHtml(cid,ev){const rows=ev?.events||[];return `<section class="panel"><div class="panel-head"><div><h3>电话筛选与面试</h3><span class="subtle">排期、完成记录和独立 Scorecard 都保留在候选人上下文中。</span></div><div class="actions"><button class="btn small" onclick="openEvent('${cid}','phone_screen')">＋ 电话筛选</button><button class="btn small primary" onclick="openEvent('${cid}','interview')">＋ 面试排期</button></div></div><div class="panel-body">${rows.length?`<div class="timeline">${rows.map(x=>`<div class="timeline-item" data-event-id="${esc(x.event_id)}"><strong>${esc(x.title||x.event_type)} <span class="status ${statusClass(x.event_state)}">${esc(x.event_state)}</span></strong><small>${x.scheduled_at?new Date(x.scheduled_at).toLocaleString():new Date(x.created_at).toLocaleString()} · ${x.duration_minutes||0} 分钟 · ${esc(x.interviewer||'未指定')}</small><div>${esc(x.notes||'')}</div><div class="subtle">地点：${esc(x.location||'—')} · outcome：${esc(x.outcome||'—')}</div><div class="actions" style="margin-top:6px">${x.event_type==='interview'?`<button class="btn small" onclick="openScorecards('${cid}','${x.event_id}')">独立 Scorecard</button>`:''}${x.editable_evidence_source?`<button class="btn small" onclick="correctEvent('${cid}','${x.event_id}')">更正证据记录</button>`:''}${x.event_state==='scheduled'?`<button class="btn small primary" onclick="completeEvent('${cid}','${x.event_id}')">完成并反馈</button><button class="btn small" onclick="cancelEvent('${x.event_id}')">取消</button>`:''}</div></div>`).join('')}</div>`:'<div class="empty"><strong>暂无电话/面试记录</strong>可以直接为该候选人创建电话筛选或结构化面试。</div>'}</div></section>`}

function candidateReevaluationHtml(cid,re){const rows=re?.drafts||[];return `<section class="panel"><div class="panel-head"><div><h3>复评与上下文变化</h3><span class="subtle">复评草案不会自动覆盖人工决定。</span></div><button class="btn small primary" onclick="openReeval('${cid}')">＋ 复评草案</button></div><div class="panel-body">${rows.length?`<div class="quick-list">${rows.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.summary||'复评草案')}</div><div class="quick-note">${esc(x.state)} · ${new Date(x.created_at).toLocaleString()}</div></div>${x.state==='draft'?`<button class="btn small" onclick="applyReeval('${cid}','${x.draft_id}')">查看/应用差异</button>`:''}</div>`).join('')}</div>`:'<div class="empty">暂无复评草案</div>'}</div></section>`}

/* Navigation hint only: the row never claims what work is pending. The authoritative
   next action is rendered inside the workspace from Core workspace/event/offer reads. */
function rowNextAction(){return{label:'打开工作台',section:'evidence'}}
window.openCandidateNext=async id=>{const c=(state.candidateRows||[]).find(x=>x.candidate_id===id)||{};const na=rowNextAction();state.candidateReturnTab='candidates';state.candidateId=id;state.candidateSection=na.section;await candidateDrawer(id)};
/* S1b: one-click candidate actions. The list never guesses an authoritative
   state from pipeline_stage: ownership and event state are read from Core. */
window.openCandidateQuickAction=async(id,kind)=>{
  // A list action may outlive its summary or drawer GET. Never let an older
  // click select A or open A's form after the operator has moved to B.
  const requestedProjectId=state.projectId,requestedCandidateId=state.candidateId;
  const requestedTab=state.projectTab,requestedView=state.candidateView;
  const seq=(state.quickActionSeq||0)+1;
  state.quickActionSeq=seq;
  const onList=()=>state.page==='projects'&&state.projectId===requestedProjectId
    &&state.projectTab===requestedTab&&state.candidateView===requestedView
    &&state.candidateId===requestedCandidateId&&state.quickActionSeq===seq;
  const onCandidate=()=>state.page==='projects'&&state.projectId===requestedProjectId
    &&state.candidateId===id&&state.quickActionSeq===seq;
  try{
    if(!['verify','schedule','scorecard'].includes(kind))throw uiError('不支持的候选人操作');
    const row=(state.candidateRows||[]).find(x=>x.candidate_id===id);
    if(!row||row.archived)throw uiError('候选人不在当前可操作列表中，请刷新后重试');
    const summary=await api(`/api/v1/candidates/${id}/summary`);
    if(!onList())return;
    if(!summary||summary.project_id!==requestedProjectId)throw uiError('候选人已不属于当前项目，已阻止跳转');
    if(summary.archived)throw uiError('候选人已归档，请先恢复后再操作');
    state.candidateReturnTab='candidates';
    state.candidateId=id;
    state.candidateSection=kind==='verify'?'evidence':'process';
    await candidateDrawer(id);
    if(!onCandidate())return;
    if(kind==='schedule'){await window.openEvent(id,'interview');return}
    if(kind==='scorecard'){
      const result=await api(`/api/v1/candidates/${id}/events`);
      if(!onCandidate())return;
      const eligible=(result.events||[]).filter(e=>e.event_type==='interview'&&!['cancelled','no_show'].includes(e.event_state));
      if(eligible.length===1){await window.openScorecards(id,eligible[0].event_id);return}
      if(eligible.length>1){toast('该候选人有多场面试，请在当前面试面板选择准确的记录',true);return}
      toast('该候选人尚无可填写面评的面试记录，请先安排面试',true);
    }
  }catch(e){
    if(state.page==='projects'&&state.projectId===requestedProjectId&&state.quickActionSeq===seq)
      toast(e.message||'无法打开候选人操作',true);
  }
};
function workspaceNextAction(w,events,offers){if(!w)return{label:'导入材料',section:'evidence',hint:'先导入简历或材料',action:"setCandidateSection('evidence')"};if(w.blocking_count>0)return{label:'核实关键事实',section:'evidence',hint:`还有 ${w.blocking_count} 条标准缺证据`,action:"setCandidateSection('evidence')"};if(!(events.events||[]).length)return{label:'安排面试',section:'process',hint:'还没有面试或电话记录',action:`openEvent('${w.candidate_id}','interview')`};if(!w.decision_label){if(!w.decision_context_hash)return{label:'完善材料后再决定',section:'evidence',hint:'材料或标准尚未发布',action:''};return{label:'记录人工决定',section:'evidence',hint:'面试记录已就绪',action:`openDecision('${w.candidate_id}')`}}if(!(offers.offers||[]).length)return{label:'创建 Offer',section:'offer',hint:'人工决定已记录',action:`openOffer('${w.candidate_id}')`};return{label:'更新 Offer 状态',section:'offer',hint:'',action:''}}
function uiError(message){const e=new Error(message);e.userFacing=true;return e}
async function candidateProjectId(cid){if(!cid)throw uiError('缺少候选人上下文，已阻止操作');const cache=state.candidateProject||(state.candidateProject={});if(cache[cid])return cache[cid];const s=await api(`/api/v1/candidates/${cid}/summary`);if(!s||!s.project_id)throw uiError('无法确认候选人所属项目，请重新打开候选人');cache[cid]=s.project_id;return s.project_id}
/* Only the server's Published `current` counts. `draft` is never a fallback and a
   mismatched project/revision pair fails closed instead of guessing. */
async function loadPublishedProtocol(pid){if(!pid)throw uiError('缺少项目上下文，无法读取已发布标准');const pw=await api(`/api/v1/projects/${pid}/protocol-workspace`);if(!pw||pw.project_id!==pid)throw uiError('岗位标准与当前项目不一致，已阻止操作');const view=pw.current;if(!view||!pw.current_revision_id||view.revision_id!==pw.current_revision_id)throw uiError('该项目还没有已发布的岗位标准：请先到「建岗与标准」保存并发布面试核实项');return{projectId:pid,revisionId:pw.current_revision_id,revision:view.revision,criteria:(view.criteria||[]).filter(c=>c&&c.criterion_key),stages:view.assessment_stages||[]}}
async function interviewDraftContext(cid,type){const pid=await candidateProjectId(cid);const p=await loadPublishedProtocol(pid);if(type==='phone_screen')return Object.assign({},p,{cid,type,structured:false,rows:[],keys:[]});const stage=(p.stages||[]).find(s=>s&&(s.stage_key==='interview'||s.name==='面试'));const keys=((stage&&stage.criteria)||[]).filter(Boolean);if(!keys.length)throw uiError('已发布的岗位标准里没有「面试」阶段的核实项：请先在「建岗与标准」把标准加入面试阶段并发布');const rows=p.criteria.filter(c=>keys.includes(c.criterion_key));if(!rows.length)throw uiError('已发布标准里找不到面试阶段可用的核实项，请重新发布岗位标准');return Object.assign({},p,{cid,type,structured:true,rows,keys:rows.map(c=>c.criterion_key)})}
function probeOf(c){const list=(c&&Array.isArray(c.verification_probes))?c.verification_probes:[];return String((c&&c.probe)||list[0]||'')}
function criterionQuestionRows(ctx){if(!ctx||!ctx.rows||!ctx.rows.length)return '';return ctx.rows.map(c=>`<div class="criterion-block" data-criterion="${esc(c.criterion_key)}"><div class="criterion-head"><strong>${esc(c.name||'标准')}</strong><span class="subtle">${esc(probeOf(c)||'按标准提问')}</span></div>${c.definition?`<div class="criterion-def">${esc(c.definition)}</div>`:''}<div class="form-grid"><div class="field full"><label>问题</label><input class="input c-q" value="${esc(probeOf(c))}" placeholder="要问的问题"></div><div class="field full"><label>提问目的</label><input class="input c-p" placeholder="想核实什么（可留空）"></div></div></div>`).join('')}
function criterionFeedbackRows(keys,names,definitions){if(!keys||!keys.length)return '';const opts=[['strong','强'],['acceptable','可接受'],['concern','有顾虑'],['unknown','无法判断']];return keys.map(k=>`<div class="criterion-block" data-criterion="${esc(k)}"><div class="criterion-head"><strong>${esc((names&&names[k])||'标准')}</strong></div>${definitions&&definitions[k]?`<div class="criterion-def">${esc(definitions[k])}</div>`:''}<div class="form-grid"><div class="field"><label>评价</label><select class="select c-rating">${opts.map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select></div><div class="field"><label>建议</label><input class="input c-rec" placeholder="advance / hold / reject"></div><div class="field full"><label>行为观察</label><input class="input c-obs" placeholder="具体发生了什么"></div><div class="field"><label>支持证据</label><input class="input c-support" placeholder="原文或来源"></div><div class="field"><label>反对证据</label><input class="input c-counter" placeholder="可留空"></div></div></div>`).join('')}
function blockedNotice(title,message,extra){modal(title,`<div class="notice danger" role="alert"><strong>${esc(message)}</strong>${extra?`<div class="subtle" style="margin-top:6px">${esc(extra)}</div>`:''}</div>`,`<button class="btn" onclick="closeModal()">关闭</button>`)}
async function eventContext(cid,eid){if(!cid||!eid)throw uiError('缺少面试记录身份，已阻止操作');const data=await api(`/api/v1/candidates/${cid}/events`);const ev=(data.events||[]).find(x=>x.event_id===eid);if(!ev)throw uiError('该面试记录不属于当前候选人，已阻止操作');return ev}
/* Feedback and completion always follow the event's own recorded keys. A newer
   Published revision never remaps a historical interview; if an original key is
   gone from the current revision the write is refused with an explanation. */
async function eventWriteContext(cid,eid,prefetched){const ev=prefetched||await eventContext(cid,eid);const meta=ev.metadata||{};const keys=Array.from(new Set((meta.questions||[]).map(q=>q&&q.criterion_key).filter(Boolean)));if(!keys.length)throw uiError('这条面试记录没有绑定岗位标准，无法提交结构化反馈；请重新安排面试并在提纲中选择标准');const pid=await candidateProjectId(cid);const p=await loadPublishedProtocol(pid);const pinned=String(meta.protocol_revision_id||'');if(!pinned)throw uiError('这条面试记录没有保存创建时的标准版本，无法安全提交结构化反馈；请查看原记录，或重新安排面试');if(pinned!==p.revisionId)throw uiError('该面试按旧的标准版本创建，当前已发布版本已经变化；为避免把旧记录改写成新标准，已阻止提交。请查看原记录，或重新安排面试');const current=new Set(p.criteria.map(c=>c.criterion_key));if(keys.some(k=>!current.has(k)))throw uiError('面试记录里的标准已不在当前发布版本中，已阻止提交结构化反馈');const snap={};(meta.criteria_snapshot||[]).forEach(c=>{if(c&&c.criterion_key)snap[c.criterion_key]=c});const names={},definitions={};keys.forEach(k=>{names[k]=(snap[k]&&snap[k].name)||'';definitions[k]=(snap[k]&&snap[k].definition)||''});p.criteria.forEach(c=>{if(!names[c.criterion_key]){names[c.criterion_key]=c.name||'';definitions[c.criterion_key]=c.definition||''}});return{ev,meta,keys,names,definitions,pid,revisionId:pinned,currentRevisionId:p.revisionId}}
function collectInterviewQuestions(){return Array.from(document.querySelectorAll('#e-criteria .criterion-block')).map(b=>({criterion_key:b.dataset.criterion||'',question:(b.querySelector('.c-q')?.value||'').trim(),purpose:(b.querySelector('.c-p')?.value||'').trim()})).filter(q=>q.question)}
function collectCriterionFeedback(scope){return Array.from(document.querySelectorAll(`${scope} .criterion-block`)).map(b=>({criterion_key:b.dataset.criterion||'',rating:(b.querySelector('.c-rating')?.value||'unknown'),observation:(b.querySelector('.c-obs')?.value||'').trim(),supporting_evidence:(b.querySelector('.c-support')?.value||'').trim(),counter_evidence:(b.querySelector('.c-counter')?.value||'').trim(),recommendation:(b.querySelector('.c-rec')?.value||'').trim()}))}
async function candidateDrawer(cid,p=null){syncTopbar();
  if(!cid)return;
  const requestedProjectId=state.projectId;
  state.candidateId=cid;
  p=p||state.projects.find(x=>x.project_id===state.projectId)||{};
  const [contact,pipe,offers,actionPlan,events,reevaluations,w]=await Promise.all([
    api(`/api/v1/candidates/${cid}/contact`),
    api(`/api/v1/candidates/${cid}/pipeline`),
    api(`/api/v1/candidates/${cid}/offers`),
    api(`/api/v1/candidates/${cid}/action-plan`).catch(()=>null),
    api(`/api/v1/candidates/${cid}/events`).catch(()=>({events:[]})),
    api(`/api/v1/candidates/${cid}/reevaluations`).catch(()=>({drafts:[]})),
    api(`/api/v1/candidates/${cid}/workspace`).catch(()=>null)
  ]);
  if(state.page!=='projects'||state.projectId!==requestedProjectId||state.candidateId!==cid)return;
  state.currentCandidateId=cid;
  state.currentCandidateName=contact.display_name||null;
  syncTopbar();
  // A just-created candidate has no published material/decision context;
  // requesting an assessment then raises an expected 409. Avoid that
  // unnecessary backend call while still showing Source intake.
  const assessment=w?.decision_context_hash?await api(`/api/v1/candidates/${cid}/assessment`).catch(()=>null):null;
  // A second awaited read can finish after the operator switches candidate/project.
  // Never paint an old candidate over the currently selected workspace.
  if(state.page!=='projects'||state.projectId!==requestedProjectId||state.candidateId!==cid)return;
  const latest=offers.offers?.[0],section=state.candidateSection||'evidence';
  const evidenceBody=`${w?candidateWorkspaceHtml(w,assessment):'<div class="empty"><strong>尚无当前材料</strong>先上传简历、扫描件或录音。支持 PDF/DOCX/XLSX/TXT/图片/OCR/音频/ASR。</div>'}<div class="divider"></div><div class="two"><div class="field"><label>粘贴文本材料</label><textarea id="paste-material" class="textarea" placeholder="简历文本、电话记录、补充材料" oninput="cacheMaterialDraft('${cid}',this.value)">${esc(materialDrafts.get(cid)||'')}</textarea><button class="btn" onclick="pasteMaterial('${cid}')">保存并发布材料版本</button></div><div class="field"><label>上传文件 / OCR / ASR</label><input id="candidate-file" class="input" type="file" accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.png,.jpg,.jpeg,.mp3,.wav,.m4a,.mp4,.webm"><button class="btn primary" onclick="uploadCandidateFile('${cid}')">上传并处理</button><small class="subtle">图片和扫描 PDF 走 OCR；音频/视频走 ASR。Provider 未配置时原文件仍会保存。</small></div></div>`;
  const processBody=`<div class="candidate-process-grid"><section class="panel"><div class="panel-head"><h3>联系方式与跟进</h3><div class="actions"><button class="btn small" onclick="openContact('${cid}')">编辑联系方式</button><button class="btn small primary" onclick="openActionPlan('${cid}')">编辑下一步</button></div></div><div class="panel-body"><div class="quick-list"><div class="quick-item"><span>电话</span><strong>${esc(contact.phone||'未录入')}</strong></div><div class="quick-item"><span>邮箱</span><strong>${esc(contact.email||'未录入')}</strong></div><div class="quick-item"><span>人工确认</span><strong>${contact.user_confirmed?'已确认':'待确认'}</strong></div><div class="quick-item"><span>联系优先级 / 负责人</span><strong>${esc(actionPlan?.priority||'normal')} · ${esc(actionPlan?.owner||'未指定')}</strong></div><div class="quick-item"><span>联系状态</span><strong>${esc(actionPlan?.contact_status||'to_contact')}</strong></div><div class="quick-item"><span>下次联系</span><strong>${esc(actionPlan?.next_contact_at||'未安排')}</strong></div></div><p class="subtle" style="margin-bottom:0">${esc(actionPlan?.reason||'尚未填写下一步说明')}</p><div class="actions" style="margin-top:12px"><button class="btn" onclick="openPhoneScript('${cid}')">电话脚本 / 核实思路</button><button class="btn" onclick="openCandidateProjectFlow()">项目级招聘流程</button></div></div></section><section class="panel"><div class="panel-head"><h3>Pipeline 历史</h3><span class="status ${statusClass(pipe.current_stage)}">${stageLabel(pipe.current_stage)}</span></div><div class="panel-body">${pipe.transitions.length?`<div class="timeline">${pipe.transitions.slice().reverse().map(x=>`<div class="timeline-item"><strong>${stageLabel(x.from_stage)} → ${stageLabel(x.to_stage)}</strong><small>${esc(x.actor)} · ${new Date(x.created_at).toLocaleString()}</small><div class="subtle">${esc(x.reason||'')}</div></div>`).join('')}</div>`:'<div class="empty">尚无阶段变更</div>'}</div></section></div><div class="two">${candidateEventsHtml(cid,events)}${candidateReevaluationHtml(cid,reevaluations)}</div>`;
  const offerBody=`<section class="panel"><div class="panel-head"><div><h3>Offer 管理</h3><span class="subtle">Offer 状态与候选人 Pipeline 分开记录；接受 Offer 不会自动改写录用决定。</span></div><button class="btn primary" onclick="openOffer('${cid}')" ${['interview','offer'].includes(pipe.current_stage)?'':'disabled title="候选人需进入面试或 Offer 阶段"'}>＋ 创建 Offer</button></div><div class="panel-body">${offers.offers?.length?`<div class="quick-list">${offers.offers.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.title)} · ${esc(offerLabels[x.status]||x.status)}</div><div class="quick-note">目标入职：${esc(x.target_start_date||'待定')} · ${esc(x.compensation_note||'暂无薪酬说明')}</div></div><button class="btn small" onclick="openOfferStatus('${x.offer_id}','${x.status}','${cid}')" ${offerNextStatuses[x.status]?.length?'':'disabled title="Offer 已处于终态"'}>更新状态</button></div>`).join('')}</div>`:'<div class="empty"><strong>尚无 Offer</strong>候选人进入面试或 Offer 阶段后，可在这里创建并跟踪草案、批准、发送和接受状态。</div>'}</div></section>`;
  const sectionBody=section==='process'?processBody:section==='offer'?offerBody:`<section class="panel"><div class="panel-head"><div><h3>证据与判断</h3><span class="subtle">材料、Claim、评价标准、人工核实与最终人工决定集中在同一工作面。</span></div>${w?`<button class="btn primary" onclick="extractAllClaims('${cid}')">AI 提取当前材料事实</button>`:''}</div><div class="panel-body">${evidenceBody}</div></section>`;
  $('#content').innerHTML=`<div class="candidate-workspace-page"><div class="candidate-workspace-breadcrumb"><span class="subtle">${esc(p.title||'招聘项目')} / 候选人</span></div><div class="candidate-workspace-head"><div><div class="pill-row"><span class="status ${statusClass(pipe.current_stage)}">${stageLabel(pipe.current_stage)}</span>${w?.readiness_label?`<span class="status info">${esc(w.readiness_label)}</span>`:''}</div><h1>${esc(contact.display_name)}</h1><div class="subtle">${esc(contact.phone||'未录电话')} · ${esc(contact.email||'未录邮箱')} · ${contact.user_confirmed?'联系方式已人工确认':'联系方式待人工确认'}</div></div><div class="actions"><button class="btn" onclick="openCandidateBrief('${cid}')">候选人简报</button><button class="btn" onclick="openContact('${cid}')">联系方式</button><button class="btn" onclick="openActionPlan('${cid}')">行动计划</button><button class="btn primary" onclick="openStage('${cid}','${pipe.current_stage}')">推进阶段</button></div></div><div class="candidate-summary-strip"><div><small>当前阶段</small><strong>${stageLabel(pipe.current_stage)}</strong></div><div><small>决策状态</small><strong>${esc(w?.readiness_label||'待材料/标准')}</strong></div><div><small>当前决定</small><strong>${esc(w?.decision_label||'未决定')}</strong></div><div><small>Offer</small><strong>${latest?esc(offerLabels[latest.status]||latest.status):'尚无 Offer'}</strong></div><div><small>下次联系</small><strong>${esc(actionPlan?.next_contact_at||'未安排')}</strong></div></div>${(()=>{const na=workspaceNextAction(w,events,offers);const steps=[['evidence','资料','材料、Claim 与核实',!!w],['process','面试','安排、记录与 Scorecard',(events.events||[]).length>0],['offer','决定','人工决定与 Offer',!!(offers.offers||[]).length||!!w?.decision_label]];return `<div class="next-action"><div><small>当前要做</small><strong>${esc(na.label)}</strong>${na.hint?`<span class="subtle"> · ${esc(na.hint)}</span>`:''}</div><div class="actions">${na.action?`<button class="btn primary" onclick="${na.action}">${esc(na.label)}</button>`:''}<button class="btn" onclick="setCandidateSection('${na.section}')">打开面板</button></div></div><div class="candidate-steps">${steps.map(([k,t,d,done],i)=>`<button class="candidate-step ${section===k?'active':''} ${done&&section!==k?'done':''}" onclick="setCandidateSection('${k}')"><span>${i+1}</span><div><strong>${t}</strong><small>${d}</small></div></button>`).join('')}</div>`})()}<div class="candidate-workspace-content">${sectionBody}</div></div>`}

window.openContact=async cid=>{try{const c=await api(`/api/v1/candidates/${cid}/contact`);modal('候选人联系方式',`<div class="form-grid"><div class="field"><label>姓名</label><input id="ct-name" class="input" value="${esc(c.display_name)}"></div><div class="field"><label>电话</label><input id="ct-phone" class="input" value="${esc(c.phone)}"></div><div class="field full"><label>邮箱</label><input id="ct-email" class="input" value="${esc(c.email)}"></div><label class="field full"><span>人工确认</span><span><input id="ct-confirm" type="checkbox" ${c.user_confirmed?'checked':''}> 我已人工核对以上联系方式</span></label></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveContact('${cid}')">保存</button>`)}catch(e){toast(e.message,true)}};window.saveContact=async cid=>{try{await api(`/api/v1/candidates/${cid}/contact`,{method:'PATCH',body:JSON.stringify({display_name:$('#ct-name').value,phone:$('#ct-phone').value,email:$('#ct-email').value,user_confirmed:$('#ct-confirm').checked,actor:'human'})});toast('联系方式已保存');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
window.openStage=(cid,current)=>modal('候选人阶段',`<div class="field"><label>当前阶段</label><div class="status ${statusClass(current)}">${stageLabel(current)}</div></div><div class="field" style="margin-top:10px"><label>推进到</label><select id="stage-next" class="select">${Object.entries(stageLabels).map(([v,l])=>`<option value="${v}" ${v===current?'selected':''}>${l}</option>`).join('')}</select></div><div class="field" style="margin-top:10px"><label>人工理由</label><textarea id="stage-reason" class="textarea"></textarea></div><p class="subtle">阶段推进属于人工业务动作。AI 不能自动改变 Pipeline。</p>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveStage('${cid}')">确认推进</button>`);window.saveStage=async cid=>{try{await api(`/api/v1/candidates/${cid}/stage`,{method:'POST',body:JSON.stringify({stage:$('#stage-next').value,reason:$('#stage-reason').value||'人工推进',actor:'human'})});toast('候选人阶段已更新');closeModal();await projectWorkspace()}catch(e){toast(e.message,true)}};
window.openOffer=cid=>modal('创建 Offer',`<div class="form-grid"><div class="field"><label>Offer 职位</label><input id="offer-title" class="input"></div><div class="field"><label>目标入职日</label><input id="offer-start" class="input" type="date"></div><div class="field full"><label>薪酬说明</label><input id="offer-comp" class="input" placeholder="base + bonus / 薪酬范围"></div><div class="field full"><label>其他条款</label><textarea id="offer-terms" class="textarea"></textarea></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveOffer('${cid}')">创建 Offer 草案</button>`);window.saveOffer=async cid=>{try{await api(`/api/v1/candidates/${cid}/offers`,{method:'POST',body:JSON.stringify({title:$('#offer-title').value,compensation_note:$('#offer-comp').value,target_start_date:$('#offer-start').value,terms:$('#offer-terms').value,actor:'human'})});toast('Offer 草案已创建');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};window.openOfferStatus=(oid,current,cid)=>modal('更新 Offer 状态',`<div class="field"><label>Offer 状态</label><select id="offer-status" class="select"><option value="">请选择下一状态</option>${(offerNextStatuses[current]||[]).map(v=>`<option value="${v}">${offerLabels[v]}</option>`).join('')}</select></div><div class="field" style="margin-top:10px"><label>理由</label><textarea id="offer-status-reason" class="textarea"></textarea></div><p class="subtle">Offer 接受不等于自动录用；录用仍需人工将候选人推进到“录用”阶段并完成最终决定。</p>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveOfferStatus('${oid}','${cid}','${current}')">保存</button>`);window.saveOfferStatus=async(oid,cid,current)=>{try{if(!$('#offer-status').value){toast('请选择合法的下一状态',true);return}await api(`/api/v1/offers/${oid}/status`,{method:'POST',body:JSON.stringify({status:$('#offer-status').value,expected_status:current,reason:$('#offer-status-reason').value||'人工更新 Offer',actor:'human'})});toast('Offer 状态已更新');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
function candidateWorkspaceHtml(w,a){const fit=a?.fit_score==null?'待证据闭合':`${a.fit_score}%`;const cov=a?`${Math.round(Number(a.evidence_coverage||0)*100)}%`:'—';return `<div class="grid kpi" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))"><div class="kpi-card"><div class="kpi-label">决策状态</div><div class="kpi-value" style="font-size:20px">${esc(w.readiness_label)}</div></div><div class="kpi-card"><div class="kpi-label">岗位匹配</div><div class="kpi-value" style="font-size:20px">${esc(fit)}</div></div><div class="kpi-card"><div class="kpi-label">证据覆盖</div><div class="kpi-value" style="font-size:20px">${esc(cov)}</div></div><div class="kpi-card"><div class="kpi-label">阻塞标准</div><div class="kpi-value">${w.blocking_count}</div></div><div class="kpi-card"><div class="kpi-label">当前决定</div><div class="kpi-value" style="font-size:20px">${esc(w.decision_label||'未决定')}</div></div></div>${a&&!a.publishable_for_comparison?`<p class="subtle">匹配分数尚不用于候选人比较：仍有未决标准、冲突或证据覆盖不足。缺失证据不会自动按“不满足”计分。</p>`:''}${w.stale_decision_id?`<div class="provider-card" style="margin:12px 0"><h3>历史决定已过期</h3><p class="subtle">上一决策上下文中的人工决定为 <strong>${esc(w.stale_decision_label)}</strong>。材料或招聘协议已经变化，因此该决定不会自动继续有效。</p><div class="quick-note">原理由：${esc(w.stale_decision_reason||'—')}</div><div class="actions" style="margin-top:10px"><button class="btn" onclick="openDecisionHistory('${w.candidate_id}')">查看决定历史</button><button class="btn primary" onclick="reaffirmHistoricalDecision('${w.candidate_id}')" ${w.decision_reaffirmable?'':'disabled title="当前证据尚不支持重申：请先核实关键评价标准"'}>按当前证据重申</button></div></div>`:''}<div class="actions" style="margin:10px 0 14px"><button class="btn small" onclick="openDecisionHistory('${w.candidate_id}')">决定 Lineage</button><button class="btn small" onclick="openCandidateAiRuns('${w.candidate_id}')">AI Run Ledger</button></div><h3>当前材料</h3>${(w.sources||[]).map(s=>`<div class="source-card"><div><strong>${esc(s.source_kind)}</strong> <span class="mono subtle">${esc(s.source_id)}</span> ${s.in_current_material?'<span class="status good">当前版本</span>':'<span class="status">历史材料</span>'}</div><div class="source-text">${esc(s.has_text?s.text_preview:'（二进制原始材料）')}</div><div class="actions"><button class="btn small" onclick="openSourceViewer('${s.source_id}')">Source Viewer</button><button class="btn small" onclick="openScoringView('${s.source_id}')" ${s.has_text?'':'disabled'}>隐私评分视图</button><button class="btn small" onclick="extractSource('${w.candidate_id}','${s.source_id}')" ${s.has_text&&s.in_current_material?'':'disabled'}>从此材料提取 Claim</button><button class="btn small" onclick="srwManualClaimOpen('${w.candidate_id}','${s.source_id}')" ${s.has_text&&s.in_current_material?'':'disabled'}>人工提出 Claim</button></div></div>`).join('')||'<div class="empty">暂无材料</div>'}<h3>AI / Source Claims</h3>${(w.claims||[]).map(c=>`<div class="claim ${c.confirmation_state}" id="srw-claim-${esc(c.claim_id)}"><div>${esc(c.normalized_text)}</div><div class="quick-note">状态：${esc(c.confirmation_state)} · Source ${esc(c.source_id)}</div><div class="actions" style="margin-top:8px"><button class="btn small" onclick="openClaimGrounding('${c.claim_id}')">定位原文</button>${c.confirmation_state==='unreviewed'?`<button class="btn small primary" onclick="reviewClaim('${c.claim_id}',true,'${w.candidate_id}')">确认事实</button><button class="btn small danger" onclick="reviewClaim('${c.claim_id}',false,'${w.candidate_id}')">拒绝提议</button>`:''}</div></div>`).join('')||'<div class="empty">尚无 Claim。可通过 AI 提取，或人工选取当前材料原文提出待核实事实。</div>'}<h3>评价标准与人工核实</h3><table class="table"><thead><tr><th>标准</th><th>状态</th><th>证据</th><th>缺口/核实问题</th><th></th></tr></thead><tbody>${(w.criteria||[]).map(c=>`<tr><td><strong>${esc(c.name)}</strong></td><td>${esc(c.status_label)} ${c.carried_forward?'<span class="status info">沿用已定位证据</span>':''}</td><td>${esc(c.evidence_label)}</td><td>${esc(c.gap||c.probe||'—')}</td><td><button class="btn small" onclick="openVerify('${w.candidate_id}','${esc(c.criterion_key)}','${esc(c.name)}')">人工核实</button></td></tr>`).join('')}</tbody></table><div class="divider"></div><div class="actions"><button class="btn primary" onclick="openDecision('${w.candidate_id}')" ${!w.decision_context_hash?'disabled title="必须先发布岗位标准与候选人材料"':''}>记录人工决定</button></div>`}
window.openSourceContent=async url=>{try{const d=await api(url);modal('完整材料原文',`<div class="codebox" style="white-space:pre-wrap;max-height:65vh;overflow:auto">${esc(d.text_content)}</div>`)}catch(e){toast(e.message,true)}};window.openScoringView=async sid=>{try{const d=await api(`/api/v1/sources/${sid}/scoring-view`);modal('隐私评分视图',`<p class="subtle">发送给远程文本 AI 的是这一份等长脱敏投影。姓名、电话、邮箱、证件号、精确地址等不会直接出站。</p><div class="pill-row">${Object.entries(d.redaction_counts||{}).map(([k,v])=>`<span class="status">${esc(k)} ${v}</span>`).join('')||'<span class="status good">未检测到需脱敏字段</span>'}</div><div class="codebox" style="white-space:pre-wrap;max-height:58vh;overflow:auto;margin-top:10px">${esc(d.text_content)}</div>`)}catch(e){toast(e.message,true)}};window.openClaimGrounding=async id=>{try{const d=await api(`/api/v1/claims/${id}/grounding`),l=d.locator||{};modal('Claim 原文定位',`<div class="quick-list"><div class="quick-item"><span>页码</span><strong>${esc(l.page??'—')}</strong></div><div class="quick-item"><span>字符范围</span><strong>${esc(`${l.char_start??'—'}–${l.char_end??'—'}`)}</strong></div><div class="quick-item"><span>PDF BBox</span><strong class="mono">${esc(l.bbox?JSON.stringify(l.bbox):'—')}</strong></div></div><div class="codebox" style="white-space:pre-wrap;margin-top:10px">${esc(l.quote||'')}</div>`,`<button class="btn" onclick="closeModal()">关闭</button><button class="btn primary" onclick="openSourceViewer('${d.source_id}','${l.page||1}','${d.claim_id}')">高亮打开 Source Viewer</button>`)}catch(e){toast(e.message,true)}};
window.cacheMaterialDraft=(cid,value)=>{if(!materialDrafts.has(cid)&&materialDrafts.size>=20)materialDrafts.delete(materialDrafts.keys().next().value);materialDrafts.set(cid,value)};
window.pasteMaterial=async cid=>{const text=materialDrafts.get(cid)??$('#paste-material')?.value??'';if(!text.trim()){toast('请先输入材料文本',true);return}try{await api(`/api/v1/candidates/${cid}/sources/text`,{method:'POST',body:JSON.stringify({text_content:text,filename:'pasted.txt',source_kind:'resume',publish_material:true})});if(materialDrafts.get(cid)===text)materialDrafts.delete(cid);toast('文本材料已发布');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
window.uploadCandidateFile=async cid=>{const f=$('#candidate-file').files[0];if(!f){toast('请选择文件',true);return}try{const r=await uploadFile(cid,f);toast(r.task_status?`文件已保存，任务状态：${r.task_status}`:'文件已导入');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
window.extractSource=async(cid,sid)=>{try{const r=await api(`/api/v1/candidates/${cid}/evidence/extract-task`,{method:'POST',body:JSON.stringify({source_id:sid})});if(r.task_status==='waiting_provider')toast('AI 提取任务已保存；配置文本 AI 后可在后台任务中直接重试',true);else toast(`AI 提取任务状态：${r.task_status}`);closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
window.extractAllClaims=async cid=>{try{const w=await api(`/api/v1/candidates/${cid}/workspace`);let queued=0;for(const s of w.sources||[]){if(!s.has_text||!s.in_current_material)continue;await api(`/api/v1/candidates/${cid}/evidence/extract-task`,{method:'POST',body:JSON.stringify({source_id:s.source_id})});queued++}toast(`已提交 ${queued} 个当前材料 AI 提取后台任务`);closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
window.reviewClaim=async(id,accepted,cid)=>{try{await api(`/api/v1/claims/${id}/review`,{method:'POST',body:JSON.stringify({accepted,actor:'human'})});toast(accepted?'已确认为事实':'已拒绝事实提议');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
window.openVerify=(cid,key,name)=>modal(`人工核实 · ${name}`,`<div class="form-grid"><div class="field"><label>状态</label><select id="v-status" class="select"><option value="met">满足</option><option value="partial">部分满足</option><option value="missing">缺失</option><option value="conflict">冲突</option><option value="not_met">不满足</option></select></div><div class="field"><label>证据强度</label><select id="v-evidence" class="select"><option value="strong">强</option><option value="medium">中</option><option value="weak">弱</option><option value="none">无</option></select></div><div class="field full"><label>理由</label><textarea id="v-reason" class="textarea"></textarea></div><div class="field full"><label>证据缺口</label><input id="v-gap" class="input"></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveVerify('${cid}','${key}')">保存人工核实</button>`);
window.saveVerify=async(cid,key)=>{try{await api(`/api/v1/candidates/${cid}/verifications`,{method:'POST',body:JSON.stringify({criterion_key:key,status:$('#v-status').value,evidence_level:$('#v-evidence').value,reason:$('#v-reason').value||'人工核实',note:$('#v-reason').value||'人工核实',gap:$('#v-gap').value,actor:'human'})});toast('人工核实已记录');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
window.openDecision=cid=>modal('记录人工决定',`<div class="field"><label>决定</label><select id="d-decision" class="select"><option value="advance">推进</option><option value="hold">暂缓</option><option value="reject">拒绝</option></select></div><div class="field" style="margin-top:10px"><label>决定理由</label><textarea id="d-reason" class="textarea"></textarea></div><p class="subtle">最终决定必须由人工明确提交；AI、OCR、ASR 不会代替此动作。</p>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveDecision('${cid}')">提交人工决定</button>`);
window.saveDecision=async cid=>{try{await api(`/api/v1/candidates/${cid}/decision`,{method:'POST',body:JSON.stringify({decision:$('#d-decision').value,reason:$('#d-reason').value||'人工决定',actor:'human'})});toast('人工决定已记录');closeModal();await candidateDrawer(cid)}catch(e){toast(e.message,true)}};
async function flowTab(el,p){let candidates=[];try{candidates=(await api(`/api/v1/projects/${state.projectId}/candidate-search?q=${encodeURIComponent(state.flowQuery)}&limit=20`)).candidates||[]}catch{};let cid=state.flowCandidateId;if(cid&&!candidates.some(x=>x.candidate_id===cid)){try{const x=await api(`/api/v1/candidates/${cid}/summary`);candidates.unshift(x)}catch{cid=null}}if(!cid)cid=candidates[0]?.candidate_id;if(cid)state.flowCandidateId=cid;if(!cid){el.innerHTML=`<div class="searchbar"><input id="flow-q" class="input" placeholder="搜索候选人"><button class="btn" onclick="flowSearchCandidates()">搜索</button></div><div class="empty"><strong>暂无匹配候选人</strong>通过姓名搜索候选人，而不是固定加载前 100/200 人。</div>`;return}const [ev,re,pipe]=await Promise.all([api(`/api/v1/candidates/${cid}/events`),api(`/api/v1/candidates/${cid}/reevaluations`),api(`/api/v1/candidates/${cid}/pipeline`)]);el.innerHTML=`<div class="panel-head" style="padding:0 0 12px;border:0"><div><h3>招聘流程 · ${stageLabel(pipe.current_stage)}</h3><div class="searchbar"><input id="flow-q" class="input" value="${esc(state.flowQuery)}" placeholder="搜索候选人"><button class="btn small" onclick="flowSearchCandidates()">搜索</button><select class="select" onchange="setFlowCandidate(this.value)">${candidates.map(x=>`<option value="${x.candidate_id}" ${x.candidate_id===cid?'selected':''}>${esc(x.display_name)} · ${stageLabel(x.pipeline_stage)}</option>`).join('')}</select></div></div><div class="actions"><button class="btn" onclick="openContactWorkbench()">联系工作台</button><button class="btn" onclick="openPhoneScript('${cid}')">电话脚本</button><button class="btn" onclick="openEvent('${cid}','phone_screen')">＋ 电话筛选</button><button class="btn primary" onclick="openEvent('${cid}','interview')">＋ 面试排期</button><button class="btn" onclick="openReeval('${cid}')">＋ 复评草案</button></div></div><div class="two"><section><h3>面试 / 电话排期</h3>${ev.events.length?`<div class="timeline">${ev.events.map(x=>`<div class="timeline-item"><strong>${esc(x.title||x.event_type)} <span class="status ${statusClass(x.event_state)}">${esc(x.event_state)}</span></strong><small>${x.scheduled_at?new Date(x.scheduled_at).toLocaleString():new Date(x.created_at).toLocaleString()} · ${x.duration_minutes||0} 分钟 · ${esc(x.interviewer||'未指定')}</small><div>${esc(x.notes)}</div><div class="subtle">地点：${esc(x.location||'—')} · outcome：${esc(x.outcome||'—')}</div>${x.event_type==='interview'?`<div class="actions" style="margin-top:6px"><button class="btn small" onclick="openScorecards('${cid}','${x.event_id}')">独立 Scorecard</button></div>`:''}${x.editable_evidence_source?`<div class="actions" style="margin-top:6px"><button class="btn small" onclick="correctEvent('${cid}','${x.event_id}')">更正证据记录</button></div>`:''}${x.event_state==='scheduled'?`<div class="actions" style="margin-top:6px"><button class="btn small primary" onclick="completeEvent('${cid}','${x.event_id}')">完成并提交结构化反馈</button><button class="btn small" onclick="cancelEvent('${x.event_id}')">取消</button></div>`:''}</div>`).join('')}</div>`:'<div class="empty">暂无电话/面试记录</div>'}</section><section><h3>复评草案</h3>${re.drafts.length?re.drafts.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.summary||'复评草案')}</div><div class="quick-note">${esc(x.state)} · ${new Date(x.created_at).toLocaleString()}</div></div>${x.state==='draft'?`<button class="btn small" onclick="applyReeval('${cid}','${x.draft_id}')">查看/应用差异</button>`:''}</div>`).join(''):'<div class="empty">暂无复评草案</div>'}</section></div>`}
window.flowSearchCandidates=()=>{state.flowQuery=$('#flow-q')?.value||'';state.flowCandidateId=null;projectWorkspace()};
window.openEvent=async(cid,type)=>{
  // An in-flight Published-protocol GET must not reopen an older candidate's
  // form, or overwrite a newer dialog, after HR changes the workspace.
  const requestedProjectId=state.projectId,requestedCandidateId=state.candidateId;
  const requestedFlowCandidateId=state.flowCandidateId;
  const requestedModalGeneration=state.modalGeneration||0;
  const stillCurrent=()=>state.page==='projects'&&state.projectId===requestedProjectId
    &&(state.modalGeneration||0)===requestedModalGeneration
    &&((requestedCandidateId===cid&&state.candidateId===cid)
       ||(!requestedCandidateId&&!state.candidateId&&state.projectTab==='candidates'
          &&state.candidateView==='flow'&&requestedFlowCandidateId===cid
          &&state.flowCandidateId===cid));
  if(!stillCurrent())return;
  let ctx=null,error='';
  try{ctx=await interviewDraftContext(cid,type)}
  catch(e){if(type==='phone_screen'){ctx={cid,type,structured:false,rows:[],keys:[],revisionId:null,projectId:null,revision:null}}
           else{error='无法读取已发布的岗位标准（'+((e&&e.message)||'网络或服务异常')+'），已阻止创建结构化面试'}}
  if(!stillCurrent())return;
  if(error){state.eventDraft=null;blockedNotice('新增结构化面试',error,'没有已发布标准时不会创建结构化面试，也不会写入任何记录。请先到「建岗与标准」保存并发布面试核实项。');return}
  state.eventDraft={cid,type,projectId:ctx.projectId,revisionId:ctx.revisionId,revision:ctx.revision,keys:[...ctx.keys],structured:ctx.structured,snapshot:ctx.rows.map(c=>({criterion_key:c.criterion_key,name:c.name||'',definition:c.definition||''}))};
  const outline=ctx.structured
    ?`<div class="field full"><label>面试提纲 · 按已发布标准（版本 R${esc(String(ctx.revision||1))}）</label><div id="e-criteria">${criterionQuestionRows(ctx)}</div><small class="subtle">问题已用标准里的核实探针预填，可直接修改；提交前会再核对标准版本。</small></div>`
    :`<div class="field full"><label>面试提纲</label><div class="empty"><strong>电话筛选只记录备注</strong>结构化核实项在「面试」阶段按已发布标准填写。</div></div>`;
  modal(type==='phone_screen'?'新增电话筛选 / 排期':'新增结构化面试',`<div class="form-grid"><div class="field"><label>标题</label><input id="e-title" class="input" value="${type==='phone_screen'?'电话筛选':'面试'}"></div><div class="field"><label>状态</label><select id="e-state" class="select"><option value="scheduled">已排期</option><option value="completed">已完成</option></select></div><div class="field"><label>计划时间</label><input id="e-time" class="input" type="datetime-local"></div><div class="field"><label>时长（分钟）</label><input id="e-duration" class="input" type="number" value="${type==='phone_screen'?30:60}"></div><div class="field"><label>面试官</label><input id="e-interviewer" class="input"></div><div class="field"><label>地点 / 会议链接</label><input id="e-location" class="input"></div>${outline}<div class="field full"><label>补充记录</label><textarea id="e-notes" class="textarea"></textarea></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveEvent('${cid}','${type}')">保存</button>`)};
function parseInterviewQuestions(v){return String(v||'').split(/\n+/).map(x=>x.trim()).filter(Boolean).map(line=>{const a=line.split('|').map(x=>x.trim());return {criterion_key:a[0]||'',question:a[1]||a[0]||'',purpose:a[2]||''}})}
window.saveEvent=async(cid,type)=>{
  const draft=state.eventDraft;
  // Pin the visible form and workspace across asynchronous Published GET and
  // event POST. Otherwise A's pending save can read B's later unsaved inputs.
  const formModal=$('#modal-root .modal'),requestedProjectId=state.projectId;
  const requestedCandidateId=state.candidateId,requestedFlowCandidateId=state.flowCandidateId;
  const requestedModalGeneration=state.modalGeneration||0;
  const stillCurrent=()=>state.page==='projects'&&state.projectId===requestedProjectId
    &&state.candidateId===requestedCandidateId
    &&state.flowCandidateId===requestedFlowCandidateId
    &&(state.modalGeneration||0)===requestedModalGeneration
    &&$('#modal-root .modal')===formModal&&state.eventDraft===draft;
  if(!draft||draft.cid!==cid||draft.type!==type||!formModal||!stillCurrent()){
    toast('面试上下文已失效，请关闭窗口后重新打开',true);return
  }
  try{
    let questions=[];
    if(draft.structured){
      const pid=await candidateProjectId(cid);
      if(!stillCurrent())return;
      if(pid!==draft.projectId)throw uiError('候选人所属项目已变化，已阻止保存');
      const fresh=await loadPublishedProtocol(draft.projectId);
      if(!stillCurrent())return;
      if(fresh.revisionId!==draft.revisionId)throw uiError('岗位标准已更新为新版本，请关闭本窗口、重新打开面试提纲后再提交');
      const allowed=new Set(fresh.criteria.map(c=>c.criterion_key));
      questions=collectInterviewQuestions();
      if(!questions.length)throw uiError('请至少保留一条面试问题；如果只是电话记录，请改用「电话筛选」');
      if(questions.some(q=>!q.criterion_key||!allowed.has(q.criterion_key)))throw uiError('面试问题与已发布标准不一致，请重新打开面试提纲');
    }
    if(!stillCurrent())return;
    const body={event_type:type,title:$('#e-title').value,notes:$('#e-notes').value,
      scheduled_at:$('#e-time').value?new Date($('#e-time').value).toISOString():'',
      duration_minutes:Number($('#e-duration').value||0),interviewer:$('#e-interviewer').value,
      location:$('#e-location').value,event_state:$('#e-state').value};
    if(questions.length)body.metadata={questions,protocol_revision_id:draft.revisionId,criteria_snapshot:draft.snapshot};
    await api(`/api/v1/candidates/${cid}/events`,{method:'POST',body:JSON.stringify(body)});
    // A successful earlier POST must not close B's newer unsaved dialog.
    if(!stillCurrent()){toast('原面试已保存，当前操作窗口保持不变');return}
    state.eventDraft=null;toast('流程记录已保存');closeModal();await candidateDrawer(cid)
  }catch(e){if(stillCurrent())toast(e.message||'保存失败',true)}
};
function bindCompletionModal(cid,eid,pid){
  const form=$('#modal-root .modal');
  if(form){form.dataset.completionCandidateId=cid;form.dataset.completionEventId=eid;form.dataset.completionProjectId=pid||''}
}
window.completeEvent=async(cid,eid)=>{
  const pid=state.projectId,selected=state.candidateId,flow=state.flowCandidateId;
  const generation=state.modalGeneration||0;
  const stillCurrent=()=>state.page==='projects'&&state.projectId===pid
    &&state.candidateId===selected&&state.flowCandidateId===flow
    &&(state.modalGeneration||0)===generation;
  try{
    const ev=await eventContext(cid,eid);
    if(!stillCurrent())return;
    const meta=ev.metadata||{};
    const keys=Array.from(new Set((meta.questions||[]).map(q=>q&&q.criterion_key).filter(Boolean)));
    if(!keys.length){
      if(ev.event_type==='interview')throw uiError('这条面试记录没有绑定岗位标准，无法提交结构化反馈；请重新安排面试并在提纲中选择标准');
      modal('完成电话筛选',`<div class="field"><label>Outcome</label><select id="event-outcome" class="select"><option value="proceed">建议推进</option><option value="hold">暂缓</option><option value="reject">建议拒绝</option><option value="completed">已完成</option></select></div><div class="field" style="margin-top:10px"><label>记录</label><textarea id="event-notes" class="textarea"></textarea></div><p class="subtle">电话筛选只记录结果与备注，不产生结构化反馈，也不会改写岗位标准。</p>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveEventCompletion('${cid}','${eid}','plain')">完成</button>`);
      bindCompletionModal(cid,eid,pid);
      return;
    }
    const ctx=await eventWriteContext(cid,eid,ev);
    if(!stillCurrent())return;
    modal('完成面试 / 电话筛选',`<div class="field"><label>Outcome</label><select id="event-outcome" class="select"><option value="proceed">建议推进</option><option value="hold">暂缓</option><option value="reject">建议拒绝</option><option value="completed">已完成</option></select></div><div class="field" style="margin-top:10px"><label>逐标准反馈（按该面试记录的标准）</label><div id="ev-criteria">${criterionFeedbackRows(ctx.keys,ctx.names,ctx.definitions)}</div></div><div class="field" style="margin-top:10px"><label>总体建议</label><input id="event-overall" class="input" placeholder="advance / hold / reject"></div><div class="field" style="margin-top:10px"><label>记录</label><textarea id="event-notes" class="textarea"></textarea></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveEventCompletion('${cid}','${eid}')">完成</button>`);
    bindCompletionModal(cid,eid,pid);
  }catch(e){if(stillCurrent())blockedNotice('完成面试',e.message||'无法读取该面试记录','未写入任何数据。')}
};

function parseInterviewFeedback(v){return String(v||'').split(/\n+/).map(x=>x.trim()).filter(Boolean).map(line=>{const a=line.split('|').map(x=>x.trim());return {criterion_key:a[0]||'',rating:a[1]||'unknown',observation:a[2]||'',supporting_evidence:a[3]||'',counter_evidence:a[4]||'',recommendation:a[5]||''}})}
window.saveEventCompletion=async(cid,id,plain)=>{
  const form=$('#modal-root .modal'),pid=state.projectId,selected=state.candidateId;
  const flow=state.flowCandidateId,generation=state.modalGeneration||0;
  const stillCurrent=()=>state.page==='projects'&&state.projectId===pid
    &&state.candidateId===selected&&state.flowCandidateId===flow
    &&(state.modalGeneration||0)===generation&&$('#modal-root .modal')===form
    &&form?.dataset.completionCandidateId===cid
    &&form?.dataset.completionEventId===id
    &&form?.dataset.completionProjectId===(pid||'');
  if(!stillCurrent()){toast('面试反馈上下文已失效，请重新打开原记录',true);return}
  try{
    if(plain==='plain'){
      const body={event_state:'completed',outcome:form.querySelector('#event-outcome').value,
        notes:form.querySelector('#event-notes').value};
      await api(`/api/v1/events/${id}`,{method:'PATCH',body:JSON.stringify(body)});
      if(!stillCurrent()){toast('原电话筛选已完成，当前窗口保持不变');return}
      toast('电话筛选已完成');closeModal();await candidateDrawer(cid);return;
    }
    const ctx=await eventWriteContext(cid,id);
    if(!stillCurrent())return;
    if(ctx.pid!==pid)throw uiError('面试记录与当前项目不一致，已阻止提交');
    const allowed=new Set(ctx.keys);
    const feedback=collectCriterionFeedback('#ev-criteria');
    if(!feedback.length)throw uiError('请至少填写一条标准反馈');
    if(feedback.some(f=>!f.criterion_key||!allowed.has(f.criterion_key)))throw uiError('反馈与面试原始标准不一致，已阻止提交');
    const merged=Object.assign({},ctx.meta,{feedback,overall_recommendation:form.querySelector('#event-overall').value});
    const body={event_state:'completed',outcome:form.querySelector('#event-outcome').value,
      notes:form.querySelector('#event-notes').value,metadata:merged};
    const before=await api(`/api/v1/events/${id}`,{method:'PATCH',body:JSON.stringify(body)});
    if(!stillCurrent()){toast('原面试反馈已提交，当前窗口保持不变');return}
    toast(before.source_id?'已完成并发布结构化面试 Source':'面试已完成');
    closeModal();await candidateDrawer(cid)
  }catch(e){if(stillCurrent())toast(e.message||'提交失败',true)}
};
window.correctEvent=async(cid,id)=>{try{const data=await api(`/api/v1/candidates/${cid}/events`);const e=(data.events||[]).find(x=>x.event_id===id);if(!e||!e.editable_evidence_source){toast('此记录没有可更正的事件原生证据',true);return}window.correctionEventData=e;const fields=(e.metadata?.questions||[]).map((q,i)=>`<div class="field"><label>问题 ${i+1} · ${esc(q.question||'')}</label><textarea class="textarea" data-corr-answer="${i}">${esc(q.answer||'')}</textarea></div>`).join('');modal('更正已完成面试证据',`<p class="subtle">更正只修改记录备注及已有问题的回答。旧 Source 和材料版本保留历史；已有人工决定需重新核实。</p><div class="field"><label>更正记录备注</label><textarea class="textarea" id="corr-notes">${esc(e.notes||'')}</textarea></div>${fields}`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveEventCorrection('${cid}','${id}','${e.source_id}')">保存更正并发布新证据</button>`)}catch(e){toast(e.message,true)}};
window.saveEventCorrection=async(cid,id,previousSourceId)=>{try{const e=window.correctionEventData;if(!e||e.event_id!==id||e.source_id!==previousSourceId||!e.editable_evidence_source)throw Error('更正上下文已经失效');const metadata=e.metadata||{};const questions=(metadata.questions||[]).map((q,i)=>{const field=document.querySelector(`[data-corr-answer="${i}"]`);if(!field)throw Error('问题编辑器缺失');return{...q,answer:field.value}});const updated=await api(`/api/v1/events/${id}`,{method:'PATCH',body:JSON.stringify({notes:$('#corr-notes').value,metadata:{...metadata,questions}})});window.correctionEventData=null;toast(updated.source_id===previousSourceId?'本次内容没有实质变更':'已保存更正；原证据与旧决定保留历史');closeModal();await projectWorkspace()}catch(e){toast(e.message,true)}};
window.cancelEvent=async id=>{if(!confirm('取消该排期？'))return;try{await api(`/api/v1/events/${id}`,{method:'PATCH',body:JSON.stringify({event_state:'cancelled'})});toast('排期已取消');await projectWorkspace()}catch(e){toast(e.message,true)}};
const reevaluationFeature=createReevaluationFeature({api,$,esc,modal,toast,closeModal:()=>window.closeModal(),refresh:projectWorkspace});
window.openReeval=reevaluationFeature.open;
window.applyReeval=reevaluationFeature.apply;

async function qualityTab(el,p){const [idq,anchors,reviews]=await Promise.all([api(`/api/v1/projects/${state.projectId}/identity-reviews`),api(`/api/v1/projects/${state.projectId}/calibration/anchors`),api(`/api/v1/projects/${state.projectId}/calibration/reviews`)]);const all=idq.reviews||[],pending=all.filter(x=>x.status==='pending'),mergeReady=all.filter(x=>x.status==='confirmed_same'&&!x.merge_performed),merged=all.filter(x=>x.merge_performed);el.innerHTML=`<div class="two"><section><div class="panel-head" style="padding:0 0 10px;border:0"><h3>候选人身份复核</h3><button class="btn primary" onclick="scanIdentity()">扫描重复身份</button></div><p class="subtle">精确邮箱/电话只用于发现候选重复线索。必须先人工确认“同一人”，再进入 Merge Preview；系统不会静默自动合并。</p>${pending.length?pending.map(x=>`<div class="quick-item" id="srw-review-${esc(x.review_id)}"><div><div class="quick-title">${esc(x.candidate_a.display_name)} ↔ ${esc(x.candidate_b.display_name)}</div><div class="quick-note">${esc(x.match_reason)} · 待人工判定</div></div><div class="actions"><button class="btn small primary" onclick="resolveIdentity('${x.review_id}','confirmed_same')">同一人</button><button class="btn small" onclick="resolveIdentity('${x.review_id}','confirmed_distinct')">不同人</button></div></div>`).join(''):'<div class="empty">没有待处理的身份复核项</div>'}${mergeReady.length?`<h3 style="margin-top:16px">已确认同一人 · 待 canonical merge</h3>${mergeReady.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.candidate_a.display_name)} ↔ ${esc(x.candidate_b.display_name)}</div><div class="quick-note">历史数据不会被重写；合并前必须查看影响预览。</div></div><button class="btn small primary" onclick="openIdentityMerge('${x.review_id}','${x.candidate_a.candidate_id}','${x.candidate_b.candidate_id}')">Merge Preview</button></div>`).join('')}`:''}${merged.length?`<p class="subtle" style="margin-top:12px">已完成 canonical merge：${merged.length} 项。</p>`:''}</section><section><div class="panel-head" style="padding:0 0 10px;border:0"><h3>判断纠错队列</h3><button class="btn" onclick="openJudgmentReview()">＋ 记录纠错</button></div>${(reviews.reviews||[]).filter(x=>x.state==='open').length?(reviews.reviews||[]).filter(x=>x.state==='open').map(x=>`<div class="quick-item" id="srw-review-${esc(x.review_id)}"><div><div class="quick-title">${esc(x.criterion_key)} · ${esc(x.error_class)}${x.candidate_name?` · ${esc(x.candidate_name)}`:' · 项目级'}</div><div class="quick-note">${esc(x.before)} → ${esc(x.after)} · ${esc(x.reason)}</div></div><div class="actions">${x.candidate_id?`<button class="btn small" onclick="openCandidate('${x.candidate_id}')">查看候选人</button>`:''}<button class="btn small primary" onclick="resolveJudgmentReview('${x.review_id}')">完成复核</button></div></div>`).join(''):'<div class="empty">暂无开放的判断纠错项</div>'}</section></div><div class="divider"></div><section><div class="panel-head" style="padding:0 0 10px;border:0"><div><h3>Criterion Anchor Cases</h3><div class="subtle">observed → human_reviewed → candidate → gold；Gold 必须由第二位不同复核者晋级。</div></div><button class="btn primary" onclick="openCreateAnchor()">＋ 新建 Anchor</button></div>${(anchors.anchors||[]).length?`<table class="table"><thead><tr><th>标准</th><th>案例</th><th>期望判断</th><th>证据</th><th>生命周期</th><th></th></tr></thead><tbody>${anchors.anchors.map(x=>`<tr><td>${esc(x.criterion_key)}</td><td>${esc(x.case_text.slice(0,100))}</td><td>${esc(x.expected_judgment)}</td><td>${esc(x.expected_evidence_level)}</td><td><span class="status ${x.lifecycle==='gold'?'good':'info'}">${esc(x.lifecycle)}</span></td><td>${x.lifecycle!=='gold'?`<button class="btn small" onclick="promoteAnchor('${x.anchor_id}','${x.lifecycle}')">晋级</button>`:''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">尚未建立校准 Anchor Case</div>'}</section>`}window.scanIdentity=async()=>{try{const r=await api(`/api/v1/projects/${state.projectId}/identity-reviews/scan`,{method:'POST',body:JSON.stringify({actor:'human'})});toast(`身份扫描完成：新增 ${r.created} 项`);await projectWorkspace()}catch(e){toast(e.message,true)}};window.resolveIdentity=async(id,status)=>{const note=prompt('复核说明：','人工核对联系方式与材料');if(note===null)return;try{await api(`/api/v1/identity-reviews/${id}/resolve`,{method:'POST',body:JSON.stringify({status,actor:'human',note})});toast(status==='confirmed_same'?'已确认同一人；请进入 Merge Preview 选择 canonical identity':'身份复核已记录');await projectWorkspace()}catch(e){toast(e.message,true)}};window.openJudgmentReview=()=>modal('记录判断纠错',`<div class="form-grid"><div class="field"><label>criterion_key</label><input id="jr-key" class="input"></div><div class="field"><label>触发场景</label><input id="jr-trigger" class="input" value="human_override"></div><div class="field"><label>原判断</label><input id="jr-before" class="input"></div><div class="field"><label>修正后</label><input id="jr-after" class="input"></div><div class="field full"><label>错误分类</label><select id="jr-reason" class="select"><option value="input_error">输入错误</option><option value="evidence_error">证据错误</option><option value="rubric_error">标准设计错误</option><option value="execution_error">执行错误</option><option value="decision_error">决策错误</option><option value="other">其他</option></select></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveJudgmentReview()">记录</button>`);window.saveJudgmentReview=async()=>{try{await api(`/api/v1/projects/${state.projectId}/calibration/reviews`,{method:'POST',body:JSON.stringify({trigger:$('#jr-trigger').value,criterion_key:$('#jr-key').value,before:$('#jr-before').value,after:$('#jr-after').value,reason:$('#jr-reason').value,actor:'human'})});closeModal();toast('判断纠错已进入复核队列');await projectWorkspace()}catch(e){toast(e.message,true)}};window.resolveJudgmentReview=async id=>{const note=prompt('复核结论 / 处理说明：','已复核并确认纠错处理');if(!note)return;try{await api(`/api/v1/calibration/reviews/${id}/resolve`,{method:'POST',body:JSON.stringify({actor:'human',note})});toast('判断纠错复核已完成');await projectWorkspace()}catch(e){toast(e.message,true)}};window.openCreateAnchor=()=>modal('新建 Criterion Anchor',`<div class="form-grid"><div class="field"><label>criterion_key</label><input id="an-key" class="input"></div><div class="field"><label>期望判断</label><select id="an-j" class="select">${['met','partial','missing','conflict','not_met'].map(x=>`<option>${x}</option>`).join('')}</select></div><div class="field"><label>期望证据等级</label><select id="an-e" class="select">${['strong','medium','weak','none'].map(x=>`<option>${x}</option>`).join('')}</select></div><div class="field full"><label>案例文本</label><textarea id="an-text" class="textarea"></textarea></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveAnchor()">创建</button>`);window.saveAnchor=async()=>{try{await api(`/api/v1/projects/${state.projectId}/calibration/anchors`,{method:'POST',body:JSON.stringify({criterion_key:$('#an-key').value,case_text:$('#an-text').value,expected_judgment:$('#an-j').value,expected_evidence_level:$('#an-e').value,actor:'human'})});closeModal();toast('Anchor 已创建');await projectWorkspace()}catch(e){toast(e.message,true)}};window.promoteAnchor=async(id,current)=>{const order=['observed','human_reviewed','candidate','gold'],target=order[order.indexOf(current)+1],actor=prompt(target==='gold'?'Gold 晋级必须填写与首位复核者不同的复核人：':'复核人：','human');if(!actor)return;try{await api(`/api/v1/calibration/anchors/${id}/promote`,{method:'POST',body:JSON.stringify({target,actor})});toast(`Anchor 已晋级到 ${target}`);await projectWorkspace()}catch(e){toast(e.message,true)}};
async function auditTab(el,p){const limit=25;const d=await api(`/api/v1/projects/${state.projectId}/audit?limit=${limit}&offset=${state.auditOffset}`);el.innerHTML=`<div class="two"><div><h3>协议版本</h3><table class="table"><thead><tr><th>版本</th><th>状态</th><th>创建</th><th>Hash</th></tr></thead><tbody>${d.protocol_revisions.map(x=>`<tr><td>v${x.revision}</td><td><span class="status ${statusClass(x.state)}">${esc(x.state)}</span></td><td>${new Date(x.created_at).toLocaleString()}</td><td class="mono">${esc(x.content_hash.slice(0,12))}…</td></tr>`).join('')}</tbody></table></div><div><h3>审计时间线 <span class="subtle">${d.total} 项</span></h3>${d.audit_events.length?`<div class="timeline">${d.audit_events.map(x=>`<div class="timeline-item"><strong>${esc(x.event_type)}</strong><small>${esc(x.actor)} · ${new Date(x.created_at).toLocaleString()}</small><div class="subtle">${esc(x.reason||x.entity_type)}</div></div>`).join('')}</div>`:'<div class="empty">暂无审计事件</div>'}<div class="actions" style="justify-content:flex-end"><button class="btn small" ${d.offset<=0?'disabled':''} onclick="auditPage(-${limit})">上一页</button><button class="btn small" ${d.offset+d.limit>=d.total?'disabled':''} onclick="auditPage(${limit})">下一页</button></div></div></div>`}
window.auditPage=d=>{state.auditOffset=Math.max(0,state.auditOffset+d);projectWorkspace()};
async function refreshProjects(){const d=await api('/api/v1/projects');state.projects=d.projects||[]}
async function ensureProjects(){if(!state.projects.length){const d=await api('/api/v1/projects');state.projects=d.projects||[]}return state.projects}
function projectOptions(){return state.projects.map(p=>`<option value="${p.project_id}">${esc(p.title)} · ${esc(p.protocol_title||'')}</option>`).join('')}
async function templatesPage(){await ensureProjects();const d=await api('/api/v1/templates');$('#content').innerHTML=head('岗位模板','模板应保存可复用的标准定义，并能够从项目生成、编辑及应用到新项目。',`<button class="btn" onclick="saveCurrentAsTemplate()">从当前项目保存模板</button><button class="btn primary" onclick="openTemplate()">＋ 新建模板</button>`)+`<section class="panel"><div class="table-wrap"><table class="table"><thead><tr><th>模板</th><th>岗位</th><th>标准数</th><th>更新</th><th></th></tr></thead><tbody>${d.templates.length?d.templates.map(x=>`<tr><td><strong>${esc(x.name)}</strong></td><td>${esc(x.role_title)}</td><td>${x.payload?.criteria?.length||0}</td><td>${new Date(x.updated_at).toLocaleString()}</td><td class="right"><button class="btn small" onclick='editTemplate(${JSON.stringify(JSON.stringify(x)).replace(/'/g,"&#39;")})'>编辑模板</button> <button class="btn small primary" onclick="applyTemplate('${x.template_id}')">应用到项目</button> <button class="btn small danger" onclick="deleteTemplate('${x.template_id}')">删除</button></td></tr>`).join(''):'<tr><td colspan="5"><div class="empty"><strong>暂无模板</strong>可从成熟项目保存完整标准模板。</div></td></tr>'}</tbody></table></div></section>`}
window.openTemplate=()=>modal('新建岗位模板',`<div class="form-grid"><div class="field"><label>模板名称</label><input id="t-name" class="input"></div><div class="field"><label>岗位名称</label><input id="t-role" class="input"></div><div class="field full"><label>标准（每行一个）</label><textarea id="t-criteria" class="textarea" placeholder="战略分析\n跨团队协同\n数据能力"></textarea></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveTemplate()">保存模板</button>`);
window.saveTemplate=async()=>{const criteria=$('#t-criteria').value.split(/\n+/).map(x=>x.trim()).filter(Boolean).map(name=>({name,decision_critical:false,verification_required:true,verification_probes:[],assessment_stages:[{stage_key:'resume',required:true}]}));try{await api('/api/v1/templates',{method:'POST',body:JSON.stringify({name:$('#t-name').value,role_title:$('#t-role').value,payload:{criteria}})});closeModal();toast('模板已保存');await templatesPage()}catch(e){toast(e.message,true)}};
window.editTemplate=s=>{const x=JSON.parse(s);modal('编辑模板',`<div class="form-grid"><div class="field"><label>模板名称</label><input id="te-name" class="input" value="${esc(x.name)}"></div><div class="field"><label>岗位名称</label><input id="te-role" class="input" value="${esc(x.role_title)}"></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="updateTemplate('${x.template_id}')">保存修改</button>`)};
window.updateTemplate=async id=>{await api(`/api/v1/templates/${id}`,{method:'PATCH',body:JSON.stringify({name:$('#te-name').value,role_title:$('#te-role').value})});closeModal();toast('模板已更新');await templatesPage()};
window.applyTemplate=async id=>{await ensureProjects();if(!state.projects.length)return toast('请先创建招聘项目',true);modal('应用模板到项目',`<div class="field"><label>目标项目</label><select id="ta-project" class="select">${projectOptions()}</select></div><p class="subtle">默认使用 merge，仅补充尚不存在的 Criteria，不覆盖当前编辑内容。</p>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="confirmApplyTemplate('${id}')">应用模板</button>`)};
window.confirmApplyTemplate=async id=>{const pid=$('#ta-project').value;await api(`/api/v1/templates/${id}/apply/${pid}`,{method:'POST',body:JSON.stringify({mode:'merge'})});closeModal();toast('模板已应用到项目标准草案')};
window.saveCurrentAsTemplate=async()=>{await ensureProjects();if(!state.projects.length)return toast('没有可保存的项目',true);modal('从当前项目保存模板',`<div class="field"><label>项目</label><select id="ts-project" class="select">${projectOptions()}</select></div><div class="field" style="margin-top:10px"><label>模板名称</label><input id="ts-name" class="input" placeholder="例如：产品经理标准模板"></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="confirmSaveCurrentTemplate()">保存</button>`)};
window.confirmSaveCurrentTemplate=async()=>{const pid=$('#ts-project').value;await api(`/api/v1/projects/${pid}/templates/from-current`,{method:'POST',body:JSON.stringify({name:$('#ts-name').value})});closeModal();toast('已从当前项目保存模板');await templatesPage()};
window.deleteTemplate=async id=>{if(confirm('删除该模板？')){await api(`/api/v1/templates/${id}`,{method:'DELETE'});await templatesPage()}};
async function knowledgePage(){await ensureProjects();const s=await api('/api/v1/knowledge/status');$('#content').innerHTML=head('知识库','知识不仅用于检索，也可以把岗位/能力建议直接送入当前项目的标准草案。')+`<div class="grid kpi" style="grid-template-columns:repeat(5,1fr)">${s.databases.map(x=>`<div class="kpi-card"><div class="kpi-label">${esc(x.name)}</div><div class="kpi-value" style="font-size:18px">${x.available?'可用':'缺失'}</div><div class="kpi-note">${x.available?`${(x.size_bytes/1024/1024).toFixed(1)} MB`:'未装配'}</div></div>`).join('')}</div><section class="panel"><div class="panel-head"><h2>知识检索与应用</h2></div><div class="panel-body"><div class="searchbar"><input id="k-q" class="input" placeholder="岗位、能力、市场关键词"><button class="btn primary" onclick="knowledgeSearch()">搜索</button></div><div id="k-results" style="margin-top:14px"><div class="empty">输入关键词开始检索。</div></div></div></section>`}
window.knowledgeSearch=async()=>{try{const d=await api(`/api/v1/knowledge/search?q=${encodeURIComponent($('#k-q').value)}&limit=20`);state.knowledgeResults=d.results||[];$('#k-results').innerHTML=d.results.length?`<div class="quick-list">${d.results.map((x,i)=>`<div class="quick-item"><div><div class="quick-title">${esc(x.title)}</div><div class="quick-note">${esc(x.database)} · ${esc(x.detail)}</div></div><button class="btn small primary" onclick="applyKnowledge(${i})">应用到项目标准草案</button></div>`).join('')}</div>`:'<div class="empty">没有找到匹配结果。</div>'}catch(e){toast(e.message,true)}};
window.applyKnowledge=async i=>{await ensureProjects();if(!state.projects.length)return toast('请先创建招聘项目',true);const x=state.knowledgeResults[i];modal('应用知识建议',`<div class="field"><label>目标项目</label><select id="ka-project" class="select">${projectOptions()}</select></div><div class="field" style="margin-top:10px"><label>Criterion 名称</label><input id="ka-name" class="input" value="${esc(x.title)}"></div><label class="check"><input id="ka-critical" type="checkbox"> 设为决策关键条件</label>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="confirmApplyKnowledge(${i})">应用</button>`)};
window.confirmApplyKnowledge=async i=>{const x=state.knowledgeResults[i];const pid=$('#ka-project').value;await api(`/api/v1/projects/${pid}/knowledge/apply`,{method:'POST',body:JSON.stringify({result:x,criterion_name:$('#ka-name').value,decision_critical:$('#ka-critical').checked,verification_required:true})});closeModal();toast('知识建议已应用到项目标准草案')};
async function tasksPage(){const qs=new URLSearchParams({limit:String(state.taskLimit),offset:String(state.taskPage*state.taskLimit)});if(state.taskStatus)qs.set('status',state.taskStatus);if(state.taskType)qs.set('type',state.taskType);const d=await api(`/api/v1/tasks?${qs.toString()}`);const pages=Math.max(1,Math.ceil(d.total/state.taskLimit));$('#content').innerHTML=head('后台任务','AI / OCR / ASR / 批量导入任务的状态、尝试次数、耗时、错误和恢复入口。',`<button class="btn" onclick="tasksPage()">刷新</button>`)+`<section class="panel"><div class="panel-body"><div class="searchbar"><div class="field"><label>状态筛选</label><select id="task-status" class="select"><option value="">全部</option>${['running','waiting_provider','failed','partial','succeeded','cancelled'].map(v=>`<option value="${v}" ${state.taskStatus===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="field"><label>类型筛选</label><select id="task-type" class="select"><option value="">全部</option>${['evidence_extract','ocr','ocr_pdf','asr','batch_candidate_intake'].map(v=>`<option value="${v}" ${state.taskType===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="actions" style="align-self:end"><button class="btn primary" onclick="applyTaskFilters()">应用筛选</button></div></div></div><div class="table-wrap"><table class="table"><thead><tr><th>任务</th><th>类型</th><th>状态</th><th>进度</th><th>尝试次数</th><th>耗时</th><th>结果 / 错误</th><th>创建</th><th></th></tr></thead><tbody>${d.tasks.length?d.tasks.map(x=>`<tr><td class="mono">${esc(x.task_id.slice(0,8))}…</td><td>${esc(x.type)}</td><td><span class="status ${statusClass(x.status)}">${esc(x.status)}</span></td><td>${x.progress_current}/${x.progress_total}</td><td>${x.attempt_count||0}</td><td>${x.duration_ms==null?'—':`${x.duration_ms} ms`}</td><td class="ellipsis">${esc(x.error_message||(Object.keys(x.result||{}).length?JSON.stringify(x.result):'—'))}</td><td>${new Date(x.created_at).toLocaleString()}</td><td class="right">${['failed','waiting_provider'].includes(x.status)&&['ocr','ocr_pdf','asr','evidence_extract'].includes(x.type)?`<button class="btn small primary" onclick="retryTask('${x.task_id}')">重试</button>`:''} ${!['succeeded','cancelled'].includes(x.status)?`<button class="btn small" onclick="cancelTask('${x.task_id}')">取消</button>`:''}</td></tr>`).join(''):'<tr><td colspan="9"><div class="empty"><strong>暂无符合条件的后台任务</strong>调整筛选条件，或执行 AI / OCR / ASR / 批量导入。</div></td></tr>'}</tbody></table></div><div class="actions" style="justify-content:flex-end;padding:12px"><button class="btn small" ${state.taskPage<=0?'disabled':''} onclick="taskPage(-1)">上一页</button><span class="subtle">第 ${state.taskPage+1} / ${pages} 页，共 ${d.total} 项</span><button class="btn small" ${(state.taskPage+1)>=pages?'disabled':''} onclick="taskPage(1)">下一页</button></div></section>`};window.applyTaskFilters=()=>{state.taskStatus=$('#task-status')?.value||'';state.taskType=$('#task-type')?.value||'';state.taskPage=0;tasksPage()};window.taskPage=delta=>{state.taskPage=Math.max(0,state.taskPage+delta);tasksPage()};window.retryTask=async id=>{try{const r=await api(`/api/v1/tasks/${id}/retry`,{method:'POST'});toast(`任务状态：${r.status}`);await tasksPage()}catch(e){toast(e.message,true)}};window.cancelTask=async id=>{await api(`/api/v1/tasks/${id}/cancel`,{method:'POST'});toast('任务已取消');await tasksPage()};
async function settingsPage(){const [p,b,d]=await Promise.all([api('/api/v1/settings/providers'),api('/api/v1/system/backups'),api('/api/v1/system/diagnostics')]);state.providers=p;const dbOk=d.database?.quick_check==='ok';const blobOk=(d.storage?.missing_source_blobs||0)===0;$('#content').innerHTML=head('设置','配置文本 AI、OCR、ASR，并管理本地备份、运行健康和诊断。')+settingsNavHtml()+`<div class="three">${[['text_ai','文本 AI','DeepSeek / OpenAI-compatible：JD、材料事实提取、复评辅助'],['ocr','OCR','扫描简历、图片、image-only PDF 文字识别'],['asr','ASR','电话筛选、面试录音与视频音轨转写']].map(([k,t,sub])=>providerCard(k,t,sub,p.profiles[k])).join('')}</div><div class="grid kpi" style="margin-top:16px"><div class="kpi-card"><div class="kpi-label">数据库健康</div><div class="kpi-value">${dbOk?'OK':'异常'}</div><div class="kpi-note">SQLite quick_check: ${esc(d.database?.quick_check||'unknown')}</div></div><div class="kpi-card"><div class="kpi-label">Blob 完整性</div><div class="kpi-value">${blobOk?'OK':d.storage.missing_source_blobs}</div><div class="kpi-note">${d.storage?.blob_files||0} 个文件 · ${((d.storage?.blob_bytes||0)/1024/1024).toFixed(1)} MB</div></div><div class="kpi-card"><div class="kpi-label">开放任务</div><div class="kpi-value">${d.tasks?.open||0}</div><div class="kpi-note">${esc(JSON.stringify(d.tasks?.by_status||{}))}</div></div><div class="kpi-card"><div class="kpi-label">数据目录</div><div class="kpi-value">${((d.storage?.data_bytes||0)/1024/1024).toFixed(1)} MB</div><div class="kpi-note">待恢复：${d.pending_restore?'是':'否'}</div></div></div><div class="two" style="margin-top:16px"><section class="panel"><div class="panel-head"><h2>备份与恢复</h2><button class="btn primary" onclick="createBackup()">创建一致性备份</button></div><div class="panel-body"><p class="subtle">恢复不会在运行中的数据库上覆盖文件。选择恢复后，会在下次启动、数据库打开前执行。</p><div id="backup-list">${b.backups.length?b.backups.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.filename)}</div><div class="quick-note">${(x.size_bytes/1024/1024).toFixed(2)} MB</div></div><div class="actions"><a class="btn small" href="/api/v1/system/backups/${encodeURIComponent(x.filename)}">下载</a><button class="btn small danger" onclick="scheduleRestore('${esc(x.filename)}')">下次启动恢复</button></div></div>`).join(''):'<div class="empty">暂无备份</div>'}</div></div></section><section class="panel"><div class="panel-head"><h2>运行诊断</h2><button class="btn" onclick="settingsPage()">刷新</button></div><div class="panel-body"><div class="quick-list"><div class="quick-item"><span>版本</span><strong>${esc(d.version)}</strong></div><div class="quick-item"><span>Schema</span><strong>${esc(d.schema_revision)}</strong></div><div class="quick-item"><span>项目 / 候选人 / Source / Claim</span><strong>${d.counts.projects} / ${d.counts.candidates} / ${d.counts.sources} / ${d.counts.claims}</strong></div></div><div class="divider"></div><div class="actions"><button class="btn" onclick='showDiagnostics(${JSON.stringify(JSON.stringify(d)).replace(/'/g,"&#39;")})'>查看完整诊断</button><a class="btn primary" href="/api/v1/system/diagnostics/export" download>导出隐私安全诊断包</a></div></div></section></div>`}
function providerCard(k,title,sub,p){return `<div class="provider-card"><div class="provider-title"><div><h3>${title}</h3><div class="provider-sub">${sub}</div></div><span class="status ${p.api_key_configured?'good':'warn'}">${p.api_key_configured?'Key 已配置':'未配置 Key'}</span></div><div class="field"><label>Provider</label><select id="p-${k}-type" class="select"><option value="deepseek" ${p.provider_type==='deepseek'?'selected':''}>DeepSeek</option><option value="openai_compatible" ${p.provider_type==='openai_compatible'?'selected':''}>OpenAI-compatible</option></select></div><div class="field" style="margin-top:8px"><label>模型</label><input id="p-${k}-model" class="input" value="${esc(p.model)}"></div><div class="field" style="margin-top:8px"><label>Base URL</label><input id="p-${k}-url" class="input" value="${esc(p.base_url)}"></div><div class="field" style="margin-top:8px"><label>API Key（留空表示不修改）</label><input id="p-${k}-key" class="input" type="password" autocomplete="off"></div><div class="actions" style="margin-top:12px"><button class="btn primary" onclick="saveProvider('${k}')">保存</button><button class="btn" onclick="testProvider('${k}')">真实能力测试</button></div></div>`}
window.saveProvider=async k=>{try{const key=$(`#p-${k}-key`).value;const body={provider_type:$(`#p-${k}-type`).value,model:$(`#p-${k}-model`).value,base_url:$(`#p-${k}-url`).value,reasoning_effort:'medium'};if(key)body.api_key=key;await api(`/api/v1/settings/providers/${k}`,{method:'PATCH',body:JSON.stringify(body)});toast(`${k} 配置已保存`);await settingsPage()}catch(e){toast(e.message,true)}};window.testProvider=async k=>{try{toast('正在执行真实能力测试…');const r=await api(`/api/v1/settings/providers/${k}/test`,{method:'POST'});toast(`${k} ${r.model} 测试通过`)}catch(e){toast(e.message,true)}};
window.createBackup=async()=>{try{const r=await api('/api/v1/system/backups',{method:'POST'});toast(`备份已创建：${r.filename}`);await settingsPage()}catch(e){toast(e.message,true)}};window.scheduleRestore=async name=>{if(!confirm(`计划在下次启动恢复 ${name}？\n\n重启时数据库会被该备份覆盖：排程之后录入或修改的候选人、证据与判断可能全部丢失。\n如需保留，请先取消计划或先创建新的备份。`))return;try{await api(`/api/v1/system/backups/${encodeURIComponent(name)}/restore`,{method:'POST'});toast('已计划恢复；重启前请勿继续录入重要数据');await refreshRestoreStatus();if(state.page==='settings')await settingsPage();}catch(e){toast(e.message,true)}};window.showDiagnostics=s=>modal('完整诊断',`<div class="codebox">${esc(JSON.stringify(JSON.parse(s),null,2))}</div>`);

















window.openContactWorkbench=async()=>{try{const q=await api(`/api/v1/projects/${state.projectId}/contact-queue?limit=100&offset=0`);modal('联系工作台',`<p class="subtle" data-priority-semantics="contact_execution_priority_not_hiring_rank">联系优先级只用于执行安排，不是录用排序。</p><table class="table"><thead><tr><th>候选人</th><th>优先级</th><th>状态</th><th>下次联系</th><th>负责人</th><th></th></tr></thead><tbody>${q.candidates.map(x=>`<tr><td>${esc(x.display_name)}<div class="subtle">${esc(x.phone||x.email||'暂无已确认联系方式')}</div></td><td>${esc(x.priority)}</td><td>${esc(x.contact_status)}</td><td>${esc(x.next_contact_at||'未安排')}</td><td>${esc(x.owner||'未指定')}</td><td><button class="btn small" onclick="openActionPlan('${x.candidate_id}')">编辑行动</button><button class="btn small" onclick="openPhoneScript('${x.candidate_id}')">电话脚本</button></td></tr>`).join('')}</tbody></table>`,`<button class="btn" onclick="closeModal()">关闭</button>`)}catch(e){toast(e.message,true)}};
window.openActionPlan=async cid=>{try{const x=await api(`/api/v1/candidates/${cid}/action-plan`);modal('候选人行动计划',`<div class="form-grid"><div class="field"><label>联系优先级</label><select id="ap-priority" class="select">${['today','high','normal','low'].map(v=>`<option value="${v}" ${x.priority===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="field"><label>负责人</label><input id="ap-owner" class="input" value="${esc(x.owner||'')}"></div><div class="field"><label>联系状态</label><select id="ap-status" class="select">${['to_contact','attempted','callback','contacted','not_interested','waiting_material','done'].map(v=>`<option value="${v}" ${x.contact_status===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="field"><label>下次联系时间</label><input id="ap-next" class="input" value="${esc(x.next_contact_at||'')}"></div><div class="field full"><label>原因 / 下一步</label><textarea id="ap-reason" class="textarea">${esc(x.reason||'')}</textarea></div></div>`,`<button class="btn" onclick="closeModal()">取消</button><button class="btn primary" onclick="saveActionPlan('${cid}')">保存</button>`)}catch(e){toast(e.message,true)}};
window.saveActionPlan=async cid=>{try{await api(`/api/v1/candidates/${cid}/action-plan`,{method:'PATCH',body:JSON.stringify({priority:$('#ap-priority').value,owner:$('#ap-owner').value,contact_status:$('#ap-status').value,next_contact_at:$('#ap-next').value,reason:$('#ap-reason').value,actor:'human'})});closeModal();toast('行动计划已保存');if(state.candidateId===cid)await candidateDrawer(cid);else await openContactWorkbench()}catch(e){toast(e.message,true)}};
window.openPhoneScript=async cid=>{try{const r=await api(`/api/v1/candidates/${cid}/phone-script`);modal('电话脚本 / 核实思路',`<p class="subtle">${esc(r.note)}</p><div class="quick-list">${r.questions.map(x=>`<div class="quick-item"><div><div class="quick-title">${esc(x.question)}</div><div class="quick-note">为什么问：${esc(x.purpose)}</div></div></div>`).join('')}</div>`,`<button class="btn" onclick="closeModal()">关闭</button>`)}catch(e){toast(e.message,true)}};
function scorecardHistoryHtml(list,ev){
  if(!list||!list.length)return '<div class="empty">尚无评价者提交 Scorecard</div>';
  const snap={};(ev&&ev.metadata&&ev.metadata.criteria_snapshot||[]).forEach(c=>{if(c&&c.criterion_key)snap[c.criterion_key]=c.name||''});
  const order=[],seen={};
  list.forEach(s=>(s.feedback||[]).forEach(f=>{const k=f.criterion_key||'';if(!(k in seen)){seen[k]=order.length+1;order.push(k)}}));
  const label=k=>snap[k]||`历史标准 ${seen[k]||order.length+1}`;
  const ratings={strong:'强',acceptable:'可接受',concern:'有顾虑',unknown:'无法判断'};
  return list.map(s=>`<div class="scorecard-history"><div class="scorecard-head"><strong>${esc(s.evaluator)}</strong><span class="status ${s.state==='submitted'?'good':''}">${esc(s.state)}</span>${s.recommendation?`<span class="subtle">总体建议：${esc(s.recommendation)}</span>`:''}</div>${(s.feedback||[]).length?`<div class="table-wrap"><table class="table compact"><thead><tr><th>标准</th><th>评价</th><th>行为观察</th><th>支持证据</th><th>反对证据</th><th>逐项建议</th></tr></thead><tbody>${s.feedback.map(f=>`<tr><td><strong>${esc(label(f.criterion_key))}</strong></td><td>${esc(ratings[f.rating]||f.rating||'—')}</td><td>${esc(f.observation||'—')}</td><td>${esc(f.supporting_evidence||'—')}</td><td>${esc(f.counter_evidence||'—')}</td><td>${esc(f.recommendation||'—')}</td></tr>`).join('')}</tbody></table></div>`:'<div class="subtle">该评分没有逐标准明细</div>'}</div>`).join('');
}
window.openScorecards=async(cid,eid)=>{
  // Delayed Core reads must not reopen an old Scorecard over another candidate
  // or overwrite a newer Scorecard request in the same workspace.
  const requestedProjectId=state.projectId,requestedCandidateId=state.candidateId;
  const requestedModalGeneration=state.modalGeneration||0;
  const requestSeq=(state.scorecardOpenSeq||0)+1;
  state.scorecardOpenSeq=requestSeq;
  const stillCurrent=()=>state.page==='projects'&&state.projectId===requestedProjectId
    &&state.candidateId===requestedCandidateId&&state.scorecardOpenSeq===requestSeq
    &&(state.modalGeneration||0)===requestedModalGeneration;
  try{
    // The selected project is UI state, not proof of candidate ownership.
    // Verify it against Core before any candidate-scoped Scorecard GET.
    if(!cid||!state.projectId)throw uiError('缺少候选人或项目上下文，已阻止读取面评');
    // A valid event belonging to the same project is not permission to display
    // or submit its Scorecard while another candidate's drawer is selected.
    if(requestedCandidateId&&requestedCandidateId!==cid)
      throw uiError('当前工作区候选人与面评目标不一致，已阻止读取');
    const owner=await api(`/api/v1/candidates/${cid}/summary`);
    if(!stillCurrent())return;
    if(!owner||!owner.project_id||owner.project_id!==requestedProjectId){
      if(!owner||!owner.project_id)throw uiError('无法确认候选人所属项目，已阻止读取面评');
      // Capture a return route, but never restore a mismatched candidate drawer.
      const origin={projectId:state.projectId,projectTab:state.projectTab,
        candidateView:state.candidateView,candidateQuery:state.candidateQuery,
        candidateArchive:state.candidateArchive,candidateMaterial:state.candidateMaterial,
        candidateStage:state.candidateStage,candidatePage:state.candidatePage};
      modal('独立 Interview Scorecard',
        '<div class="notice danger" role="alert"><strong>候选人所属项目与当前项目不一致，已阻止读取</strong><div class="subtle" style="margin-top:6px">本次未读取评分或写入数据。可前往候选人所属项目，重新核对原面试记录。</div></div>',
        '<button class="btn" onclick="closeModal()">关闭</button><button class="btn primary" id="sc-open-owner">前往所属项目并查看本次面评</button>');
      $('#sc-open-owner').addEventListener('click',async()=>{
        try{
          // Recheck ownership before switching workspaces; never trust a stale UI hint.
          const fresh=await api(`/api/v1/candidates/${cid}/summary`);
          if(!fresh||fresh.project_id!==owner.project_id)throw uiError('候选人所属项目已变化，请刷新后重新查找');
          closeModal();
          await window.openProject(owner.project_id);
          await window.setProjectTab('candidates');
          await window.openCandidate(cid);
          await window.setCandidateSection('process');
          // This explicit recovery action opens the original event, not just a candidate list.
          await window.openScorecards(cid,eid);
          // Keep the operator's original project/filter route available after
          // recovery, without restoring an unverified candidate identity.
          const footer=$('#modal-root .modal-foot');
          if(footer){
            const back=document.createElement('button');
            back.type='button';back.className='btn';back.textContent='返回原项目';
            back.addEventListener('click',async()=>{
              try{
                closeModal();
                state.candidateQuery=origin.candidateQuery;
                state.candidateArchive=origin.candidateArchive;
                state.candidateMaterial=origin.candidateMaterial;
                state.candidateStage=origin.candidateStage;
                state.candidatePage=origin.candidatePage;
                await window.openProject(origin.projectId);
                await window.setProjectTab(origin.projectTab);
                state.candidateView=origin.candidateView;
                if(origin.projectTab==='candidates'&&origin.candidateView!=='all')await projectWorkspace();
              }catch(e){blockedNotice('无法返回原项目',e.message||'原项目暂不可访问','请从招聘项目列表重新进入；本次没有写入面评。')}
            });
            footer.prepend(back);
          }
        }catch(e){blockedNotice('无法打开候选人所属项目',e.message||'项目导航失败','请从招聘项目列表重新查找该候选人；本次没有写入面评。')}
      });
      return;
    }
    let ev=null;
    try{ev=await eventContext(cid,eid)}
    catch(e){if(!stillCurrent())return;blockedNotice('独立 Interview Scorecard',e.message||'无法读取该面试记录','未读取该面试的任何反馈，也未写入数据。');return}
    if(!stillCurrent())return;
    const r=await api(`/api/v1/projects/${requestedProjectId}/candidates/${cid}/events/${eid}/scorecards`);
    if(!stillCurrent())return;
    const existing=scorecardHistoryHtml(r.scorecards,ev);
    /* Ownership is enough to READ history; only a new write needs the pinned
       revision. A changed Published revision makes the record read-only, not
       invisible. */
    let ctx=null,readonly='';
    try{ctx=await eventWriteContext(cid,eid,ev)}catch(e){readonly=e.message||'该记录当前不可编辑'}
    if(!stillCurrent())return;
    if(readonly){
      modal('独立 Interview Scorecard',`${existing}<div class="notice" role="status" style="margin-top:12px"><strong>只读</strong><div class="subtle" style="margin-top:6px">${esc(readonly)}</div><div class="subtle" style="margin-top:6px">历史评分仍可查看；本次不会新增或修改任何记录。</div></div>`,`<button class="btn" onclick="closeModal()">关闭</button>`);
      return;
    }
    modal('独立 Interview Scorecard',`${existing}<div class="divider"></div><div class="form-grid"><div class="field"><label>评价者</label><input id="sc-evaluator" class="input"></div><div class="field"><label>总体建议</label><input id="sc-rec" class="input" placeholder="advance / hold / reject"></div></div><div id="sc-criteria" style="margin-top:12px">${criterionFeedbackRows(ctx.keys,ctx.names,ctx.definitions)}</div><p class="subtle">不同评价者意见独立保存；系统不会自动平均成总分。</p>`,`<button class="btn" onclick="closeModal()">关闭</button><button class="btn primary" onclick="saveScorecard('${cid}','${eid}')">提交并锁定</button>`)
    // Bind the visible form to its Core candidate/event/project identity.
    // A stale callback must not submit observations to another interview.
    const scorecardModal=$('#modal-root .modal');
    if(scorecardModal){
      scorecardModal.dataset.scorecardCandidateId=cid;
      scorecardModal.dataset.scorecardEventId=eid;
      scorecardModal.dataset.scorecardProjectId=requestedProjectId;
      scorecardModal.dataset.scorecardWorkspaceCandidateId=requestedCandidateId||'';
    }
  }catch(e){if(!stillCurrent())return;blockedNotice('独立 Interview Scorecard',e.message||'无法读取该面试记录','请从正确项目的候选人工作台重新打开；本次未提交任何评分。')}
};


window.saveScorecard=async(cid,eid)=>{
  try{
    const formModal=$('#modal-root .modal'),projectId=state.projectId;
    if(!formModal||state.page!=='projects'
       ||formModal.dataset.scorecardCandidateId!==cid
       ||formModal.dataset.scorecardEventId!==eid
       ||formModal.dataset.scorecardProjectId!==projectId
       ||formModal.dataset.scorecardWorkspaceCandidateId!==(state.candidateId||''))
      throw uiError('面评窗口与目标候选人/事件不一致，已阻止提交');
    // Snapshot the actual visible form BEFORE asynchronous Core reads.
    const evaluator=(formModal.querySelector('#sc-evaluator')?.value||'').trim();
    if(!evaluator)throw uiError('请填写评价者');
    const feedback=collectCriterionFeedback('#sc-criteria');
    const recommendation=formModal.querySelector('#sc-rec')?.value||'';
    if(!feedback.length)throw uiError('请至少填写一条标准评价');
    const ctx=await eventWriteContext(cid,eid);
    if($('#modal-root .modal')!==formModal||state.page!=='projects'
       ||state.projectId!==projectId||ctx.pid!==projectId
       ||formModal.dataset.scorecardWorkspaceCandidateId!==(state.candidateId||''))
      throw uiError('面评窗口或项目已变化，请重新打开后提交');
    const allowed=new Set(ctx.keys);
    if(feedback.some(f=>!f.criterion_key||!allowed.has(f.criterion_key)))
      throw uiError('评价与面试原始标准不一致，已阻止提交');
    await api(`/api/v1/events/${eid}/scorecards`,{method:'POST',body:JSON.stringify({evaluator,feedback,recommendation,submit:true})});
    // The POST can finish after the operator opens a different dialog. Keep
    // that newer unsaved form intact; only close the submitted Scorecard itself.
    if($('#modal-root .modal')===formModal&&state.page==='projects'
       &&state.projectId===projectId
       &&formModal.dataset.scorecardWorkspaceCandidateId===(state.candidateId||'')){
      closeModal();toast('Scorecard 已独立提交并锁定');
    }else{
      toast('原面评已提交，当前操作窗口保持不变');
    }
  }catch(e){toast(e.message||'提交失败',true)}
};
function candidateBriefHtml(r){const contact=r.contact||{},plan=r.action_plan||{},criteria=r.criteria||[],v=r.version_context||{};return `<div class="business-strip"><div><small>候选人</small><strong>${esc(r.display_name||'—')}</strong></div><div><small>当前阶段</small><strong>${esc(stageLabel(r.pipeline_stage))}</strong></div><div><small>联系方式</small><strong>${contact.user_confirmed?'已人工确认':'待确认'}</strong></div></div><div class="two"><section><h3>联系方式</h3><div class="quick-list"><div class="quick-item"><span>电话</span><strong>${esc(contact.phone||'未录入')}</strong></div><div class="quick-item"><span>邮箱</span><strong>${esc(contact.email||'未录入')}</strong></div></div></section><section><h3>当前行动计划</h3>${plan?`<div class="quick-list"><div class="quick-item"><span>优先级 / 负责人</span><strong>${esc(plan.priority||'normal')} · ${esc(plan.owner||'未指定')}</strong></div><div class="quick-item"><span>联系状态</span><strong>${esc(plan.contact_status||'to_contact')}</strong></div><div class="quick-item"><span>下次联系</span><strong>${esc(plan.next_contact_at||'未安排')}</strong></div></div><p class="subtle">${esc(plan.reason||'')}</p>`:'<div class="empty">暂无行动计划</div>'}</section></div><div class="divider"></div><h3>评价摘要</h3>${criteria.length?`<table class="table"><thead><tr><th>标准</th><th>判断</th><th>证据</th><th>理由 / 缺口</th></tr></thead><tbody>${criteria.map(x=>`<tr><td>${esc(x.criterion_key)}</td><td>${esc(x.status)}</td><td>${esc(x.evidence_level)}</td><td>${esc(x.reason||x.gap||'—')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">当前没有评价结果</div>'}<details style="margin-top:12px"><summary>审计上下文</summary><div class="codebox" style="margin-top:8px">${esc(JSON.stringify(v,null,2))}</div></details>`}
function handoffHtml(r){const rows=r.candidates||[];return `<div class="business-strip"><div><small>项目</small><strong>${esc(r.project_title||'—')}</strong></div><div><small>候选人</small><strong>${fmt(rows.length)}</strong></div><div><small>生成时间</small><strong style="font-size:14px">${r.generated_at?new Date(r.generated_at).toLocaleString():'—'}</strong></div></div><p class="subtle">交接视图聚焦阶段、联系方式、下一步和当前评价；完整版本上下文仍保留在下载的 JSON 中。</p>${rows.length?`<div class="quick-list">${rows.map(x=>{const contact=x.contact||{},plan=x.action_plan||{},criteria=x.criteria||[];const gaps=criteria.filter(c=>c.status==='missing'||c.status==='partial'||c.status==='conflict').length;return `<div class="quick-item" style="align-items:flex-start"><div style="flex:1"><div class="quick-title">${esc(x.display_name)} · ${esc(stageLabel(x.pipeline_stage))}</div><div class="quick-note">${esc(contact.phone||contact.email||'暂无联系方式')} · ${contact.user_confirmed?'联系方式已确认':'联系方式待确认'}</div><div class="quick-note">下一步：${esc(plan?.reason||plan?.contact_status||'未设置行动计划')} · 评价项 ${criteria.length} · 待核实/冲突 ${gaps}</div></div><button class="btn small" onclick="closeModal();openCandidate('${x.candidate_id}')">打开候选人</button></div>`}).join('')}</div>`:'<div class="empty">项目暂无候选人</div>'}`}
window.openCandidateBrief=async cid=>{try{const r=await api(`/api/v1/candidates/${cid}/brief`);modal('候选人简报',candidateBriefHtml(r),`<button class="btn" onclick="closeModal()">关闭</button><button class="btn primary" onclick="closeModal();openActionPlan('${cid}')">编辑下一步</button>`)}catch(e){toast(e.message,true)}};
window.openHandoff=async()=>{try{const r=await api(`/api/v1/projects/${state.projectId}/handoff`);state.handoffPayload=r;modal('项目交接摘要',handoffHtml(r),`<button class="btn" onclick="closeModal()">关闭</button><button class="btn primary" onclick="downloadHandoff()">下载完整交接 JSON</button>`)}catch(e){toast(e.message,true)}};
window.downloadHandoff=()=>{if(!state.handoffPayload)return;const raw=JSON.stringify(state.handoffPayload,null,2),blob=new Blob([raw],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`SRW_handoff_${state.projectId||'project'}.json`;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url)};

const jobSetup = createJobSetupFeature({
  api, $, esc, modal, toast, fmt, state, projectWorkspace, refreshProjects,
  closeModal: () => window.closeModal(), forkDraft: () => window.forkDraft(),
  collectAssessmentStages, defaultAssessmentStages, head,
});
const {criteriaTab, collectCriteria, syncJobSetupDraftFromDom, jobSetupProgress,
       renderJobSetupWizard, criterionRow, criterionStageKeys, ensureCriterionKey} = jobSetup;
window.addCriterionRow = jobSetup.addCriterionRow;
window.applyJobSetupSuggestions = jobSetup.applyJobSetupSuggestions;
window.jobSetupMove = jobSetup.jobSetupMove;
window.openJobSetup = jobSetup.openJobSetup;
window.publishCriteria = jobSetup.publishCriteria;
window.saveCriteria = jobSetup.saveCriteria;
window.saveJobSetup = jobSetup.saveJobSetup;
window.suggestJobSetup = jobSetup.suggestJobSetup;


function restoreBannerHtml(){
  const status=state.restoreStatus||'unknown';
  if(status==='clear')return '';
  if(status==='pending'){
    return `<div class="restore-banner" id="restore-banner"><div class="restore-banner-title">已排程下次启动恢复</div><div class="restore-banner-body">重启时会用所选备份覆盖当前数据库，<strong>排程之后录入或修改的内容可能全部丢失</strong>。</div><div class="actions"><button class="btn small danger" onclick="cancelPendingRestore()">取消待恢复计划</button><button class="btn small" onclick="go('settings')">查看设置</button></div></div>`;
  }
  return `<div class="restore-banner" id="restore-banner"><div class="restore-banner-title">无法确认恢复状态</div><div class="restore-banner-body">诊断接口不可用或返回异常，<strong>不要假定当前没有待恢复计划</strong>。</div><div class="actions"><button class="btn small" onclick="refreshRestoreStatus()">重试</button></div></div>`;
}
function paintRestoreBanner(){
  const host=$('#restore-banner-host'); if(!host)return;
  host.innerHTML=restoreBannerHtml();
  if(!$('#restore-banner'))host.innerHTML='';
}
async function refreshRestoreStatus(){
  // Fail-closed classification. Only a literal boolean may clear the warning:
  // a 200 that omits the field, returns null, or sends a truthy string must not
  // be read as "safe", because "clear" hides the one alert protecting the user
  // from a restart that overwrites their recent work.
  let next='unknown';
  try{
    const d=await api('/api/v1/system/diagnostics');
    if(d&&d.pending_restore===true)next='pending';
    else if(d&&d.pending_restore===false)next='clear';
  }catch(e){ next='unknown'; }
  state.restoreStatus=next;
  paintRestoreBanner();
}
window.cancelPendingRestore=async()=>{
  if(!confirm('取消待恢复计划？数据库不会被覆盖，当前改动会保留。'))return;
  try{
    await api('/api/v1/system/restore/cancel',{method:'POST'});
    toast('已取消待恢复计划');
    await refreshRestoreStatus();
    if(state.page==='settings')await settingsPage();
  }catch(e){toast(e.message,true)}
};

init();

