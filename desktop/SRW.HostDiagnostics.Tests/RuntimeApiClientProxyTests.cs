using System.Net;
using System.Net.Sockets;
using System.Text;
using SRW.Desktop.Runtime;

namespace SRW.HostDiagnostics.Tests;

/// <summary>
/// #171 regression: .NET HttpClient inherits HTTP_PROXY/HTTPS_PROXY/ALL_PROXY from
/// the environment. With a proxy configured and NO_PROXY empty, the Host's loopback
/// control plane was sent to that proxy, /api/v1/runtime/ready never answered and the
/// WPF window never appeared. The acceptance here is deliberately hostile: a real
/// loopback stub plus an unreachable proxy, so a regression fails instead of passing
/// on a machine that happens to have no proxy at all.
/// </summary>
internal static class RuntimeApiClientProxyTests
{
    private const string UnreachableProxy = "http://127.0.0.1:1";

    private static readonly string[] ProxyVariables =
    {
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    };

    internal static async Task RunAsync()
    {
        var saved = ProxyVariables.ToDictionary(name => name, Environment.GetEnvironmentVariable);
        using var stub = LoopbackControlPlaneStub.Start();
        try
        {
            // Reproduce the machine state rather than clearing it: unreachable proxy,
            // empty NO_PROXY. Only this client's own configuration may save us.
            foreach (var name in ProxyVariables)
            {
                Environment.SetEnvironmentVariable(name, null);
            }
            foreach (var name in new[] {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                                        "http_proxy", "https_proxy", "all_proxy"})
            {
                Environment.SetEnvironmentVariable(name, UnreachableProxy);
            }
            Environment.SetEnvironmentVariable("NO_PROXY", string.Empty);

            // Control probe: prove the environment really is poisonous in this
            // process, otherwise the assertion below could pass for the wrong reason.
            var proxyActuallyUsed = false;
            try
            {
                using var plain = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
                using var _ = await plain.GetAsync(stub.ReadyUrl);
            }
            catch (HttpRequestException)
            {
                proxyActuallyUsed = true;
            }
            if (!proxyActuallyUsed)
            {
                throw new InvalidOperationException(
                    "proxy control probe did not fail: this runtime ignores HTTP_PROXY, "
                    + "so the loopback acceptance below would prove nothing");
            }

            using var client = new RuntimeApiClient(stub.Port, "session-token-under-test");
            await client.WaitUntilReadyAsync(TimeSpan.FromSeconds(5));
            var identity = await client.GetInfoAsync();
            if (identity.InstanceId != "instance-under-test")
            {
                throw new InvalidOperationException("loopback /info identity was not parsed");
            }
            await client.RequestShutdownAsync();
            if (stub.ShutdownRequests != 1)
            {
                throw new InvalidOperationException("loopback /shutdown was not delivered");
            }
        }
        finally
        {
            foreach (var (name, value) in saved)
            {
                Environment.SetEnvironmentVariable(name, value);
            }
        }

        Console.WriteLine("PASS: loopback control plane reachable while an unreachable "
            + "HTTP_PROXY is set and NO_PROXY is empty (#171)");
    }

    /// <summary>Minimal HTTP/1.1 stub over TcpListener: no HTTP.sys URL ACL needed.</summary>
    private sealed class LoopbackControlPlaneStub : IDisposable
    {
        private readonly TcpListener _listener;
        private readonly CancellationTokenSource _stop = new();
        private readonly Task _accepting;
        private int _shutdownRequests;

        private LoopbackControlPlaneStub(TcpListener listener)
        {
            _listener = listener;
            _accepting = AcceptAsync();
        }

        internal int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;

        internal string ReadyUrl => $"http://127.0.0.1:{Port}/api/v1/runtime/ready";

        internal int ShutdownRequests => Volatile.Read(ref _shutdownRequests);

        internal static LoopbackControlPlaneStub Start()
        {
            var listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            return new LoopbackControlPlaneStub(listener);
        }

        private async Task AcceptAsync()
        {
            while (!_stop.IsCancellationRequested)
            {
                TcpClient connection;
                try
                {
                    connection = await _listener.AcceptTcpClientAsync(_stop.Token);
                }
                catch (Exception)
                {
                    return;
                }
                _ = Task.Run(() => ServeAsync(connection));
            }
        }

        private async Task ServeAsync(TcpClient connection)
        {
            using (connection)
            {
                var stream = connection.GetStream();
                using var reader = new StreamReader(stream, Encoding.ASCII, false, 1024, true);
                var requestLine = await reader.ReadLineAsync();
                while (!string.IsNullOrEmpty(await reader.ReadLineAsync()))
                {
                    // Drain headers; the stub never needs their content.
                }

                var target = requestLine?.Split(' ') is { Length: >= 2 } parts ? parts[1] : "/";
                var isShutdown = target.EndsWith("/runtime/shutdown", StringComparison.Ordinal);
                var body = isShutdown
                    ? "{}"
                    : target.EndsWith("/runtime/info", StringComparison.Ordinal)
                        ? "{\"product\":\"Synthetic Recruitment Workbench\",\"version\":\"test-only\","
                          + "\"runtime\":\"stub\",\"edition\":\"windows\",\"instanceId\":\"instance-under-test\","
                          + "\"releaseId\":\"release-under-test\",\"sessionId\":\"session-under-test\"}"
                        : "{\"status\":\"ready\"}";
                if (isShutdown)
                {
                    Interlocked.Increment(ref _shutdownRequests);
                }

                var payload = Encoding.UTF8.GetBytes(body);
                var head = Encoding.ASCII.GetBytes(
                    $"HTTP/1.1 {(isShutdown ? "202 Accepted" : "200 OK")}\r\n"
                    + "Content-Type: application/json\r\n"
                    + $"Content-Length: {payload.Length}\r\nConnection: close\r\n\r\n");
                await stream.WriteAsync(head);
                await stream.WriteAsync(payload);
                await stream.FlushAsync();
            }
        }

        public void Dispose()
        {
            _stop.Cancel();
            _listener.Stop();
            try
            {
                _accepting.Wait(TimeSpan.FromSeconds(2));
            }
            catch (AggregateException)
            {
                // Shutdown of the accept loop is best effort by design.
            }
            _stop.Dispose();
        }
    }
}
