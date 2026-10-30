using System.Net;
using System.Net.Sockets;
using System.Text;
using SRW.Desktop.Runtime;

namespace SRW.HostDiagnostics.Tests;

/// <summary>
/// #171 follow-up: the control plane is loopback-only and carries the lifecycle
/// token in X-SRW-Session. HttpClientHandler follows redirects by default and .NET
/// only strips Authorization on a cross-origin hop, not custom headers - so a single
/// 302 from the backend would hand the token to whatever host the Location names.
/// These tests pin the closed behaviour: a redirect is refused locally, the second
/// listener sees zero requests, and the token never travels.
/// </summary>
internal static class RuntimeApiClientRedirectTests
{
    private const string Token = "session-token-must-not-leak";

    internal static async Task RunAsync()
    {
        using var sink = RecordingListener.Start();
        using var control = RedirectingListener.Start(sink.Port);

        // 1. Shutdown carries the token. A 302 here is the realistic leak path.
        using (var client = new RuntimeApiClient(control.Port, Token))
        {
            var refused = false;
            try
            {
                await client.RequestShutdownAsync();
            }
            catch (HttpRequestException)
            {
                refused = true;
            }
            Expect(refused, "a 302 on /runtime/shutdown must be refused, not followed");
        }

        // 2. The ready probe must fail closed instead of spinning to its timeout.
        using (var client = new RuntimeApiClient(control.Port, Token))
        {
            var failedFast = false;
            var started = DateTime.UtcNow;
            try
            {
                await client.WaitUntilReadyAsync(TimeSpan.FromSeconds(8));
            }
            catch (InvalidOperationException)
            {
                failedFast = (DateTime.UtcNow - started) < TimeSpan.FromSeconds(4);
            }
            Expect(failedFast, "a redirect on /runtime/ready must fail closed, not time out");
        }

        // Give any (buggy) followed request time to arrive before asserting zero.
        await Task.Delay(400);
        Expect(sink.RequestCount == 0,
            $"redirect target received {sink.RequestCount} request(s); the token would have leaked");
        Expect(!sink.SawToken(Token), "the lifecycle token reached the redirect target");

        Console.WriteLine("PASS: control plane refuses redirects; second listener saw 0 requests "
            + "and 0 lifecycle tokens (#171)");
    }

    private static void Expect(bool value, string reason)
    {
        if (!value) throw new InvalidOperationException(reason);
    }

    /// <summary>Answers every request with a 302 pointing at the recording sink.</summary>
    private sealed class RedirectingListener : IDisposable
    {
        private readonly TcpListener _listener;
        private readonly CancellationTokenSource _stop = new();
        private readonly Task _accepting;
        private readonly int _sinkPort;

        private RedirectingListener(TcpListener listener, int sinkPort)
        {
            _listener = listener;
            _sinkPort = sinkPort;
            _accepting = AcceptAsync();
        }

        internal int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;

        internal static RedirectingListener Start(int sinkPort)
        {
            var listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            return new RedirectingListener(listener, sinkPort);
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
                await DrainAsync(stream);
                var head = Encoding.ASCII.GetBytes(
                    "HTTP/1.1 302 Found\r\n"
                    + $"Location: http://127.0.0.1:{_sinkPort}/collect\r\n"
                    + "Content-Length: 0\r\nConnection: close\r\n\r\n");
                await stream.WriteAsync(head);
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
                // Accept loop teardown is best effort by design.
            }
            _stop.Dispose();
        }
    }

    /// <summary>Records anything that reaches it; it must stay empty.</summary>
    private sealed class RecordingListener : IDisposable
    {
        private readonly TcpListener _listener;
        private readonly CancellationTokenSource _stop = new();
        private readonly Task _accepting;
        private readonly StringBuilder _seen = new();
        private int _requests;

        private RecordingListener(TcpListener listener)
        {
            _listener = listener;
            _accepting = AcceptAsync();
        }

        internal int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;

        internal int RequestCount => Volatile.Read(ref _requests);

        internal static RecordingListener Start()
        {
            var listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            return new RecordingListener(listener);
        }

        internal bool SawToken(string token)
        {
            lock (_seen)
            {
                return _seen.ToString().Contains(token, StringComparison.Ordinal);
            }
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
                Interlocked.Increment(ref _requests);
                var stream = connection.GetStream();
                var text = await DrainAsync(stream);
                lock (_seen)
                {
                    _seen.Append(text);
                }
                var body = Encoding.ASCII.GetBytes("{}");
                var head = Encoding.ASCII.GetBytes(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    + $"Content-Length: {body.Length}\r\nConnection: close\r\n\r\n");
                await stream.WriteAsync(head);
                await stream.WriteAsync(body);
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
                // Accept loop teardown is best effort by design.
            }
            _stop.Dispose();
        }
    }

    private static async Task<string> DrainAsync(NetworkStream stream)
    {
        var buffer = new byte[4096];
        using var memory = new MemoryStream();
        var deadline = DateTime.UtcNow.AddSeconds(2);
        while (DateTime.UtcNow < deadline)
        {
            var read = await stream.ReadAsync(buffer);
            if (read <= 0)
            {
                break;
            }
            memory.Write(buffer, 0, read);
            var text = Encoding.ASCII.GetString(memory.ToArray());
            if (text.Contains("\r\n\r\n", StringComparison.Ordinal))
            {
                break;
            }
        }
        return Encoding.ASCII.GetString(memory.ToArray());
    }
}
