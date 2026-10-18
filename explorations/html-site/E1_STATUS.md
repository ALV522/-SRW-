# E1 Verification Status

## Implemented

- standalone HTML website experiment;
- same-origin SRW health probe;
- live Dashboard GET adapter;
- live Project list GET adapter;
- live Project pipeline GET adapter;
- live active Candidate list GET adapter;
- live Candidate Summary GET adapter;
- live Candidate Workspace GET adapter;
- optional Candidate Brief GET adapter;
- mock fallback for direct `file://` opening;
- hard design boundary: E1 issues GET requests only;
- Web/EXE shared-authority architecture documented.

## Verified in this development turn

- exploration remains on `explore/html-site-prototype`;
- no pull request was opened;
- no mainline files were edited;
- inline JavaScript in `e1-live.html` parses successfully;
- the normal mainline Source Gate is not configured to run on this isolated branch unless a PR targeting main is deliberately opened.

## Not yet verified

- serving `e1-live.html` from a real SRW local origin;
- real Dashboard rendering from a Windows portable instance;
- real Project/Candidate navigation against a populated database;
- simultaneous browser + WebView2 observation of the same database;
- refresh/change notification latency;
- Windows browser launch and process lifecycle;
- production authentication/session policy for any future non-loopback Web deployment.

## Acceptance rule

Do not describe E1 as production-ready until the above live-runtime checks have been executed. The current result is an isolated, syntactically valid, read-only integration prototype.
