using System.Net;
using System.Net.Sockets;

namespace SRW.Desktop.Runtime;

public static class PortAllocator
{
    public static int AllocateLoopback()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        return ((IPEndPoint)listener.LocalEndpoint).Port;
    }
}
