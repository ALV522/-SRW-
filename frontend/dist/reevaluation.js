// Thin reevaluation client: Core owns diff calculation, validation and apply.
export function createReevaluationFeature({api, $, esc, modal, toast, closeModal, refresh}) {
  const statuses = [['met','已确认'],['partial','部分满足'],['missing','仍需核实'],['conflict','存在矛盾'],['not_met','未满足']];
  const levels = [['strong','强'],['medium','一般'],['weak','弱'],['none','无']];
  const options = rows => '<option value="">请选择</option>' + rows.map(([v,label]) => `<option value="${v}">${label}</option>`).join('');
  const open = async cid => {
    try {
      const workspace = await api(`/api/v1/candidates/${cid}/workspace`);
      if (!workspace.decision_context_hash) {toast('请先发布岗位标准和候选人材料', true); return;}
      const currentSources = new Map(workspace.sources.filter(s => s.in_current_material).map(s => [s.source_id,s]));
      const claims = workspace.claims.filter(c => currentSources.has(c.source_id));
      const rows = workspace.criteria.map((criterion, index) => `<section class="panel reeval-criterion" data-index="${index}">
        <div class="panel-head"><label><input type="checkbox" class="reeval-include"> 修改 ${esc(criterion.name)}</label></div>
        <div class="panel-body"><p class="subtle">当前：${esc(criterion.status_label)} · ${esc(criterion.evidence_label)}。勾选后请填写完整提议；未选 Claim 表示不引用证据。</p>
        <fieldset disabled style="border:0;padding:0;margin:0"><div class="form-grid">
          <label class="field">提议判断<select class="select reeval-status">${options(statuses)}</select></label>
          <label class="field">提议证据强度<select class="select reeval-level">${options(levels)}</select></label>
          <label class="field full">理由<textarea class="textarea reeval-reason"></textarea></label>
          <label class="field full">缺口<textarea class="textarea reeval-gap"></textarea></label>
        </div><p>引用当前材料中的 Claim（选择不会将其自动确认为事实）：</p>
        ${claims.length ? claims.map(c => `<label style="display:block;overflow-wrap:anywhere"><input class="reeval-claim" type="checkbox" value="${esc(c.claim_id)}"> ${esc(c.normalized_text)}<small class="subtle"> · ${esc(currentSources.get(c.source_id).filename||c.source_id)} · ${esc(c.authority)} / ${esc(c.confirmation_state)}</small></label>`).join('') : '<p class="subtle">当前材料暂无 Claim，可先完成人工核实。</p>'}
        </fieldset></div></section>`).join('');
      modal('创建复评草案', `<div class="field"><label>复评摘要</label><textarea id="r-summary" class="textarea"></textarea></div>
        <div class="field"><label>提议说明（不会直接改人工决定）</label><textarea id="r-proposal" class="textarea"></textarea></div>
        <p>选择需要修改的标准；不勾选时保留为仅说明草案。保存后仍需查看差异并确认应用。</p>${rows}`,
        '<button class="btn" onclick="closeModal()">取消</button><button id="reeval-save" class="btn primary">创建草案</button>');
      const root = $('#modal-root');
      root.querySelectorAll('.reeval-include').forEach(box => {box.onchange = () => {box.closest('section').querySelector('fieldset').disabled = !box.checked;};});
      const button = root.querySelector('#reeval-save');
      button.onclick = async () => {
        const judgments = [];
        for (const row of root.querySelectorAll('.reeval-criterion')) {
          if (!row.querySelector('.reeval-include').checked) continue;
          const status = row.querySelector('.reeval-status').value;
          const evidence_level = row.querySelector('.reeval-level').value;
          if (!status || !evidence_level) {toast('请为勾选的标准选择判断和证据强度', true); return;}
          judgments.push({criterion_key:workspace.criteria[Number(row.dataset.index)].criterion_key, status, evidence_level,
            reason:row.querySelector('.reeval-reason').value, gap:row.querySelector('.reeval-gap').value,
            claim_ids:[...row.querySelectorAll('.reeval-claim:checked')].map(c => c.value)});
        }
        button.disabled = true;
        try {
          await api(`/api/v1/candidates/${cid}/reevaluations`, {method:'POST',body:JSON.stringify({
            summary:root.querySelector('#r-summary').value, expected_context_hash:workspace.decision_context_hash,
            proposal:{note:root.querySelector('#r-proposal').value, judgments}})});
          closeModal(); toast('复评草案已创建，请查看差异后确认应用'); await refresh();
        } catch(e) {toast(e.message, true); button.disabled = false;}
      };
    } catch(e) {toast(e.message, true);}
  };
const apply=async(cid,id)=>{
  try{
    const {drafts}=await api(`/api/v1/candidates/${cid}/reevaluations`);
    const draft=drafts.find(x=>x.draft_id===id);
    if(!draft||draft.state!=='draft'){toast('草案已变化，请刷新后查看',true);return}
    const fields=[['status','判断状态'],['evidence_level','证据强度'],['reason','理由'],['gap','缺口'],['claim_ids','Claim 引用']];
    const value=(row,key)=>esc(Array.isArray(row?.[key])?row[key].join('、')||'—':row?.[key]||'—');
    const changes=(draft.diff||[]).map(change=>`<section class="panel"><div class="panel-head"><h3>标准：${esc(change.criterion_key)}</h3></div><div class="panel-body" style="overflow-x:auto"><table class="table"><thead><tr><th>字段</th><th>应用前</th><th>应用后</th></tr></thead><tbody>${fields.map(([key,label])=>`<tr><th>${label}</th><td style="white-space:pre-wrap;overflow-wrap:anywhere">${value(change.before,key)}</td><td style="white-space:pre-wrap;overflow-wrap:anywhere">${value(change.after,key)}</td></tr>`).join('')}</tbody></table></div></section>`).join('');
    modal('复评差异确认',`<p>${esc(draft.summary||'复评草案')}</p><p style="white-space:pre-wrap">${esc(draft.proposal?.note||'')}</p><p>确认后应用以下判断差异；不会新增或覆盖人工决定。上下文变化时 Core 将拒绝应用。</p>${changes||'<div class="empty">无判断差异；确认仅将草案标记为已应用。</div>'}`,
      '<button class="btn" onclick="closeModal()">取消</button><button id="reeval-confirm" class="btn primary">确认应用</button>');
    // Capture the reviewed draft, rather than mutable navigation state.
    const button=$('#reeval-confirm');
    button.onclick=async()=>{
      button.disabled=true;
      try{
        await api(`/api/v1/reevaluations/${id}/apply`,{method:'POST'});
        closeModal();toast('草案已应用；人工决定未被修改');await refresh();
      }catch(e){toast(e.message,true);button.disabled=false}
    };
  }catch(e){toast(e.message,true)}
};
  return {open, apply};
}
