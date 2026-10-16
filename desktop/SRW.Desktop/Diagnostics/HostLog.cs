using System.Text.Json;

namespace SRW.Desktop.Diagnostics;

public sealed class HostLog
{
    private readonly string _path;
    private readonly object _gate = new();
    private readonly Func<object> _identity;

    public HostLog(string path, Func<object> identity)
    {
        _path = path;
        _identity = identity;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
    }

    public void Write(string eventName, object? details = null)
    {
        var payload = new
        {
            ts = DateTimeOffset.UtcNow.ToString("O"),
            @event = eventName,
            identity = _identity(),
            details,
        };
        var line = JsonSerializer.Serialize(payload);
        lock (_gate)
        {
            File.AppendAllText(_path, line + Environment.NewLine);
        }
    }
}
