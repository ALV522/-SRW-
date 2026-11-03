/* #198: Browser-only manual Source → unreviewed Claim proposal.
 * All provenance, revision, CSRF and human-review rules remain in the shared Core.
 * No Provider request, persistent client cache or second database is introduced.
 */
const srwManualEscape = value => String(value ?? '').replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','"':'&#39;'}[c]));
let srwManualDraft = null;

function srwManualToast(message, error = false) {
  const root = document.querySelector('#toast-root');
  if (!root) return;
  root.innerHTML = `<div class="toast ${error ? 'error' : ''}">${srwManualEscape(message)}</div>`;
}
window.srwManualClaimCancel = () => {
  srwManualDraft = null;
  window.closeModal?.();
};

window.srwManualClaimOpen = async (candidateId, sourceId) => {
  try {
    const workspace = await window.srwApi(`/api/v1/candidates/${encodeURIComponent(candidateId)}/workspace`);
    const source = (workspace.sources || []).find(row => row.source_id === sourceId);
    if (!source?.in_current_material || !source.has_text) {
      srwManualToast('只能从当前已发布、含文字的材料提出事实。请先发布材料版本。', true);
      return;
    }
    const content = await window.srwApi(`/api/v1/sources/${encodeURIComponent(sourceId)}/content`);
    if (content.candidate_id !== candidateId || !content.has_text ||
        typeof content.text_content !== 'string') {
      srwManualToast('材料归属或原文不可核实，请刷新候选人。', true);
      return;
    }
    srwManualDraft = {candidateId, sourceId, text: content.text_content, selection: null};
    const root = document.querySelector('#modal-root');
    root.innerHTML = `<div class="modal-backdrop"><div class="modal" style="width:min(960px,94vw)">
      <div class="modal-head"><h3>从当前 Source 人工提出事实</h3>
        <button class="x" onclick="srwManualClaimCancel()" aria-label="关闭">×</button></div>
      <div class="modal-body">
        <p class="subtle">选中下方原文中的确切引文，再点击“引用选中文本”。此操作只提出待核实 Claim，不会自动确认事实或形成录用决定。</p>
        <div class="field"><label for="srw-manual-source">当前材料原文（只读，可选择）</label>
          <textarea id="srw-manual-source" class="textarea" readonly
            style="min-height:170px;max-height:36vh;white-space:pre-wrap">${srwManualEscape(content.text_content)}</textarea></div>
        <div class="actions" style="margin:8px 0"><button class="btn" onclick="srwManualCaptureQuote()">引用选中文本</button></div>
        <div class="field"><label>待引用原文</label>
          <div id="srw-manual-quote" class="codebox" style="white-space:pre-wrap">尚未选取原文</div></div>
        <div class="field" style="margin-top:12px"><label for="srw-manual-normalized">事实提案（人工编辑）</label>
          <textarea id="srw-manual-normalized" class="textarea" maxlength="2000"
            placeholder="用一句可核实的话概括选中引文，不添加原文没有的信息"></textarea></div>
        <p class="subtle">提交后必须在候选人 Claim 列表中另行点击“确认事实”或“拒绝提议”。材料版本变化时需重新选取。</p>
      </div>
      <div class="modal-foot"><button class="btn" onclick="srwManualClaimCancel()">取消</button>
        <button id="srw-manual-submit" class="btn primary" disabled onclick="srwManualClaimSubmit()">提交待核实 Claim</button></div>
    </div></div>`;
  } catch (error) {
    srwManualDraft = null;
    srwManualToast('无法读取当前 Source。请确认材料已发布并刷新候选人。', true);
  }
};

window.srwManualCaptureQuote = () => {
  const field = document.querySelector('#srw-manual-source');
  if (!field || !srwManualDraft) return;
  const raw = field.value.slice(field.selectionStart, field.selectionEnd);
  const quote = raw.trim();
  const leading = raw.length - raw.trimStart().length;
  // Browser selectionStart is UTF-16; Python Source locators use Unicode
  // code-point offsets. Count code points before the first non-space character.
  const charStart = Array.from(field.value.slice(0, field.selectionStart + leading)).length;
  if (!quote || Array.from(quote).length > 1000) {
    srwManualDraft.selection = null;
    document.querySelector('#srw-manual-quote').textContent = '请选择 1–1000 字符的原文';
    document.querySelector('#srw-manual-submit').disabled = true;
    srwManualToast('请在原文中选中不超过 1000 字符的确切引文。', true);
    return;
  }
  srwManualDraft.selection = {quote, char_start: charStart};
  document.querySelector('#srw-manual-quote').textContent = quote;
  const summary = document.querySelector('#srw-manual-normalized');
  if (!summary.value.trim()) summary.value = quote;
  document.querySelector('#srw-manual-submit').disabled = false;
};

window.srwManualClaimSubmit = async () => {
  const draft = srwManualDraft;
  const summary = document.querySelector('#srw-manual-normalized');
  const button = document.querySelector('#srw-manual-submit');
  if (!draft?.selection || !summary || !button || button.disabled) return;
  const normalized = summary.value.trim();
  if (!normalized || Array.from(normalized).length > 2000) {
    srwManualToast('事实提案必须包含 1–2000 字符。', true);
    return;
  }
  button.disabled = true;
  try {
    const workspace = await window.srwApi(`/api/v1/candidates/${encodeURIComponent(draft.candidateId)}/workspace`);
    if (!(workspace.sources || []).some(source =>
      source.source_id === draft.sourceId && source.in_current_material && source.has_text)) {
      throw new Error('stale-material');
    }
    const result = await window.srwApi(
      `/api/v1/candidates/${encodeURIComponent(draft.candidateId)}/claims/manual`,
      {method: 'POST', body: JSON.stringify({
        source_id: draft.sourceId, normalized_text: normalized, locator: draft.selection
      })}
    );
    srwManualDraft = null;
    window.closeModal?.();
    await window.openCandidate(draft.candidateId);
    srwManualToast(result.confirmation_state === 'unreviewed'
      ? '已提出待核实 Claim。请单独执行人工确认或拒绝。'
      : '该 Claim 已存在；保留其原有人工核实状态。');
    document.getElementById(`srw-claim-${result.claim_id}`)?.scrollIntoView({block:'center'});
  } catch (error) {
    button.disabled = false;
    srwManualToast('提交未完成：请刷新当前材料、重新选择原文并核对事实描述。', true);
  }
};
