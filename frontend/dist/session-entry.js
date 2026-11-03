/* #43 M3A: the opt-in Local Browser pairing entry, not a second authority.
 * A real Core must issue the code to a trusted operator console. The page
 * receives it only from a deliberate human entry; no URL, log or localStorage.
 */
export async function ensureBusinessSession() {
  const probe = await fetch('/api/v1/runtime/info', {
    credentials: 'same-origin', cache: 'no-store',
  });
  if (probe.ok) return;
  if (probe.status !== 401) {
    throw new Error('无法确认本机会话状态，请检查 Core 后重试。');
  }

  const host = document.getElementById('app');
  if (!host) throw new Error('缺少 SRW 应用容器');
  host.innerHTML = `<main style="max-width:440px;margin:9vh auto;padding:24px;border:1px solid #d6dce5;border-radius:12px">
    <h1>本机配对</h1>
    <p>从启动 SRW 的交互式本机终端读取一次性配对码。此操作不会授予自动招聘决策权限。</p>
    <form id="srw-pair-form">
      <label for="srw-pair-code">一次性配对码</label>
      <input id="srw-pair-code" type="password" autocomplete="off" spellcheck="false"
        required style="display:block;width:100%;box-sizing:border-box;margin:12px 0;padding:10px">
      <button type="submit" class="btn primary">连接工作台</button>
      <p id="srw-pair-error" role="alert" aria-live="polite"></p>
    </form>
  </main>`;
  const form = host.querySelector('#srw-pair-form');
  const input = host.querySelector('#srw-pair-code');
  const error = host.querySelector('#srw-pair-error');
  const button = form.querySelector('button');
  return new Promise(resolve => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (button.disabled) return;
      const code = input.value;
      input.value = '';
      error.textContent = '';
      button.disabled = true;
      try {
        const response = await fetch('/api/v1/runtime/business-attach', {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({code}),
        });
        if (!response.ok) {
          error.textContent = '配对失败或已过期，请在本机终端获取有效配对码。';
          return;
        }
        const verified = await fetch('/api/v1/runtime/info', {
          credentials: 'same-origin', cache: 'no-store',
        });
        if (!verified.ok) {
          error.textContent = '会话未生效，请重新启动并配对。';
          return;
        }
        resolve();
      } catch {
        error.textContent = '无法连接本地 Core，请检查服务状态。';
      } finally {
        button.disabled = false;
      }
    });
    input.focus();
  });
}
