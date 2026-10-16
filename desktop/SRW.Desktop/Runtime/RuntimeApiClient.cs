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
        _client = new HttpClient
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
