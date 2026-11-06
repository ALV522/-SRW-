using System.Text.Json;
using SRW.Desktop.Diagnostics;

static void Expect(bool value, string reason)
{
    if (!value) throw new InvalidOperationException(reason);
}

static string Serial(BackendOutputPrivacy.Entry entry) =>
    JsonSerializer.Serialize(new { @event = entry.EventName, details = entry.Details });

// An actual host.log HTTP request with synthetic UUIDs and an injected query
// must retain useful status/route family but never expose identifiable paths.
const string candidateId = "5df9eeb5-6245-416e-aa75-ee781f1ee353";
const string projectId = "07ad3288-c53c-4d66-afe9-90ea840e754f";
const string pii = "candidate@example.org";
var request = BackendOutputPrivacy.Classify(
    $"INFO: 127.0.0.1:56001 - \"GET /api/v1/candidates/{candidateId}/assessment?email={pii} HTTP/1.1\" 409 Conflict",
    isStderr: false);
var text = Serial(request);
Expect(request.EventName == "backend_http", "HTTP classification");
Expect(text.Contains("\"candidate_api\""), "HTTP route family");
Expect(text.Contains("\"status\":409"), "HTTP numeric status");
Expect(text.Contains("\"GET\""), "HTTP method");
Expect(!text.Contains(candidateId) && !text.Contains(pii), "PII leaked in HTTP diagnostics");

var create = BackendOutputPrivacy.Classify(
    $"INFO: 127.0.0.1:56001 - \"POST /api/v1/projects/{projectId}/candidates HTTP/1.1\" 200 OK",
    isStderr: false);
text = Serial(create);
Expect(text.Contains("\"project_api\"") && !text.Contains(projectId), "Project UUID not redacted");

var unknown = BackendOutputPrivacy.Classify(
    "private candidate resume text, auth token=hidden-secret", isStderr: true);
text = Serial(unknown);
Expect(unknown.EventName == "backend_output_redacted", "Unknown output classification");
Expect(!text.Contains("resume") && !text.Contains("hidden-secret"), "stderr payload leaked");

var error = BackendOutputPrivacy.Classify(
    "RuntimeError: candidate@example.org and token=hidden-secret", isStderr: true);
text = Serial(error);
Expect(error.EventName == "backend_exception", "Python exception detection");
Expect(text.Contains("\"RuntimeError\""), "Retain exception type");
Expect(!text.Contains("candidate@example.org") && !text.Contains("hidden-secret"),
       "Python traceback details leaked");

var started = BackendOutputPrivacy.Classify(
    "INFO:     Application startup complete.", isStderr: true);
Expect(started.EventName == "backend_lifecycle"
    && Serial(started).Contains("application_ready"), "Retain startup transition");

var stopped = BackendOutputPrivacy.Classify(
    "INFO:     Application shutdown complete.", isStderr: true);
Expect(stopped.EventName == "backend_lifecycle"
    && Serial(stopped).Contains("application_stopped"), "Retain shutdown transition");

await SRW.HostDiagnostics.Tests.RuntimeApiClientProxyTests.RunAsync();
await SRW.HostDiagnostics.Tests.RuntimeApiClientRedirectTests.RunAsync();
await SRW.HostDiagnostics.Tests.RuntimeApiClientCookieTests.RunAsync();


// #232: the initial window is authored as 1440x900 DIP. The work area reported by
// SystemParameters.WorkArea is DIP too, so divide the physical screen by the scale
// factor instead of hardcoding pixels in the production code.
var resolutions = new (double Scale, double PxWidth, double PxHeight, double TaskbarPx)[]
{
    (1.00, 1920, 1200, 72),
    (1.25, 1920, 1080, 40),
    (1.35, 1920, 1200, 72),
    (1.50, 1920, 1080, 40),
    (1.00, 1366, 768, 40),
    (1.25, 1366, 768, 40),
};
foreach (var (scale, pxWidth, pxHeight, taskbarPx) in resolutions)
{
    var workWidth = pxWidth / scale;
    var workHeight = (pxHeight - taskbarPx) / scale;
    var fit = SRW.Desktop.Hosting.WindowPlacement.Fit(1440, 900, 1024, 720, 0, 0, workWidth, workHeight);
    var label = $"{scale:0.00}x {pxWidth}x{pxHeight}";
    Expect(fit.Width <= workWidth + 0.01 && fit.Height <= workHeight + 0.01, $"window wider/taller than work area at {label}");
    Expect(fit.Left >= -0.01 && fit.Top >= -0.01, $"window starts off-screen at {label}");
    Expect(fit.Left + fit.Width <= workWidth + 0.01, $"window right edge outside work area at {label}");
    Expect(fit.Top + fit.Height <= workHeight + 0.01, $"window bottom edge outside work area at {label}");
    Expect(fit.MinWidth <= fit.Width + 0.01 && fit.MinHeight <= fit.Height + 0.01, $"min size exceeds fitted size at {label}");
}

// A work area that already fits the authored size must not be resized or moved:
// 1440x900 on a 1920x1128 DIP desktop stays exactly as authored, so CenterScreen
// keeps working for the common case.
var untouched = SRW.Desktop.Hosting.WindowPlacement.Fit(1440, 900, 1024, 720, 0, 0, 1920, 1128);
Expect(!untouched.Changed && untouched.Width == 1440 && untouched.Height == 900, "needless resize on a large work area");

Console.WriteLine($"PASS: #232 window placement fits the work area for {resolutions.Length} DPI/resolution combinations (DIP math, no pixel constants)");

// Degenerate/no-monitor work area must fall back to the authored size instead of throwing.
var degenerate = SRW.Desktop.Hosting.WindowPlacement.Fit(1440, 900, 1024, 720, 0, 0, 0, 0);
Expect(!degenerate.Changed && degenerate.Width == 1440 && degenerate.Height == 900, "degenerate work area fallback");

Console.WriteLine("PASS: child-process HTTP status/route diagnostics without candidate, project, path, query, secret or stderr leaks");
