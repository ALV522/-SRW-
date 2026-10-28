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

if __name__ == '__main__':
    unittest.main()
