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
            good:good.includes('Three reporting workflows PASS') && good.includes('NOT COVERED:') && !good.includes('Three required workflow runs'),
            hasLink:good.includes('actions/runs/123'),
            pending:partial.includes('NOT FOUND / PENDING') && partial.includes('Not all three reporting'),
            mixed,fail:failing.includes('FAIL/BLOCKED')&&!failing.includes('Three reporting workflows PASS'),
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
        self.assertIn('cancel-in-progress: false', workflow)
        self.assertIn('deleteComment', script)
        self.assertIn('beforeWrite.data.head.sha !== headSha', script)
        self.assertIn('NOT COVERED:', script)
        self.assertNotIn('ref: ${{ github.event.workflow_run.head_sha }}', workflow)
        self.assertIn('pull-requests: write', workflow)
        self.assertIn('live.data.head.sha !== headSha', script)
        self.assertIn("x.user?.login === 'github-actions[bot]'", script)
        self.assertIn("r.head_sha === headSha", script)


    def test_overlapping_heads_without_event_pr_identity_keep_newest_report(self):
        # Exercise the real reporter under a deterministic two-run scheduler.
        # The external GitHub concurrency boundary is modeled, not deployed.
        code = r"""
          const fs = require('fs');
          const {runReporter, MARKER} = require('./scripts/ci_evidence_comment.cjs');
          const workflow = fs.readFileSync('.github/workflows/ci-evidence-comment.yml','utf8');
          const template = workflow.match(/^  group: (.+)$/m)[1];
          function group(sha) {
            // Characterize the former fallback as well as a literal global lock.
            if (!template.includes('${{')) return template;
            const legacy='${{ github.event.workflow_run.pull_requests[0].number || github.event.workflow_run.head_sha }}';
            if (!template.includes(legacy)) throw Error('unmodeled concurrency expression');
            return template.replace(legacy,sha);
          }
          const A='a'.repeat(40), B='b'.repeat(40);
          let live=A, body=MARKER+' initial', release, entered;
          const paused=new Promise(r=>entered=r), resume=new Promise(r=>release=r);
          const writes=[];
          function run(sha) {
            const github={rest:{
              repos:{listPullRequestsAssociatedWithCommit:async()=>({data:[{number:150,state:'open',base:{ref:'main'},head:{sha}}]})},
              pulls:{get:async()=>({data:{state:'open',head:{sha:live}}})},
              actions:{listWorkflowRuns:async()=>({data:{workflow_runs:[]}})},
              issues:{listComments:()=>{},updateComment:async(args)=>{
                if(sha===A){entered();await resume;}
                body=args.body;writes.push(sha===A?'A':'B');
              }},
            },paginate:async()=>[{id:1,user:{login:'github-actions[bot]'},body}]};
            return runReporter({github,core:{info(){},warning(){}},context:{
              repo:{owner:'ALV522',repo:'-SRW-'},payload:{workflow_run:{
                event:'pull_request',repository:{full_name:'ALV522/-SRW-'},
                head_sha:sha,pull_requests:[],
              }},
            }});
          }
          (async()=>{
            const first=run(A);await paused;live=B;
            if(group(A)===group(B)) {
              // Same group cannot start B while A's write is in flight.
              release();await first;await run(B);
            } else {
              await run(B);release();await first;
            }
            process.stdout.write(JSON.stringify({writes,newest:body.includes(B)}));
          })().catch(e=>{console.error(e);process.exit(1)});
        """
        self.assertEqual(self.check_js(code), {'writes':['A','B'], 'newest':True})

    def test_cleanup_failure_preserves_fresh_evidence_and_stays_visible(self):
        code = r"""
          const {runReporter,MARKER}=require('./scripts/ci_evidence_comment.cjs');
          const sha='a'.repeat(40);
          (async()=>{
            const results=[];
            for(const status of [404,500]) {
              let body=MARKER+' old', failure=null;
              const github={rest:{
                repos:{listPullRequestsAssociatedWithCommit:async()=>({data:[{number:151,state:'open',base:{ref:'main'},head:{sha}}]})},
                pulls:{get:async()=>({data:{state:'open',head:{sha}}})},
                actions:{listWorkflowRuns:async()=>({data:{workflow_runs:[]}})},
                issues:{listComments(){},
                  updateComment:async args=>{if(args.comment_id!==2)throw Error('wrong marker');body=args.body;},
                  deleteComment:async()=>{throw Object.assign(Error('cleanup failed'),{status});}},
              },paginate:async()=>[1,2].map(id=>({id,user:{login:'github-actions[bot]'},body}))};
              try {await runReporter({github,core:{info(){},warning(){}},context:{
                repo:{owner:'ALV522',repo:'-SRW-'},payload:{workflow_run:{event:'pull_request',
                repository:{full_name:'ALV522/-SRW-'},head_sha:sha,pull_requests:[]}},
              }});}catch(e){failure=e.status;}
              results.push({fresh:body.includes(sha),failure});
            }
            process.stdout.write(JSON.stringify({results}));
          })().catch(e=>{console.error(e);process.exit(1)});
        """
        self.assertEqual(self.check_js(code), {'results':[
            {'fresh':True,'failure':404}, {'fresh':True,'failure':500}]})

    def test_reporter_deduplicates_and_respects_live_head(self):
        code = r"""
          const {runReporter, MARKER, SOURCES} = require('./scripts/ci_evidence_comment.cjs');
          const SHA='a'.repeat(40), NEXT='b'.repeat(40);
          const logs=[], edited=[], deleted=[], created=[];
          const issueComments=[
            {id:11,user:{login:'github-actions[bot]'},body:MARKER+'\nold 11'},
            {id:44,user:{login:'human'},body:MARKER+'\nnot the bot'},
            {id:33,user:{login:'github-actions[bot]'},body:MARKER+'\nold 33'},
          ];
          let live=SHA;
          const github={
            rest:{
              repos:{listPullRequestsAssociatedWithCommit:async()=>({data:[{number:150,state:'open',base:{ref:'main'},head:{sha:SHA}}]})},
              pulls:{get:async()=>({data:{state:'open',head:{sha:live}}})},
              actions:{listWorkflowRuns:async({workflow_id})=>({data:{workflow_runs:[{head_sha:SHA,event:'pull_request',status:'completed',conclusion:'success',id:SOURCES.findIndex(([f])=>f===workflow_id)+101,html_url:'https://github.com/ALV522/-SRW-/actions/runs/123',created_at:'2026-10-28T00:00:00Z'}]}})},
              issues:{
                listComments:()=>{},
                updateComment:async({comment_id,body})=>{edited.push(comment_id);const c=issueComments.find(x=>x.id===comment_id);c.body=body},
                deleteComment:async({comment_id})=>{deleted.push(comment_id);const ix=issueComments.findIndex(x=>x.id===comment_id);issueComments.splice(ix,1)},
                createComment:async({body})=>{created.push(body);issueComments.push({id:99,user:{login:'github-actions[bot]'},body})},
              },
            },
            paginate:async()=>issueComments.map(x=>({...x})),
          };
          const core={info:x=>logs.push(x),warning:x=>logs.push(x)};
          const context={repo:{owner:'ALV522',repo:'-SRW-'},payload:{workflow_run:{event:'pull_request',repository:{full_name:'ALV522/-SRW-'},head_sha:SHA,pull_requests:[{number:150,head:{sha:SHA}}]}}};
          (async()=>{
            await runReporter({github,context,core});
            const afterOne=issueComments.filter(x=>x.user.login==='github-actions[bot]');
            await runReporter({github,context,core});
            live=NEXT;
            await runReporter({github,context,core});
            context.payload.workflow_run.pull_requests[0].head.sha=NEXT;
            live=SHA;
            await runReporter({github,context,core});
            process.stdout.write(JSON.stringify({
              edits:edited,deletes:deleted,creates:created.length,
              remainingBot:afterOne.length,bodyHead:afterOne[0].body.includes(SHA),
              includesCoverage:afterOne[0].body.includes('NOT COVERED:'),
              staleWarning:logs.some(x=>x.includes('differs from PR #150')),
            }));
          })().catch(e=>{process.stderr.write(String(e.stack));process.exit(1)});
        """
        flags=self.check_js(code)
        self.assertEqual(flags, {
            'edits':[33,33], 'deletes':[11], 'creates':0,
            'remainingBot':1, 'bodyHead':True, 'includesCoverage':True,
            'staleWarning':True,
        })

    def test_count_extraction_matches_real_log_lines_only(self):
        # Lines below are byte-shaped like the real job logs downloaded from
        # run 40854398176 (Ubuntu LF, Windows CRLF) rather than invented.
        code = r"""
          const {extractCounts} = require('./scripts/ci_evidence_comment.cjs');
          const sha = 'a'.repeat(40);
          const ubuntu = ['2026-10-29T10:03:11.8782279Z Current source integrity: 416 SHA-256 entries PASS',
                          '2026-10-29T10:03:55.9479883Z Ran 594 tests in 42.100s'].join('\n');
          const windows = ['2026-10-29T10:03:21.1556012Z Current source integrity: 416 SHA-256 entries PASS',
                           '2026-10-29T10:11:18.5049275Z Ran 601 tests in 474.007s'].join('\r\n');
          const ansi = '\u001b[32mRan 594 tests in 42.100s\u001b[0m\n'
                     + '\u001b[32mCurrent source integrity: 416 SHA-256 entries PASS\u001b[0m';
          process.stdout.write(JSON.stringify({
            ubuntu: extractCounts(ubuntu),
            windows: extractCounts(windows),
            ansi: extractCounts(ansi).status === 'ok',
            indented: extractCounts('  Ran 594 tests in 42.100s').reason,
            partial: extractCounts('Ran 594 tests').reason,
            trailing: extractCounts('Ran 594 tests in 42.100s extra').reason,
            empty: extractCounts('').reason,
          }));
        """
        self.assertEqual(self.check_js(code), {
            'ubuntu': {'status': 'ok', 'tests': 594, 'manifest': 416},
            'windows': {'status': 'ok', 'tests': 601, 'manifest': 416},
            'ansi': True,
            'indented': 'unmatched-tests',
            'partial': 'unmatched-tests',
            'trailing': 'unmatched-tests',
            'empty': 'empty-log',
        })

    def test_two_os_counts_are_separated_and_optional(self):
        code = r"""
          const {summarizeChecks, SOURCES} = require('./scripts/ci_evidence_comment.cjs');
          const sha = 'a'.repeat(40);
          const all = Object.fromEntries(SOURCES.map(([file], i) => [file, {
            head_sha:sha,status:'completed',conclusion:'success',id:300+i,
            html_url:'https://github.com/o/r/actions/runs/'+(300+i),
          }]));
          const counts = {ubuntu:{status:'ok',tests:594,manifest:416},
                          windows:{status:'ok',tests:601,manifest:416}};
          const withCounts = summarizeChecks(all, sha, counts);
          const without = summarizeChecks(all, sha);
          const half = summarizeChecks(all, sha,
            {ubuntu:{status:'ok',tests:594,manifest:416},
             windows:{status:'unavailable',reason:'log-403'}});
          process.stdout.write(JSON.stringify({
            ubuntu: withCounts.includes('ubuntu 594 / 416'),
            windows: withCounts.includes('windows 601 / 416'),
            noStray: (withCounts.match(/COUNT_UNAVAILABLE\(/g) || []).length === 1,
            legacyDash: (without.match(/\| — \|/g) || []).length === 3,
            half: half.includes('windows COUNT_UNAVAILABLE(log-403)'),
            stillPass: withCounts.includes('Three reporting workflows PASS'),
            notAuthorization: withCounts.includes('a merge authorization'),
          }));
        """
        self.assertEqual(self.check_js(code), {
            'ubuntu': True, 'windows': True, 'noStray': True, 'legacyDash': True,
            'half': True, 'stillPass': True, 'notAuthorization': True,
        })

    def test_log_denied_degrades_to_reason_and_keeps_the_verdict(self):
        code = r"""
          const {runReporter, MARKER, SOURCES} = require('./scripts/ci_evidence_comment.cjs');
          const SHA='a'.repeat(40);
          const runs = Object.fromEntries(SOURCES.map(([f], i) => [f, {
            head_sha:SHA,event:'pull_request',status:'completed',conclusion:'success',id:401+i,
            html_url:'https://github.com/o/r/actions/runs/'+(401+i)}]));
          const jobs = [{id:7,name:'source-gate (ubuntu-latest, py3.12)'},
                        {id:8,name:'source-gate (windows-latest, py3.12)'}];
          async function scenario(mode) {
            let body = '';
            const denied = () => { throw Object.assign(Error('denied'), {status:403}); };
            const github = {rest:{
              repos:{listPullRequestsAssociatedWithCommit:async()=>({data:[{number:152,state:'open',base:{ref:'main'},head:{sha:SHA}}]})},
              pulls:{get:async()=>({data:{state:'open',head:{sha:SHA}}})},
              actions:{
                listWorkflowRuns:async({workflow_id})=>({data:{workflow_runs:[runs[workflow_id]]}}),
                listJobsForWorkflowRun: mode === 'jobs' ? denied : async()=>({data:jobs}),
                downloadJobLogsForWorkflowRun: mode === 'jobs' ? denied : denied,
              },
              issues:{listComments(){},updateComment:async a=>{body=a.body},
                      deleteComment:async()=>{},createComment:async a=>{body=a.body}},
            },paginate:async(fn,args)=>{
              if (args && args.run_id) { const r = await fn(args); return r.data || r; }
              return [{id:1,user:{login:'github-actions[bot]'},body:MARKER+' old'}];
            }};
            await runReporter({github,core:{info(){},warning(){}},context:{
              repo:{owner:'ALV522',repo:'-SRW-'},payload:{workflow_run:{event:'pull_request',
              repository:{full_name:'ALV522/-SRW-'},head_sha:SHA,pull_requests:[]}}}});
            return body;
          }
          (async()=>{
            const jobsDenied = await scenario('jobs');
            const logsDenied = await scenario('logs');
            const seen = (body, token) => (body.match(new RegExp(token.replace(/[()]/g,'\\$&'),'g'))||[]).length;
            process.stdout.write(JSON.stringify({
              jobsCounted: seen(jobsDenied, 'COUNT_UNAVAILABLE(jobs-403)'),
              logsCounted: seen(logsDenied, 'COUNT_UNAVAILABLE(log-403)'),
              logsStillPass: logsDenied.includes('Three reporting workflows PASS'),
              logsStatusIntact: (logsDenied.match(/\*\*PASS\*\*/g)||[]).length === 3,
              noLeak: !/denied|unreachable|Error:/.test(jobsDenied + logsDenied),
            }));
          })().catch(e=>{console.error(e);process.exit(1)});
        """
        self.assertEqual(self.check_js(code), {'jobsCounted': 2, 'logsCounted': 2,
                                               'logsStillPass': True, 'logsStatusIntact': True,
                                               'noLeak': True})

    def test_ambiguous_oversized_or_hostile_logs_publish_no_number(self):
        code = r"""
          const {extractCounts, summarizeChecks, SOURCES} = require('./scripts/ci_evidence_comment.cjs');
          const sha='a'.repeat(40);
          const line = n => `2026-10-29T10:03:55.9479883Z Ran ${n} tests in 42.100s`;
          const secret = 'srw1.abcdef0123456789.' + 'c'.repeat(64);
          const hostileLog = [secret, 'C:\\Users\\alice\\token.txt', line(594), line(601)].join('\n');
          const counts = {ubuntu: extractCounts(hostileLog), windows: extractCounts(line(594))};
          const all = Object.fromEntries(SOURCES.map(([f], i) => [f, {
            head_sha:sha,status:'completed',conclusion:'success',id:500+i,
            html_url:'https://github.com/o/r/actions/runs/'+(500+i)}]));
          const body = summarizeChecks(all, sha, counts);
          process.stdout.write(JSON.stringify({
            ambiguous: counts.ubuntu.reason,
            oversized: extractCounts(line(594), {maxBytes: 32}).reason,
            tooManyLines: extractCounts(line(594) + '\n'
              + '2026-10-29T10:03:11.8782279Z Current source integrity: 416 SHA-256 entries PASS',
              {maxLines: 1}).reason,
            noSecret: !body.includes('srw1.'),
            noPath: !body.includes('alice'),
            noNumber: !body.includes('ubuntu 594'),
          }));
        """
        self.assertEqual(self.check_js(code), {
            'ambiguous': 'ambiguous-tests', 'oversized': 'too-large',
            'tooManyLines': 'too-large', 'noSecret': True, 'noPath': True, 'noNumber': True,
        })

if __name__ == '__main__':
    unittest.main()
