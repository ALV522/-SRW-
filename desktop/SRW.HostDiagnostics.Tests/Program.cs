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

Console.WriteLine("PASS: child-process HTTP status/route diagnostics without candidate, project, path, query, secret or stderr leaks");
