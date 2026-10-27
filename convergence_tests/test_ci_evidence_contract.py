"""Smoke the read-only exact-SHA status logic of the trusted workflow_run bot."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for JS evidence status tests')
class EvidenceCommentTests(unittest.TestCase):
    def check_js(self, script: str) -> dict:
        proc = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True,
                              text=True, timeout=10, check=True)
        return json.loads(proc.stdout)

    def test_only_exact_sha_success_can_claim_green(self):
        code = '''
          const {summarizeChecks, SOURCES} = require('./scripts/ci_evidence_comment.cjs');
          const sha = 'a'.repeat(40), bad = 'b'.repeat(40);
          const all = Object.fromEntries(SOURCES.map(([file], i) => [file, {
            head_sha:sha, status:'completed',conclusion:'success',id:123+i,
            html_url:'https://github.com/example/repo/actions/runs/'+(123+i),
          }]));
          const good=summarizeChecks(all,sha);
          const partial=summarizeChecks({...all, 'ci.yml':null},sha);
          let mixed=false;
          try {summarizeChecks({...all,'ci.yml':{...all['ci.yml'],head_sha:bad}},sha)}
          catch(e) {mixed=e.message.includes('mixed CI head')}
          const failing=summarizeChecks({...all,'ci.yml':{...all['ci.yml'], conclusion:'failure'}},sha);
          process.stdout.write(JSON.stringify({
            good:good.includes('Three required workflow runs PASS'),
            hasLink:good.includes('actions/runs/123'),
            pending:partial.includes('NOT FOUND / PENDING') && partial.includes('Not all three'),
            mixed,fail:failing.includes('FAIL/BLOCKED')&&!failing.includes('Three required workflow runs PASS'),
          }));
        '''
        flags = self.check_js(code)
        self.assertEqual(flags, {"good": True, "hasLink": True, "pending": True,
                                 "mixed": True, "fail": True})

    def test_writer_never_executes_pr_code(self):
        workflow = (ROOT / '.github/workflows/ci-evidence-comment.yml').read_text()
        script = (ROOT / 'scripts/ci_evidence_comment.cjs').read_text()
        self.assertIn('workflow_run:', workflow)
        self.assertIn('ref: main', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertNotIn('ref: ${{ github.event.workflow_run.head_sha }}', workflow)
        self.assertIn('pull-requests: write', workflow)
        self.assertIn('live.data.head.sha !== headSha', script)
        self.assertIn("x.user?.login === 'github-actions[bot]'", script)
        self.assertIn("r.head_sha === headSha", script)


if __name__ == '__main__':
    unittest.main()
