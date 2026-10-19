using System.Text.RegularExpressions;

namespace SRW.Desktop.Diagnostics;

/// <summary>
/// Data-minimizing translation of child-process stdout/stderr into structured
/// diagnostics. Never persist raw HTTP paths, query strings, candidate/project
/// IDs, provider responses, secrets, Python tracebacks or resume contents.
/// Keep method/status/route family and known lifecycle transitions instead.
/// </summary>
public static partial class BackendOutputPrivacy
{
    public readonly record struct Entry(string EventName, object Details);

    [GeneratedRegex(
        "\"" + @"(?<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(?<target>\S+)\s+HTTP/\d+(?:\.\d+)?\"" + @"\s+(?<status>\d{3})\b",
        RegexOptions.CultureInvariant | RegexOptions.IgnoreCase)]
    private static partial Regex HttpAccessLine();

    [GeneratedRegex(
        @"^\s*(?<type>[a-zA-Z_][a-zA-Z_0-9]{0,95}(?:Error|Exception))\s*:",
        RegexOptions.CultureInvariant)]
    private static partial Regex PythonExceptionLine();

    public static Entry Classify(string? line, bool isStderr)
    {
        // No child-process data is written verbatim, even for stderr.
        var input = line ?? "";
        var match = HttpAccessLine().Match(input);
        if (match.Success && int.TryParse(match.Groups["status"].Value, out var status))
        {
            return new Entry("backend_http", new
            {
                method = match.Groups["method"].Value.ToUpperInvariant(),
                status,
                route = RouteFamily(match.Groups["target"].Value),
            });
        }

        string? phase = null;
        if (input.Contains("Application startup complete.", StringComparison.Ordinal))
            phase = "application_ready";
        else if (input.Contains("Application shutdown complete.", StringComparison.Ordinal))
            phase = "application_stopped";
        else if (input.Contains("Waiting for application startup.", StringComparison.Ordinal))
            phase = "starting";
        else if (input.Contains("Waiting for application shutdown.", StringComparison.Ordinal))
            phase = "stopping";
        else if (input.Contains("Shutting down", StringComparison.Ordinal))
            phase = "shutdown_requested";
        else if (input.Contains("Finished server process", StringComparison.Ordinal))
            phase = "process_exited";
        else if (input.Contains("Started server process", StringComparison.Ordinal))
            phase = "process_started";
        else if (input.Contains("Uvicorn running on ", StringComparison.Ordinal))
            phase = "loopback_listener_ready";

        if (phase is not null)
            return new Entry("backend_lifecycle", new { phase });

        var exception = PythonExceptionLine().Match(input);
        if (exception.Success)
            return new Entry("backend_exception", new
            {
                stream = isStderr ? "stderr" : "stdout",
                exception_type = exception.Groups["type"].Value,
                message_redacted = true,
            });

        return new Entry("backend_output_redacted", new
        {
            stream = isStderr ? "stderr" : "stdout",
            message_redacted = true,
        });
    }

    private static string RouteFamily(string target)
    {
        // The exact URI and query parameters are never exposed by this
        // classifier. Labels deliberately omit business UUIDs and filenames.
        if (target.StartsWith("/api/v1/candidates/", StringComparison.OrdinalIgnoreCase))
            return "candidate_api";
        if (target.StartsWith("/api/v1/projects/", StringComparison.OrdinalIgnoreCase))
            return "project_api";
        if (target.StartsWith("/api/v1/protocol-revisions/", StringComparison.OrdinalIgnoreCase))
            return "protocol_api";
        if (target.StartsWith("/api/v1/settings/", StringComparison.OrdinalIgnoreCase))
            return "settings_api";
        if (target.StartsWith("/api/v1/runtime/", StringComparison.OrdinalIgnoreCase))
            return "runtime_api";
        if (target.StartsWith("/api/v1/", StringComparison.OrdinalIgnoreCase))
            return "other_api";
        if (target.StartsWith("/health/", StringComparison.OrdinalIgnoreCase))
            return "health";
        if (target.StartsWith("/v1/", StringComparison.OrdinalIgnoreCase))
            return "frontend_asset";
        if (target == "/")
            return "frontend";
        return "other";
    }
}
