using System.Diagnostics;
using SRW.Desktop.Diagnostics;
using SRW.Desktop.Runtime;

namespace SRW.Desktop.Hosting;

public sealed class BackendProcess : IDisposable
{
    private readonly Process _process;
    private readonly BackendJob _job;
    private readonly HostLog _log;

    private BackendProcess(Process process, BackendJob job, HostLog log)
    {
        _process = process;
        _job = job;
        _log = log;
    }

    public bool HasExited => _process.HasExited;
    public int Id => _process.Id;

    public static BackendProcess Start(
        AppPaths paths,
        HostIdentity identity,
        string releaseId,
        int port,
        HostLog log)
    {
        var arguments = $"\"scripts/run_local.py\" --host 127.0.0.1 --port {port} --edition windows --workspace-lock host";
        var start = new ProcessStartInfo
        {
            FileName = paths.PythonExe,
            Arguments = arguments,
            WorkingDirectory = paths.ApplicationRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        start.Environment["RECRUITMENT_DATA_DIR"] = paths.UserDataRoot;
        start.Environment["RECRUITMENT_FRONTEND_DIST"] = paths.FrontendDist;
        start.Environment["RECRUITMENT_KNOWLEDGE_DIR"] = paths.KnowledgeRoot;
        start.Environment["RECRUITMENT_EDITION"] = "windows";
        start.Environment["RECRUITMENT_RUNTIME_MODE"] = "desktop";
        start.Environment["RECRUITMENT_INSTANCE_ID"] = identity.InstanceId;
        start.Environment["RECRUITMENT_SESSION_ID"] = identity.SessionId;
        start.Environment["RECRUITMENT_SESSION_TOKEN"] = identity.SessionToken;
        start.Environment["RECRUITMENT_RELEASE_ID"] = releaseId;

        var process = new Process { StartInfo = start, EnableRaisingEvents = true };
        process.OutputDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) log.Write("backend_stdout", new { line = e.Data }); };
        process.ErrorDataReceived += (_, e) => { if (!string.IsNullOrWhiteSpace(e.Data)) log.Write("backend_stderr", new { line = e.Data }); };
        if (!process.Start())
        {
            throw new InvalidOperationException("Embedded Python backend process did not start.");
        }
        var job = new BackendJob();
        try
        {
            job.Assign(process);
        }
        catch
        {
            process.Kill(entireProcessTree: true);
            job.Dispose();
            process.Dispose();
            throw;
        }
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        return new BackendProcess(process, job, log);
    }

    public async Task<bool> WaitForExitAsync(TimeSpan timeout)
    {
        if (_process.HasExited)
        {
            return true;
        }
        using var cts = new CancellationTokenSource(timeout);
        try
        {
            await _process.WaitForExitAsync(cts.Token);
            return true;
        }
        catch (OperationCanceledException)
        {
            return _process.HasExited;
        }
    }

    public void KillBoundedFallback()
    {
        if (!_process.HasExited)
        {
            _log.Write("backend_force_kill");
            _process.Kill(entireProcessTree: true);
        }
    }

    public void Dispose()
    {
        _process.Dispose();
        _job.Dispose();
    }
}
