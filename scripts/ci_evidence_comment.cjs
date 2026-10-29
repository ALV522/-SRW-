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

/**
 * Machine summary lines, mirrored from the Source Gate step output. Each rule is
 * a *whole-line* match after the log timestamp is removed: a decorated, partial
 * or re-worded line contributes nothing. Numeric groups are bounded so a hostile
 * log cannot smuggle a long digit run into the published comment.
 */
const COUNT_PATTERNS = Object.freeze({
  tests: /^Ran ([0-9]{1,7}) tests in [0-9]{1,6}\.[0-9]{1,6}s$/,
  manifest: /^Current source integrity: ([0-9]{1,7}) SHA-256 entries PASS$/,
});
// Ubuntu and Windows job display names come from the ci.yml matrix expansion.
const COUNTED_JOBS = Object.freeze({
  ubuntu: /^source-gate \(ubuntu-latest, /,
  windows: /^source-gate \(windows-latest, /,
});
const LOG_TIMESTAMP = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z ?/;
const ANSI_ESCAPE = /\u001b\[[0-9;]*[A-Za-z]/g;
// Hard bound on what this reporter will look at. Job logs are attacker-influenced
// only in the sense that a PR controls what its own tests print, so the reader is
// capped and never echoes a line it did not fully match.
const MAX_LOG_BYTES = 8 * 1024 * 1024;
const MAX_LOG_LINES = 200000;

function unavailable(reason) {
  return {status: 'unavailable', reason};
}

/** Only ever returns numbers plus a fixed reason token; never log content. */
function extractCounts(logText, {maxBytes = MAX_LOG_BYTES, maxLines = MAX_LOG_LINES} = {}) {
  if (typeof logText !== 'string' || logText.length === 0) return unavailable('empty-log');
  if (Buffer.byteLength(logText, 'utf8') > maxBytes) return unavailable('too-large');
  const raw = logText.split('\n');
  if (raw.length > maxLines) return unavailable('too-large');
  const seen = {tests: new Set(), manifest: new Set()};
  for (const line of raw) {
    // Windows job logs are CRLF; both are normalised before the anchored match.
    const text = line.replace(/\r$/, '').replace(ANSI_ESCAPE, '').replace(LOG_TIMESTAMP, '');
    for (const [key, pattern] of Object.entries(COUNT_PATTERNS)) {
      const match = pattern.exec(text);
      if (match) seen[key].add(Number(match[1]));
    }
  }
  const found = {};
  for (const key of Object.keys(COUNT_PATTERNS)) {
    const values = seen[key];
    // Zero matches means the format changed; more than one value means the log
    // is not a single deterministic run. Neither may be reported as a number.
    if (values.size === 0) return unavailable(`unmatched-${key}`);
    if (values.size > 1) return unavailable(`ambiguous-${key}`);
    found[key] = [...values][0];
  }
  return {status: 'ok', tests: found.tests, manifest: found.manifest};
}

function statusToken(error) {
  const status = error && error.status;
  return Number.isInteger(status) ? String(status) : 'error';
}

/**
 * Read the two Ubuntu/Windows Source Gate job logs of *one* exact-HEAD run.
 * Every failure mode degrades to a reason token; nothing here can throw at the
 * caller and nothing here may influence the workflow PASS/FAIL verdict.
 */
async function readSourceGateCounts(github, {owner, repo, run}) {
  const result = {ubuntu: unavailable('no-run'), windows: unavailable('no-run')};
  if (!run || !run.id) return result;
  let jobs;
  try {
    jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun,
      {owner, repo, run_id: run.id, per_page: 100});
  } catch (error) {
    const reason = `jobs-${statusToken(error)}`;
    return {ubuntu: unavailable(reason), windows: unavailable(reason)};
  }
  for (const [os, pattern] of Object.entries(COUNTED_JOBS)) {
    const job = jobs.find(item => pattern.test(item.name || ''));
    if (!job) { result[os] = unavailable('job-missing'); continue; }
    let data;
    try {
      const response = await github.rest.actions.downloadJobLogsForWorkflowRun(
        {owner, repo, job_id: job.id});
      data = response && response.data;
    } catch (error) {
      result[os] = unavailable(`log-${statusToken(error)}`);
      continue;
    }
    result[os] = typeof data === 'string' ? extractCounts(data) : unavailable('log-unreadable');
  }
  return result;
}

function countCell(run, counts) {
  // Only the Source Gate carries the machine summary lines; the other two
  // workflows must never inherit its numbers.
  if (!run || !counts) return '—';
  return Object.keys(COUNTED_JOBS).map((os) => {
    const entry = counts[os] || unavailable('no-data');
    return entry.status === 'ok'
      ? `${os} ${entry.tests} / ${entry.manifest}`
      : `${os} COUNT_UNAVAILABLE(${entry.reason})`;
  }).join('<br>');
}

function summarizeChecks(checks, headSha, counts) {
  if (!/^[a-f0-9]{40}$/.test(headSha)) throw new Error('invalid exact HEAD');
  const lines = [MARKER, '### SRW exact-HEAD CI evidence (automated)',
    '', `PR source HEAD: \`${headSha}\`. This comment is computed from GitHub Actions, not agent claims.`,
    '', '| Workflow | Exact-HEAD result | Counts (tests / manifest) | GitHub run |', '|---|---|---|---|'];
  for (const [file, label] of SOURCES) {
    const run = checks[file];
    if (run && run.head_sha !== headSha) throw new Error('mixed CI head: ' + file);
    const status = !run ? 'NOT FOUND / PENDING' : run.status !== 'completed'
      ? 'PENDING' : (run.conclusion === 'success' ? 'PASS' : `FAIL/BLOCKED (${run.conclusion || 'unknown'})`);
    const link = run ? `[run ${run.id}](${run.html_url})` : 'NOT AVAILABLE';
    lines.push(`| ${label} | **${status}** | ${countCell(run, file === 'ci.yml' ? counts : null)} | ${link} |`);
  }
  const green = SOURCES.every(([f]) => checks[f] && checks[f].status === 'completed'
    && checks[f].conclusion === 'success');
  lines.push('', green ? '**Three reporting workflows PASS on this HEAD (not the complete merge gate).**'
    : '**Not all three reporting workflows PASS on this HEAD.**',
  '', 'Counts are read from the same exact-HEAD run\'s own job logs, one value per OS, '
      + 'and are **visibility only**: they never turn a FAIL into a PASS, never authorise a merge, '
      + 'and `COUNT_UNAVAILABLE(<reason>)` means the count could not be proven, not that it passed.',
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
  // Counts are collected *after* the verdict is fixed and can never alter it.
  // A collector failure is reported as a reason token, not as an exception.
  let counts = null;
  try {
    counts = await readSourceGateCounts(github, {owner, repo, run: checks['ci.yml']});
  } catch (error) {
    counts = {ubuntu: unavailable('collector-error'), windows: unavailable('collector-error')};
  }
  core.info(`source counts: ${JSON.stringify(counts)}`);
  const body = summarizeChecks(checks, headSha, counts);
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

module.exports = {MARKER, SOURCES, COUNT_PATTERNS, MAX_LOG_BYTES, MAX_LOG_LINES,
  extractCounts, readSourceGateCounts, summarizeChecks, runReporter};
