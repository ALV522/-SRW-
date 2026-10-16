using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace SRW.Desktop.Workspace;

public sealed class WorkspaceLease : IDisposable
{
    private const int SchemaVersion = 2;
    private const int ERROR_ALREADY_EXISTS = 183;
    private static readonly TimeSpan FreshIncompleteWindow = TimeSpan.FromSeconds(5);
    private readonly string _lockDirectory;
    private readonly string _metadataPath;
    private readonly LeaseMetadata _metadata;
    private bool _owned;

    private WorkspaceLease(string dataRoot, LeaseMetadata metadata)
    {
        _lockDirectory = Path.Combine(dataRoot, "app.lock");
        _metadataPath = Path.Combine(_lockDirectory, "instance.json");
        _metadata = metadata;
    }

    public static WorkspaceLease Acquire(
        string dataRoot,
        int port,
        string version,
        string releaseId,
        string instanceId,
        string sessionId)
    {
        Directory.CreateDirectory(dataRoot);
        var metadata = new LeaseMetadata(
            SchemaVersion,
            Environment.ProcessId,
            port,
            version,
            releaseId,
            instanceId,
            sessionId,
            "windows",
            DateTimeOffset.UtcNow.ToString("O"),
            GetCurrentProcessStartUtc(),
            Environment.MachineName,
            Path.GetFullPath(dataRoot),
            HashDataRoot(dataRoot));
        var lease = new WorkspaceLease(dataRoot, metadata);
        lease.AcquireDirectory();
        return lease;
    }

    public void UpdatePort(int port)
    {
        EnsureOwned();
        _metadata.Port = port;
        WriteMetadata();
    }

    private void AcquireDirectory()
    {
        for (var attempt = 0; attempt < 2; attempt++)
        {
            if (CreateDirectoryW(_lockDirectory, IntPtr.Zero))
            {
                _owned = true;
                try
                {
                    WriteMetadata();
                    return;
                }
                catch
                {
                    _owned = false;
                    Directory.Delete(_lockDirectory, recursive: true);
                    throw;
                }
            }

            var error = Marshal.GetLastWin32Error();
            if (error != ERROR_ALREADY_EXISTS)
            {
                throw new Win32Exception(error, $"Cannot create workspace lock directory: {_lockDirectory}");
            }
            if (!TryRecoverStale())
            {
                throw BuildAlreadyRunning();
            }
        }
        throw BuildAlreadyRunning();
    }

    private bool TryRecoverStale()
    {
        if (!Directory.Exists(_lockDirectory))
        {
            return true;
        }
        if (!File.Exists(_metadataPath))
        {
            var age = DateTimeOffset.UtcNow - Directory.GetLastWriteTimeUtc(_lockDirectory);
            if (age < FreshIncompleteWindow)
            {
                return false;
            }
            Directory.Delete(_lockDirectory, recursive: true);
            return true;
        }
        try
        {
            var existing = JsonSerializer.Deserialize<LeaseMetadata>(File.ReadAllText(_metadataPath));
            if (existing is not null && IsSameProcessInstance(existing.Pid, existing.ProcessStartedAtUtc))
            {
                return false;
            }
        }
        catch (JsonException)
        {
            return false;
        }
        Directory.Delete(_lockDirectory, recursive: true);
        return true;
    }

    private InvalidOperationException BuildAlreadyRunning() =>
        new("INSTANCE_ALREADY_RUNNING: 同一数据目录已有 Web 或 Windows Edition 实例持有写入权。");

    private static string GetCurrentProcessStartUtc()
    {
        using var process = Process.GetCurrentProcess();
        return process.StartTime.ToUniversalTime().ToString("O");
    }

    private static bool IsSameProcessInstance(int pid, string? expectedStartedAtUtc)
    {
        try
        {
            using var process = Process.GetProcessById(pid);
            if (process.HasExited)
            {
                return false;
            }
            if (string.IsNullOrWhiteSpace(expectedStartedAtUtc))
            {
                // Backward compatibility with schema-v2 locks written before process identity was added.
                return true;
            }
            if (!DateTimeOffset.TryParse(expectedStartedAtUtc, out var expected))
            {
                // Corrupt identity on a live PID is treated conservatively as active.
                return true;
            }
            var actual = new DateTimeOffset(process.StartTime.ToUniversalTime(), TimeSpan.Zero);
            return Math.Abs((actual - expected.ToUniversalTime()).TotalMilliseconds) < 1.0;
        }
        catch (ArgumentException)
        {
            return false;
        }
        catch (InvalidOperationException)
        {
            return false;
        }
    }

    private static string HashDataRoot(string dataRoot)
    {
        var normalized = Path.GetFullPath(dataRoot).ToLowerInvariant();
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(normalized))).ToLowerInvariant();
    }

    private void WriteMetadata()
    {
        var json = JsonSerializer.Serialize(_metadata, new JsonSerializerOptions { WriteIndented = true });
        var temp = _metadataPath + ".tmp";
        File.WriteAllText(temp, json, new UTF8Encoding(false));
        File.Move(temp, _metadataPath, overwrite: true);
    }

    private void EnsureOwned()
    {
        if (!_owned)
        {
            throw new ObjectDisposedException(nameof(WorkspaceLease));
        }
    }

    public void Dispose()
    {
        if (!_owned)
        {
            return;
        }
        try
        {
            var current = JsonSerializer.Deserialize<LeaseMetadata>(File.ReadAllText(_metadataPath));
            if (current?.InstanceId == _metadata.InstanceId)
            {
                Directory.Delete(_lockDirectory, recursive: true);
            }
        }
        catch (IOException)
        {
            // Best-effort release. A stale host-PID lease is recovered on next startup.
        }
        finally
        {
            _owned = false;
        }
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateDirectoryW(string lpPathName, IntPtr lpSecurityAttributes);

    private sealed class LeaseMetadata
    {
        [JsonPropertyName("schema_version")] public int SchemaVersion { get; init; }
        [JsonPropertyName("pid")] public int Pid { get; init; }
        [JsonPropertyName("port")] public int Port { get; set; }
        [JsonPropertyName("version")] public string Version { get; init; }
        [JsonPropertyName("release_id")] public string ReleaseId { get; init; }
        [JsonPropertyName("instance_id")] public string InstanceId { get; init; }
        [JsonPropertyName("session_id")] public string SessionId { get; init; }
        [JsonPropertyName("edition")] public string Edition { get; init; }
        [JsonPropertyName("started_at")] public string StartedAt { get; init; }
        [JsonPropertyName("process_started_at_utc")] public string? ProcessStartedAtUtc { get; init; }
        [JsonPropertyName("hostname")] public string Hostname { get; init; }
        [JsonPropertyName("data_dir")] public string DataDir { get; init; }
        [JsonPropertyName("data_root_hash")] public string DataRootHash { get; init; }

        [JsonConstructor]
        public LeaseMetadata(int schemaVersion, int pid, int port, string version, string releaseId,
            string instanceId, string sessionId, string edition, string startedAt, string? processStartedAtUtc,
            string hostname, string dataDir, string dataRootHash)
        {
            SchemaVersion = schemaVersion;
            Pid = pid;
            Port = port;
            Version = version;
            ReleaseId = releaseId;
            InstanceId = instanceId;
            SessionId = sessionId;
            Edition = edition;
            StartedAt = startedAt;
            ProcessStartedAtUtc = processStartedAtUtc;
            Hostname = hostname;
            DataDir = dataDir;
            DataRootHash = dataRootHash;
        }
    }
}
