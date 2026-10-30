using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;

namespace SRW.Desktop.Runtime;

public sealed class RuntimeApiClient : IDisposable
{
    private readonly HttpClient _client;
    private readonly string _sessionToken;

    public RuntimeApiClient(int port, string sessionToken)
    {
        // The control plane is strictly loopback (127.0.0.1). Two ambient defaults
        // are wrong for it:
        //   1. HttpClientHandler inherits HTTP_PROXY/HTTPS_PROXY/ALL_PROXY, so on a
        //      machine with a corporate proxy and no NO_PROXY entry every
        //      /api/v1/runtime/* call is sent to that proxy: ready/info fail, the
        //      Host gives up after its retries and the window never opens (#171).
        //   2. It follows redirects by default. .NET only drops Authorization on a
        //      cross-origin hop; a custom header such as X-SRW-Session would be
        //      copied to the redirect target, i.e. the lifecycle token would leave
        //      the loopback control plane on a single 302.
        // Both are scoped to this one loopback client: provider/AI traffic and every
        // other outbound call keep the ambient proxy and redirect behaviour.
        var handler = new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false };
        _client = new HttpClient(handler)
        {
            BaseAddress = new Uri($"http://127.0.0.1:{port}"),
            Timeout = TimeSpan.FromSeconds(3),
        };
        _sessionToken = sessionToken;
    }

    public async Task WaitUntilReadyAsync(TimeSpan timeout, CancellationToken cancellationToken = default)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        Exception? last = null;
        while (DateTimeOffset.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                using var response = await _client.GetAsync("/api/v1/runtime/ready", cancellationToken);
                // A redirect is never legitimate for a loopback control plane, and
                // retrying it until the deadline would hide the anomaly behind a
                // timeout. Fail closed on the first one instead.
                if ((int)response.StatusCode is >= 300 and < 400)
                {
                    throw new InvalidOperationException(
                        "Backend /api/v1/runtime/ready answered with a redirect; "
                        + "the loopback control plane never follows one.");
                }
                if (response.StatusCode == HttpStatusCode.OK)
                {
                    using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken));
                    if (doc.RootElement.TryGetProperty("status", out var status) && status.GetString() == "ready")
                    {
                        return;
                    }
                }
            }
            catch (Exception exc) when (exc is HttpRequestException or TaskCanceledException)
            {
                last = exc;
            }
            await Task.Delay(200, cancellationToken);
        }
        throw new TimeoutException("Backend /api/v1/runtime/ready did not become ready before timeout.", last);
    }

    public async Task<RuntimeIdentity> GetInfoAsync(CancellationToken cancellationToken = default)
    {
        using var response = await _client.GetAsync("/api/v1/runtime/info", cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<RuntimeIdentity>(cancellationToken: cancellationToken)
            ?? throw new InvalidDataException("Runtime /info returned an empty identity payload.");
    }

    public async Task RequestShutdownAsync(CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/runtime/shutdown");
        request.Headers.Add("X-SRW-Session", _sessionToken);
        using var response = await _client.SendAsync(request, cancellationToken);
        if (response.StatusCode is not HttpStatusCode.Accepted and not HttpStatusCode.Conflict)
        {
            response.EnsureSuccessStatusCode();
        }
    }

    public void Dispose() => _client.Dispose();
}
