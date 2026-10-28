/**
 * Trusted-main workflow_run reporter: one updatable PR comment, exact HEAD only.
 * NEVER checkout/execute a pull-request branch with this write-scoped token.
 */
'use strict';
const MARKER = '<!-- srw-ci-evidence-v1 -->';
const SOURCES = Object.freeze([
  ['ci.yml', 'SRW Source Gate'],
  ['browser-e2e.yml', 'SRW Chromium Business Acceptance'],
  ['governance.yml', 'SRW Governance Contract'],
]);

function summarizeChecks(checks, headSha) {
  if (!/^[a-f0-9]{40}$/.test(headSha)) throw new Error('invalid exact HEAD');
  const lines = [MARKER, '### SRW exact-HEAD CI evidence (automated)',
    '', `PR source HEAD: \`${headSha}\`. This comment is computed from GitHub Actions, not agent claims.`,
    '', '| Workflow | Exact-HEAD result | GitHub run |', '|---|---|---|'];
  for (const [file, label] of SOURCES) {
    const run = checks[file];
    if (run && run.head_sha !== headSha) throw new Error('mixed CI head: ' + file);
    const status = !run ? 'NOT FOUND / PENDING' : run.status !== 'completed'
      ? 'PENDING' : (run.conclusion === 'success' ? 'PASS' : `FAIL/BLOCKED (${run.conclusion || 'unknown'})`);
    const link = run ? `[run ${run.id}](${run.html_url})` : 'NOT AVAILABLE';
    lines.push(`| ${label} | **${status}** | ${link} |`);
  }
  const green = SOURCES.every(([f]) => checks[f] && checks[f].status === 'completed'
    && checks[f].conclusion === 'success');
  lines.push('', green ? '**Three reporting workflows PASS on this HEAD (not the complete merge gate).**'
    : '**Not all three reporting workflows PASS on this HEAD.**',
  '', '**NOT COVERED:** SRW Repository Integrity, SRW Windows Host Rebuild Candidate, SRW C11 Windows Offline Wheelhouse; check their actual runs separately.',
  '', 'This is **not** a merge authorization. Non-author-track review, manifest diff, '
      + 'Windows WPF/Native acceptance and final main/head checks remain separate gates.',
  '', 'Automated comment updates in place; old PR commits and main-push CI are not reused.');
  return lines.join('\n');
}

async function runReporter({github, context, core}) {
  const {owner, repo} = context.repo;
  const upstream = context.payload.workflow_run;
  if (!upstream || upstream.event !== 'pull_request'
      || upstream.repository?.full_name !== `${owner}/${repo}`) {
    core.info('Not an in-repository PR workflow completion; no comment');
    return;
  }
  const headSha = upstream.head_sha;
  if (!/^[a-f0-9]{40}$/.test(headSha)) throw new Error('missing SHA');
  // A GitHub pull_request workflow may report a synthetic merge-ref. Do not
  // relabel it as the submitted PR HEAD; produce an explicit provenance log.
  for (const attached of upstream.pull_requests || []) {
    if (attached.head?.sha && attached.head.sha !== headSha) {
      core.warning(`Workflow SHA ${headSha} differs from PR #${attached.number} source HEAD ${attached.head.sha}; refusing to mix evidence`);
      return;
    }
  }
  // All referenced PR metadata is untrusted; it is never interpolated into
  // shell commands, and this trusted workflow executes no PR-provided code.
  const associated = await github.rest.repos.listPullRequestsAssociatedWithCommit({
    owner, repo, commit_sha: headSha, per_page: 100,
  });
  const candidates = associated.data.filter(p => p.state === 'open' && p.base.ref === 'main'
    && p.head.sha === headSha);
  if (!candidates.length) {
    core.info(`No open main PR at exact workflow HEAD ${headSha}; no comment`);
    return;
  }
  const checks = {};
  for (const [file] of SOURCES) {
    const response = await github.rest.actions.listWorkflowRuns({
      owner, repo, workflow_id: file, event: 'pull_request', head_sha: headSha,
      per_page: 100,
    });
    // Only *exact-head* PR runs are eligible. Never promote merge-ref SHA,
    // a prior head, or green main push CI into this report.
    const matching = response.data.workflow_runs.filter(r => r.head_sha === headSha
      && r.event === 'pull_request');
    matching.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    checks[file] = matching[0] || null;
  }
  const body = summarizeChecks(checks, headSha);
  for (const pr of candidates) {
    const live = await github.rest.pulls.get({owner, repo, pull_number: pr.number});
    if (live.data.state !== 'open' || live.data.head.sha !== headSha) {
      core.info(`PR #${pr.number} changed head while reporting; skipping`);
      continue;
    }
    const all = await github.paginate(github.rest.issues.listComments, {
      owner, repo, issue_number: pr.number, per_page: 100,
    });
    // Workflow concurrency is repository-wide, including empty event PR lists.
    // Consolidate any duplicate
    // markers created by older bot versions or interrupted deployments. Keep
    // the newest one as the sole authoritative updatable comment.
    const markers = all.filter(x => x.user?.login === 'github-actions[bot]'
      && x.body?.startsWith(MARKER)).sort((a, b) => b.id - a.id);
    // Recheck the live head immediately before any write: a stale workflow_run
    // must never overwrite evidence from a later PR source HEAD.
    const beforeWrite = await github.rest.pulls.get({owner, repo, pull_number: pr.number});
    if (beforeWrite.data.state !== 'open' || beforeWrite.data.head.sha !== headSha) {
      core.info(`PR #${pr.number} moved while building evidence; refusing stale write`);
      continue;
    }
    if (markers.length) {
      await github.rest.issues.updateComment({owner, repo, comment_id: markers[0].id, body});
    } else {
      await github.rest.issues.createComment({owner, repo, issue_number: pr.number, body});
    }
    // Publish fresh evidence first; cleanup errors still fail the workflow visibly.
    for (const obsolete of markers.slice(1)) {
      await github.rest.issues.deleteComment({owner, repo, comment_id: obsolete.id});
    }
    core.info(`CI evidence updated for PR #${pr.number} at ${headSha}`);
  }
}

module.exports = {MARKER, SOURCES, summarizeChecks, runReporter};
