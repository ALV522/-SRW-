using System.Text.Json;
using System.Text.Json.Serialization;

namespace SRW.Desktop.Contracts;

public sealed record BuildInfo(
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("release_id")] string ReleaseId,
    [property: JsonPropertyName("source_revision")] string? SourceRevision)
{
    public static BuildInfo Load(string applicationRoot)
    {
        var version = File.ReadAllText(Path.Combine(applicationRoot, "VERSION")).Trim();
        var path = Path.Combine(applicationRoot, "BUILD_INFO.json");
        if (!File.Exists(path))
        {
            return new BuildInfo(version, version, null);
        }
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        var root = document.RootElement;
        return new BuildInfo(
            root.TryGetProperty("version", out var v) ? v.GetString() ?? version : version,
            root.TryGetProperty("release_id", out var r) ? r.GetString() ?? version : version,
            root.TryGetProperty("source_revision", out var s) ? s.GetString() : null);
    }
}
