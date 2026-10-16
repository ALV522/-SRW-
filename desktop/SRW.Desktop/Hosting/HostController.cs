using SRW.Desktop.Contracts;
using SRW.Desktop.Diagnostics;
using SRW.Desktop.Runtime;
using SRW.Desktop.Workspace;

namespace SRW.Desktop.Hosting;

public sealed class HostController
{
    private const int MaxBackendStartAttempts = 3;
    private readonly HostIdentity _identity;
    private readonly BuildInfo _build;
    private readonly HostLog _log;
    private WorkspaceLease? _lease;
    private BackendProcess? _backend;
    private RuntimeApiClient? _runtime;
    private int _port;
    private string? _backendSessionId;
    private bool _stopped;

    public HostController(AppPaths paths)
    {
        Paths = paths;
        _identity = HostIdentity.Create();
        _build = BuildInfo.Load(paths.ApplicationRoot);
        _log = new HostLog(Path.Combine(paths.LogRoot, "host.log"), () => new
        {
            release_id = _build.ReleaseId,
            host_session_id = _identity.SessionId,
            backend_session_id = _backendSessionId,
            instance_id = _identity.InstanceId,
            edition = "windows",
            port = _port,
        });
    }

    public AppPaths Paths { get; }
    public Uri ApplicationUri => new($"http://127.0.0.1:{_port}/");

    public async Task StartAsync()
    {
        _log.Write("host_started", new { version = _build.Version });
        _log.Write("paths_resolved", new { application_root = Paths.ApplicationRoot, user_data_root = Paths.UserDataRoot });
        _lease = WorkspaceLease.Acquire(
            Paths.UserDataRoot,
            port: 0,
            version: _build.Version,
            releaseId: _build.ReleaseId,
            instanceId: _identity.InstanceId,
            sessionId: _identity.SessionId);
        _log.Write("workspace_lock_acquired");

        Exception? lastError = null;
        for (var attempt = 1; attempt <= MaxBackendStartAttempts; attempt++)
        {
            _port = PortAllocator.AllocateLoopback();
            _lease.UpdatePort(_port);
            _log.Write("port_allocated", new { attempt });

            try
            {
                _backend = BackendProcess.Start(Paths, _identity, _build.ReleaseId, _port, _log);
                _log.Write("backend_process_started", new { pid = _backend.Id, attempt });
                _runtime = new RuntimeApiClient(_port, _identity.SessionToken);

                using var attemptCts = new CancellationTokenSource();
                var readyTask = _runtime.WaitUntilReadyAsync(TimeSpan.FromSeconds(20), attemptCts.Token);
                var exitedTask = _backend.WaitForExitAsync(TimeSpan.FromSeconds(20));
                var completed = await Task.WhenAny(readyTask, exitedTask);
                if (completed == exitedTask && await exitedTask)
                {
                    attemptCts.Cancel();
                    try
                    {
                        await readyTask;
                    }
                    catch (OperationCanceledException)
                    {
                        // Expected: the backend already exited, so stop the readiness poll immediately.
                    }
                    throw new InvalidOperationException($"Backend exited before readiness on port {_port}.");
                }

                await readyTask;
                var info = await _runtime.GetInfoAsync();
                ValidateRuntimeIdentity(info);
                _backendSessionId = info.SessionId;
                _log.Write("backend_ready", new { backend_session_id = info.SessionId, runtime = info.Runtime, attempt });
                return;
            }
            catch (RuntimeIdentityMismatchException exc)
            {
                await CleanupFailedAttemptAsync();
                _log.Write("backend_start_non_retryable", new
                {
                    attempt,
                    port = _port,
                    error = exc.GetType().Name,
                    message = exc.Message,
                });
                throw;
            }
            catch (Exception exc)
            {
                lastError = exc;
                await CleanupFailedAttemptAsync();

                if (attempt < MaxBackendStartAttempts)
                {
                    _log.Write("backend_start_retry", new
                    {
                        attempt,
                        next_attempt = attempt + 1,
                        port = _port,
                        error = exc.GetType().Name,
                        message = exc.Message,
                    });
                    await Task.Delay(TimeSpan.FromMilliseconds(150));
                }
            }
        }

        throw new InvalidOperationException(
            $"Backend failed to become ready after {MaxBackendStartAttempts} attempts.",
            lastError);
    }

    private void ValidateRuntimeIdentity(RuntimeIdentity info)
    {
        var mismatches = new List<string>();
        if (info.Version != _build.Version) mismatches.Add($"version={info.Version}");
        if (info.ReleaseId != _build.ReleaseId) mismatches.Add($"releaseId={info.ReleaseId}");
        if (info.InstanceId != _identity.InstanceId) mismatches.Add($"instanceId={info.InstanceId}");
        if (info.SessionId != _identity.SessionId) mismatches.Add($"sessionId={info.SessionId}");
        if (info.Edition != "windows") mismatches.Add($"edition={info.Edition}");
        if (info.Runtime != "desktop") mismatches.Add($"runtime={info.Runtime}");
        if (mismatches.Count > 0)
        {
            throw new RuntimeIdentityMismatchException("Runtime identity validation failed: " + string.Join(", ", mismatches));
        }
    }

    private async Task CleanupFailedAttemptAsync()
    {
        _runtime?.Dispose();
        _runtime = null;
        if (_backend is null)
        {
            return;
        }
        if (!_backend.HasExited)
        {
            _backend.KillBoundedFallback();
        }
        await _backend.WaitForExitAsync(TimeSpan.FromSeconds(3));
        _backend.Dispose();
        _backend = null;
    }

    private sealed class RuntimeIdentityMismatchException(string message) : InvalidOperationException(message);

    public void LogEvent(string eventName, object? details = null) => _log.Write(eventName, details);

    public async Task StopAsync()
    {
        if (_stopped)
        {
            return;
        }
        _stopped = true;
        _log.Write("shutdown_requested");
        try
        {
            if (_runtime is not null && _backend is not null && !_backend.HasExited)
            {
                try
                {
                    await _runtime.RequestShutdownAsync();
                }
                catch (Exception exc)
                {
                    _log.Write("shutdown_request_failed", new { error = exc.GetType().Name, message = exc.Message });
                }
                if (!await _backend.WaitForExitAsync(TimeSpan.FromSeconds(12)))
                {
                    _backend.KillBoundedFallback();
                    await _backend.WaitForExitAsync(TimeSpan.FromSeconds(3));
                }
            }
            _log.Write("backend_stopped");
        }
        finally
        {
            _runtime?.Dispose();
            _backend?.Dispose();
            _lease?.Dispose();
            _log.Write("workspace_released");
            _log.Write("host_closed");
        }
    }
}
