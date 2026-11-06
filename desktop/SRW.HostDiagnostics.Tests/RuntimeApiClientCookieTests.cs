using System.Net;
using System.Net.Sockets;
using System.Text;
using SRW.Desktop.Runtime;

namespace SRW.HostDiagnostics.Tests;

/// <summary>Real loopback HTTP: Host ON must send exactly one explicit Cookie
/// header after attach, without automatic CookieContainer replay.</summary>
internal static class RuntimeApiClientCookieTests
{
    private const string Lifecycle = "synthetic-lifecycle-only";
    private const string Business = "srw1.synthetic.session";
    private const string Csrf = "synthetic-csrf";

    internal static async Task RunAsync()
    {
        using var server = new CookieStub();
        using var client = new RuntimeApiClient(server.Port, Lifecycle);
        await client.AttachBusinessSessionIfAvailableAsync();
        if (client.BrowserCookies.Count != 2)
            throw new InvalidOperationException("Host did not retain two validated cookies");
        var identity = await client.GetInfoAsync();
        await server.CompleteAsync();
        if (identity.InstanceId != "synthetic-instance")
            throw new InvalidOperationException("Host identity mismatch");
        if (server.AttachCookies.Length != 0 || server.InfoCookies.Length != 1)
            throw new InvalidOperationException("Host Cookie header count invalid");
        var header = server.InfoCookies[0];
        if (Count(header, "srw_business_session=") != 1
            || Count(header, "srw_csrf=") != 1
            || !header.Contains(Business, StringComparison.Ordinal)
            || !header.Contains(Csrf, StringComparison.Ordinal)
            || header.Contains(Lifecycle, StringComparison.Ordinal))
            throw new InvalidOperationException("Host business Cookie duplicated or contaminated");
        Console.WriteLine("PASS: Host business cookies are explicit, unique and isolated");
    }

    private static int Count(string text, string part)
    {
        var count = 0;
        var index = 0;
        while ((index = text.IndexOf(part, index, StringComparison.Ordinal)) >= 0)
        {
            count++;
            index += part.Length;
        }
        return count;
    }

    private sealed class CookieStub : IDisposable
    {
        private readonly TcpListener _listener;
        private readonly CancellationTokenSource _stop = new();
        private readonly Task _serving;
        internal string[] AttachCookies { get; private set; } = [];
        internal string[] InfoCookies { get; private set; } = [];
        internal int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;

        internal CookieStub()
        {
            _listener = new TcpListener(IPAddress.Loopback, 0);
            _listener.Start();
            _serving = ServeAsync();
        }

        private async Task ServeAsync()
        {
            for (var i = 0; i < 2; i++)
            {
                using var connection = await _listener.AcceptTcpClientAsync(_stop.Token);
                var stream = connection.GetStream();
                using var reader = new StreamReader(stream, Encoding.ASCII, false, 1024, true);
                var request = await reader.ReadLineAsync() ?? "";
                var headers = new List<string>();
                string? line;
                while (!string.IsNullOrEmpty(line = await reader.ReadLineAsync()))
                    headers.Add(line);
                var cookies = headers.Where(h => h.StartsWith("Cookie:", StringComparison.OrdinalIgnoreCase)).ToArray();
                string body;
                string extra = "";
                if (request.Contains("/host-business-attach", StringComparison.Ordinal))
                {
                    AttachCookies = cookies;
                    body = "{\"status\":\"attached\"}";
                    extra = "Set-Cookie: srw_business_session=" + Business
                        + "; Path=/; HttpOnly; SameSite=Strict\r\n"
                        + "Set-Cookie: srw_csrf=" + Csrf + "; Path=/; SameSite=Strict\r\n";
                }
                else if (request.Contains("/runtime/info", StringComparison.Ordinal))
                {
                    InfoCookies = cookies;
                    body = "{\"product\":\"Synthetic\",\"version\":\"test\",\"runtime\":\"desktop\","
                        + "\"edition\":\"windows\",\"instanceId\":\"synthetic-instance\","
                        + "\"releaseId\":\"synthetic-release\",\"sessionId\":\"synthetic-session\"}";
                }
                else throw new InvalidOperationException("Unexpected control-plane request");
                var payload = Encoding.UTF8.GetBytes(body);
                var response = Encoding.ASCII.GetBytes(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    + extra + "Content-Length: " + payload.Length
                    + "\r\nConnection: close\r\n\r\n");
                await stream.WriteAsync(response);
                await stream.WriteAsync(payload);
                await stream.FlushAsync();
            }
        }

        internal Task CompleteAsync() => _serving;
        public void Dispose()
        {
            _stop.Cancel();
            _listener.Stop();
            _stop.Dispose();
        }
    }
}
