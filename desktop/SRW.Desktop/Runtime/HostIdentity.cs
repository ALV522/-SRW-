using System.Security.Cryptography;

namespace SRW.Desktop.Runtime;

public sealed record HostIdentity(string InstanceId, string SessionId, string SessionToken)
{
    public static HostIdentity Create() => new(
        $"instance-{Guid.NewGuid():N}",
        $"session-{Guid.NewGuid():N}",
        Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant());
}
