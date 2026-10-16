using System.Text.Json.Serialization;

namespace SRW.Desktop.Runtime;

public sealed record RuntimeIdentity(
    [property: JsonPropertyName("product")] string Product,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("runtime")] string Runtime,
    [property: JsonPropertyName("edition")] string Edition,
    [property: JsonPropertyName("instanceId")] string InstanceId,
    [property: JsonPropertyName("releaseId")] string ReleaseId,
    [property: JsonPropertyName("sessionId")] string SessionId);
