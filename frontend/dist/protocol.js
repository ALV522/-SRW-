/* Protocol criteria editing domain — extracted from app.js (ADR-0002 domain split).
 * Loaded after shared.js; infra, state and core helpers resolve through window. */
const {state,materialDrafts,api,esc,fmt,toast,modal,modalWide,closeModal,$}=window;
window.criterionRow=criterionRow;window.criteriaTab=criteriaTab;

const defaultAssessmentStages=[
  {stage_key:'resume',name:'简历筛选',criteria:[]},
  {stage_key:'phone_screen',name:'电话筛选',criteria:[]},
  {stage_key:'interview',name:'面试',criteria:[]}
];

function criterionStageKeys(key){
  if(!key)return [];
  return (state.criteriaStageDefs||[]).filter(s=>(s.criteria||[]).includes(key)).map(s=>s.stage_key)
}

async function criteriaTab(el,p){
  const d=await api(`/api/v1/projects/${state.projectId}/protocol-workspace`);
  const active=d.draft||d.current||{};
  state.criteriaDraftToken=active.token||'';
  const criteria=active.criteria||[];
  state.criteriaOriginalByKey=Object.fromEntries(criteria.filter(x=>x&&typeof x==='object').map(x=>[String(x.criterion_key||x.key||''),{...x}]).filter(([k])=>k));
  state.criteriaBrief={...(active.brief||{})};
  state.criteriaRecruitmentContext={...(active.recruitment_context||{})};
  state.criteriaDecisionPolicy={...(active.decision_policy||{})};
  state.criteriaStageDefs=(active.assessment_stages?.length?active.assessment_stages:defaultAssessmentStages).map(s=>({...s,criteria:[...(s.criteria||[])]}));
  el.innerHTML=`<div class="actions" style="margin-bottom:12px"><button class="btn primary" onclick="openJobSetup()">四步建岗向导</button><button class="btn" onclick="suggestJobSetup()">知识/系统建议</button></div><div class="two criteria-layout"><div><div class="field"><label>岗位名称</label><input id="crit-title" class="input" value="${esc(active.brief?.title||p.protocol_title||'')}"></div><div class="field" style="margin-top:10px"><label>岗位摘要 / JD</label><textarea id="crit-summary" class="textarea">${esc(active.brief?.summary||'')}</textarea></div><div class="divider"></div><div class="panel-head" style="padding:0 0 10px;border:0"><div><h3>评价标准</h3><span class="subtle">权重只在证据闭合后参与诊断性匹配投影；缺失或冲突证据不会按 0 分处理。</span></div><button class="btn small" onclick="addCriterionRow()">＋ 添加标准</button></div><div id="criteria-rows">${criteria.map((x,i)=>criterionRow(x,i,criterionStageKeys(x.criterion_key||x.key||''))).join('')}</div><div class="actions" style="margin-top:12px"><button class="btn primary" onclick="saveCriteria('${d.draft_revision_id||''}')">保存草案</button>${d.draft_revision_id?`<button class="btn" onclick="publishCriteria('${d.draft_revision_id}')">发布当前标准</button>`:`<button class="btn" onclick="forkDraft()">基于当前版本创建新草案</button>`}</div></div><div><div class="provider-card"><h3>标准设计约束</h3><p class="subtle">“必须核实”与“决策关键”会决定 Candidate Workspace 的阻塞项。阶段分配用于说明在哪个招聘环节核实该标准；一个标准可以属于多个阶段。</p><div class="divider"></div><div class="pill-row"><span class="status info">Missing ≠ 0</span><span class="status info">AI ≠ Decision</span><span class="status info">版本可追溯</span><span class="status info">保存 ≠ 发布</span></div></div><div class="provider-card" style="margin-top:12px"><h3>草案完整性</h3><div class="quick-list"><div class="quick-item"><span>建岗上下文</span><strong>${Object.keys(state.criteriaRecruitmentContext).length?'保留':'尚未填写'}</strong></div><div class="quick-item"><span>评价阶段</span><strong>${state.criteriaStageDefs.length} 个</strong></div><div class="quick-item"><span>发布边界</span><strong>必须人工显式发布</strong></div></div></div></div></div>`
}

function criterionRow(x={},i=0,stageKeys=[]){
  const key=x.criterion_key||x.key||'';
  const weight=Number(x.weight??1);
  const stages=(state.criteriaStageDefs?.length?state.criteriaStageDefs:defaultAssessmentStages);
  return `<div class="criterion-card criterion-row" data-i="${i}" data-criterion-key="${esc(key)}"><div class="criterion-card-head"><div><strong>${esc(x.name||'新评价标准')}</strong><span class="mono subtle">${esc(key||'保存时生成稳定 ID')}</span></div><button class="btn small danger" onclick="this.closest('.criterion-row').remove()">删除</button></div><div class="form-grid"><div class="field"><label>标准名称</label><input class="input c-name" value="${esc(x.name||'')}"></div><div class="field"><label>权重</label><input class="input c-weight" type="number" min="0.01" step="0.1" value="${Number.isFinite(weight)&&weight>0?weight:1}"></div><div class="field full"><label>标准定义 / 判断口径</label><textarea class="textarea c-definition" placeholder="说明什么证据可支持“满足 / 部分满足 / 未满足”">${esc(x.definition||'')}</textarea></div><div class="field full"><label>核实问题</label><input class="input c-probe" value="${esc((x.verification_probes||[])[0]||'')}" placeholder="缺证据时，TA / 面试官应该问什么？"></div></div><div class="criterion-stage-box"><small>核实阶段</small><div class="pill-row">${stages.map(s=>`<label class="stage-check"><input type="checkbox" class="c-stage" value="${esc(s.stage_key)}" ${stageKeys.includes(s.stage_key)?'checked':''}> ${esc(s.name||s.stage_key)}</label>`).join('')}</div></div><div class="pill-row" style="margin-top:10px"><label><input type="checkbox" class="c-critical" ${x.decision_critical?'checked':''}> 决策关键</label><label><input type="checkbox" class="c-verify" ${x.verification_required?'checked':''}> 必须核实</label></div></div>`
}

window.addCriterionRow=()=>{
  $('#criteria-rows').insertAdjacentHTML('beforeend',criterionRow({},document.querySelectorAll('.criterion-row').length,[]))
};

function ensureCriterionKey(row){
  let key=(row.dataset.criterionKey||'').trim();
  if(!key){
    key=(globalThis.crypto?.randomUUID?.()||('criterion-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8)));
    row.dataset.criterionKey=key
  }
  return key
}

function collectCriteria(){
  return [...document.querySelectorAll('.criterion-row')].map(r=>{
    const name=r.querySelector('.c-name').value.trim();
    if(!name)return null;
    const weight=Number(r.querySelector('.c-weight').value||1);
    if(!Number.isFinite(weight)||weight<=0)throw new Error(`“${name}”的权重必须大于 0`);
    const criterion_key=ensureCriterionKey(r);
    return {
      ...(state.criteriaOriginalByKey[criterion_key]||{}),
      criterion_key,
      name,
      definition:r.querySelector('.c-definition').value.trim(),
      weight,
      decision_critical:r.querySelector('.c-critical').checked,
      verification_required:r.querySelector('.c-verify').checked,
      verification_probes:[r.querySelector('.c-probe').value.trim()].filter(Boolean)
    }
  }).filter(Boolean)
}

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

window.saveCriteria=async rid=>{
  try{
    if(!rid){toast('请先创建草案',true);return}
    const criteria=collectCriteria();
    const payload={
      brief:{...state.criteriaBrief,title:$('#crit-title').value,summary:$('#crit-summary').value},
      criteria,
      assessment_stages:collectAssessmentStages(criteria),
      decision_policy:{...state.criteriaDecisionPolicy,human_final:true},
      recruitment_context:{...state.criteriaRecruitmentContext}
    };
    const saved=await api(`/api/v1/protocol-revisions/${rid}`,{method:'PATCH',headers:{...(state.criteriaDraftToken?{'If-Match':state.criteriaDraftToken}:{})},body:JSON.stringify({payload,provenance:{ui:'business-convergence11-product-workflow'}})});if(saved&&saved.token)state.criteriaDraftToken=saved.token;
    toast('草案已保存；建岗上下文、阶段分配与决策策略已保留');
    await projectWorkspace()
  }catch(e){toast(e.message,true)}
};

window.publishCriteria=async rid=>{if(!confirm('发布后将成为候选人评价的当前标准，确认发布？'))return;try{const published=await api(`/api/v1/protocol-revisions/${rid}/publish`,{method:'POST',headers:{...(state.criteriaDraftToken?{'If-Match':state.criteriaDraftToken}:{})}});if(published&&published.token)state.criteriaDraftToken=published.token;toast('招聘标准已发布');await refreshProjects();await projectWorkspace()}catch(e){toast(e.message,true)}};
window.forkDraft=async()=>{try{await api(`/api/v1/projects/${state.projectId}/protocol-drafts`,{method:'POST'});toast('已创建新草案');await projectWorkspace()}catch(e){toast(e.message,true)}};
