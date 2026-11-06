using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace SRW.Desktop.Runtime;

public sealed class RuntimeApiClient : IDisposable
{
    private readonly HttpClient _client;
    private readonly string _sessionToken;
    private IReadOnlyList<Cookie> _browserCookies = Array.Empty<Cookie>();

    public IReadOnlyList<Cookie> BrowserCookies => _browserCookies;

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

    // Only the native Host control client can call this route. The lifecycle
    // secret is never placed in a WebView2 Cookie, URL, JavaScript or log.
    // A 404 is the legacy/default-OFF Core: retain existing WPF behavior.
    public async Task AttachBusinessSessionIfAvailableAsync(
        CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(
            HttpMethod.Post, "/api/v1/runtime/host-business-attach");
        // Never send the raw lifecycle secret to an unverified listener. The
        // HMAC is scoped to this attach use case and uses a fresh 256-bit nonce.
        var nonce = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
        var proof = HMACSHA256.HashData(
            Encoding.ASCII.GetBytes(_sessionToken),
            Encoding.ASCII.GetBytes("srw-host-attach-v1:" + nonce));
        request.Headers.Add("X-SRW-Host-Nonce", nonce);
        request.Headers.Add("X-SRW-Host-Proof", Convert.ToHexString(proof).ToLowerInvariant());
        using var response = await _client.SendAsync(request, cancellationToken);
        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            return;
        }
        response.EnsureSuccessStatusCode();
        if (!response.Headers.TryGetValues("Set-Cookie", out var values))
        {
            throw new InvalidDataException("Host attach returned no business Cookies.");
        }
        var headers = values.ToArray();
        if (headers.Length != 2)
        {
            throw new InvalidDataException("Host attach returned an invalid Cookie count.");
        }
        var jar = new CookieContainer();
        foreach (var header in headers)
        {
            jar.SetCookies(_client.BaseAddress!, header);
        }
        var cookies = jar.GetCookies(_client.BaseAddress!).Cast<Cookie>().ToArray();
        var business = cookies.SingleOrDefault(c => c.Name == "srw_business_session");
        var csrf = cookies.SingleOrDefault(c => c.Name == "srw_csrf");
        if (cookies.Length != 2 || business is null || csrf is null
            || !business.HttpOnly || csrf.HttpOnly || business.Path != "/"
            || csrf.Path != "/" || business.Secure || csrf.Secure
            || !business.Value.StartsWith("srw1.", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(csrf.Value))
        {
            throw new InvalidDataException("Host attach returned invalid Cookie attributes.");
        }
        _browserCookies = new[] { business, csrf };
    }

    public async Task<RuntimeIdentity> GetInfoAsync(CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/v1/runtime/info");
        if (_browserCookies.Count != 0)
        {
            request.Headers.TryAddWithoutValidation("Cookie", string.Join("; ",
                _browserCookies.Select(c => c.Name + "=" + c.Value)));
        }
        using var response = await _client.SendAsync(request, cancellationToken);
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
