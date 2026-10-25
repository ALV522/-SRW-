/**
 * Job Setup feature module (R4-2, ADR-0002).
 *
 * The 16 functions below are copied verbatim from app.js. Only their scope source
 * changed: they close over injected dependencies instead of the app module's
 * top-level bindings. No business rule, API path, DOM selector, storage key or
 * user-facing message was edited.
 *
 * Injection notes (approved by Track A):
 * - `state` must be the same live object app.js holds; copying it would freeze the
 *   wizard on a stale project or candidate.
 * - `closeModal` / `forkDraft` arrive as late-bound thunks because in app.js they
 *   are `window.*` property writes and are not hoisted; capturing them by value
 *   early would silently capture undefined and fail only on click.
 */
export function createJobSetupFeature({api, $, esc, modal, closeModal, toast, fmt,
    state, projectWorkspace, refreshProjects, forkDraft, collectAssessmentStages,
    defaultAssessmentStages, head}) {
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
  async function criteriaTab(el,p){
    const d=await api(`/api/v1/projects/${state.projectId}/protocol-workspace`);
    const active=d.draft||d.current||{};
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
  function criterionStageKeys(key){
    if(!key)return [];
    return (state.criteriaStageDefs||[]).filter(s=>(s.criteria||[]).includes(key)).map(s=>s.stage_key)
  }
  function ensureCriterionKey(row){
    let key=(row.dataset.criterionKey||'').trim();
    if(!key){
      key=(globalThis.crypto?.randomUUID?.()||('criterion-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8)));
      row.dataset.criterionKey=key
    }
    return key
  }
  function jobSetupProgress(){return `<div class="wizard-steps">${[['1','岗位'],['2','用工'],['3','协作'],['4','确认']].map(([n,l])=>`<div class="wizard-step ${Number(n)===state.jobSetupStep?'active':Number(n)<state.jobSetupStep?'done':''}"><span>${n}</span><strong>${l}</strong></div>`).join('')}</div>`}
  function renderJobSetupWizard(){
    const x=state.jobSetupDraft||{},step=state.jobSetupStep;
    let body='';
    if(step===1)body=`<div class="wizard-copy"><h3>1. 岗位基本信息</h3><p>先明确招聘对象和编制，不在这一步定义评价结论。</p></div><div class="form-grid"><div class="field"><label>岗位名称</label><input id="js-role" class="input" value="${esc(x.role_title||'')}" placeholder="例如：产品经理"></div><div class="field"><label>Headcount</label><input id="js-headcount" class="input" type="number" min="0" value="${x.headcount??1}"></div><div class="field"><label>地点</label><input id="js-location" class="input" value="${esc(x.location||'')}" placeholder="城市 / 办公地点 / Remote"></div><div class="field"><label>职级</label><input id="js-level" class="input" value="${esc(x.level||'')}" placeholder="例如：P6 / Senior"></div></div>`;
    if(step===2)body=`<div class="wizard-copy"><h3>2. 用工与计划</h3><p>记录业务约束，用于招聘执行和候选人沟通，不自动转化为录用评分。</p></div><div class="form-grid"><div class="field"><label>用工方式</label><input id="js-employment" class="input" value="${esc(x.employment_type||'full_time')}" placeholder="full_time / intern / contract"></div><div class="field"><label>薪酬口径</label><input id="js-comp" class="input" value="${esc(x.compensation||'')}" placeholder="薪酬范围 / 结构 / 口径"></div><div class="field"><label>计划到岗</label><input id="js-start" class="input" type="date" value="${esc(x.target_start_date||'')}"></div></div>`;
    if(step===3)body=`<div class="wizard-copy"><h3>3. 责任人与业务背景</h3><p>把招聘责任、决策协作者和真实业务背景写清楚，后续再拆成评价标准。</p></div><div class="form-grid"><div class="field"><label>招聘负责人</label><input id="js-owner" class="input" value="${esc(x.recruiter_owner||'')}"></div><div class="field"><label>Hiring Manager</label><input id="js-hm" class="input" value="${esc(x.hiring_manager||'')}"></div><div class="field full"><label>JD / 业务背景</label><textarea id="js-jd" class="textarea" style="min-height:180px" placeholder="团队目标、岗位职责、核心业务问题、协作关系等">${esc(x.jd_text||'')}</textarea></div></div>`;
    if(step===4)body=`<div class="wizard-copy"><h3>4. 确认建岗草案</h3><p>此处只保存 Draft。招聘标准仍需在“建岗与标准”页人工检查并显式发布。</p></div><div class="review-grid"><div><small>岗位</small><strong>${esc(x.role_title||'未填写')}</strong><span>${esc(x.level||'未设职级')} · HC ${fmt(x.headcount??0)}</span></div><div><small>地点 / 用工</small><strong>${esc(x.location||'未填写')}</strong><span>${esc(x.employment_type||'未填写')}</span></div><div><small>计划到岗</small><strong>${esc(x.target_start_date||'未填写')}</strong><span>${esc(x.compensation||'未填写薪酬口径')}</span></div><div><small>协作者</small><strong>${esc(x.recruiter_owner||'未指定招聘负责人')}</strong><span>HM：${esc(x.hiring_manager||'未指定')}</span></div></div><div class="provider-card" style="margin-top:14px"><h3>JD / 业务背景</h3><div class="source-text" style="max-height:180px">${esc(x.jd_text||'尚未填写')}</div></div>`;
    const foot=`<button class="btn" onclick="closeModal()">取消</button>${step>1?'<button class="btn" onclick="jobSetupMove(-1)">上一步</button>':''}${step<4?'<button class="btn primary" onclick="jobSetupMove(1)">下一步</button>':'<button class="btn primary" onclick="saveJobSetup()">保存 Draft 并继续标准设计</button>'}`;
    modal('四步建岗向导',jobSetupProgress()+body,foot)
  }
  function syncJobSetupDraftFromDom(){
    const x=state.jobSetupDraft||{};
    const value=(id,prev='')=>$(id)?$(id).value:prev;
    if(state.jobSetupStep===1){x.role_title=value('#js-role',x.role_title||'');x.headcount=Number(value('#js-headcount',x.headcount??1)||0);x.location=value('#js-location',x.location||'');x.level=value('#js-level',x.level||'')}
    if(state.jobSetupStep===2){x.employment_type=value('#js-employment',x.employment_type||'full_time');x.compensation=value('#js-comp',x.compensation||'');x.target_start_date=value('#js-start',x.target_start_date||'')}
    if(state.jobSetupStep===3){x.recruiter_owner=value('#js-owner',x.recruiter_owner||'');x.hiring_manager=value('#js-hm',x.hiring_manager||'');x.jd_text=value('#js-jd',x.jd_text||'')}
    state.jobSetupDraft=x
  }

  const addCriterionRow = ()=>{
    $('#criteria-rows').insertAdjacentHTML('beforeend',criterionRow({},document.querySelectorAll('.criterion-row').length,[]))
  };
  const applyJobSetupSuggestions = ()=>{const root=$('#criteria-rows');if(!root){toast('请先回到“建岗与标准”页面',true);return}for(const x of state.jobSetupSuggestions||[]){root.insertAdjacentHTML('beforeend',criterionRow({name:x.name||'',decision_critical:!!x.decision_critical,verification_required:x.verification_required!==false,verification_probes:x.verification_probes||[]},document.querySelectorAll('.criterion-row').length))}closeModal();toast('建议已加入草案编辑区；请人工检查后保存并发布')};
  const jobSetupMove = delta=>{syncJobSetupDraftFromDom();state.jobSetupStep=Math.max(1,Math.min(4,state.jobSetupStep+delta));renderJobSetupWizard()};
  const openJobSetup = async()=>{try{const d=await api(`/api/v1/projects/${state.projectId}/protocol-workspace`);const a=d.draft||d.current||{},x=a.recruitment_context||{};state.jobSetupDraft={role_title:x.role_title||a.brief?.title||'',headcount:x.headcount??1,location:x.location||'',level:x.level||'',employment_type:x.employment_type||'full_time',compensation:x.compensation||'',target_start_date:x.target_start_date||'',recruiter_owner:x.recruiter_owner||'',hiring_manager:x.hiring_manager||'',jd_text:x.jd_text||a.brief?.summary||''};state.jobSetupStep=1;renderJobSetupWizard()}catch(e){toast(e.message,true)}};
  const publishCriteria = async rid=>{if(!confirm('发布后将成为候选人评价的当前标准，确认发布？'))return;try{await api(`/api/v1/protocol-revisions/${rid}/publish`,{method:'POST'});toast('招聘标准已发布');await refreshProjects();await projectWorkspace()}catch(e){toast(e.message,true)}};
  const saveCriteria = async rid=>{
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
      await api(`/api/v1/protocol-revisions/${rid}`,{method:'PATCH',body:JSON.stringify({payload,provenance:{ui:'business-convergence11-product-workflow'}})});
      toast('草案已保存；建岗上下文、阶段分配与决策策略已保留');
      await projectWorkspace()
    }catch(e){toast(e.message,true)}
  };
  const saveJobSetup = async()=>{syncJobSetupDraftFromDom();const body=state.jobSetupDraft||{};if(!String(body.role_title||'').trim()){toast('请填写岗位名称',true);state.jobSetupStep=1;renderJobSetupWizard();return}if(Number(body.headcount)<0){toast('Headcount 不能为负数',true);state.jobSetupStep=1;renderJobSetupWizard();return}try{const r=await api(`/api/v1/projects/${state.projectId}/job-setup`,{method:'PATCH',body:JSON.stringify(body)});closeModal();state.jobSetupDraft=null;state.jobSetupStep=1;toast(`已保存建岗 Draft · ${r.protocol_state}；请继续检查评价标准并显式发布`);await refreshProjects();await projectWorkspace()}catch(e){toast(e.message,true)}};
  const suggestJobSetup = async()=>{try{const r=await api(`/api/v1/projects/${state.projectId}/job-setup/suggest`,{method:'POST',body:JSON.stringify({use_knowledge:true})});state.jobSetupSuggestions=r.suggestions||[];const rows=state.jobSetupSuggestions;modal('标准草案建议',`<p class="subtle">这些建议只进入当前页面的草案编辑区，不会自动发布，也不会自动形成录用结论。</p>${rows.length?`<div class="quick-list">${rows.map(x=>`<div class="quick-item" style="align-items:flex-start"><div><div class="quick-title">${esc(x.name)}</div><div class="quick-note">${esc(x.definition||'')}</div><div class="pill-row" style="margin-top:6px"><span class="status ${x.decision_critical?'warn':'info'}">${x.decision_critical?'决策关键':'一般标准'}</span><span class="status ${x.verification_required?'warn':'good'}">${x.verification_required?'需要核实':'无需强制核实'}</span></div><div class="quick-note">${esc((x.verification_probes||[]).join('；')||'暂无核实问题')}</div></div></div>`).join('')}</div>`:'<div class="empty"><strong>当前没有新增建议</strong>现有标准不为空，系统不会自动追加重复标准。</div>'}`,`<button class="btn" onclick="closeModal()">关闭</button>${rows.length?'<button class="btn primary" onclick="applyJobSetupSuggestions()">加入当前草案编辑区</button>':''}`)}catch(e){toast(e.message,true)}};

  return {
    collectCriteria,
    criteriaTab,
    criterionRow,
    criterionStageKeys,
    ensureCriterionKey,
    jobSetupProgress,
    renderJobSetupWizard,
    syncJobSetupDraftFromDom,
    addCriterionRow,
    applyJobSetupSuggestions,
    jobSetupMove,
    openJobSetup,
    publishCriteria,
    saveCriteria,
    saveJobSetup,
    suggestJobSetup,
  };
}
