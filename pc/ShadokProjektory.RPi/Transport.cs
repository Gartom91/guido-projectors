using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;

namespace ShadokProjektory.RPi;

internal static class Transport
{
    public static async Task<JsonElement> Request(Settings settings, string action, string target = "all")
    {
        settings.Validate();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(150));
        using var tcp = new TcpClient();
        await tcp.ConnectAsync(settings.RpiHost, settings.RpiPort, timeout.Token);
        using var tls = new SslStream(tcp.GetStream(), leaveInnerStreamOpen: false,
            (_, certificate, _, _) =>
            {
                if (certificate is null) return false;
                using var current = X509CertificateLoader.LoadCertificate(certificate.GetRawCertData());
                string actual = Convert.ToHexString(SHA256.HashData(current.RawData));
                return CryptographicOperations.FixedTimeEquals(
                    Encoding.ASCII.GetBytes(actual), Encoding.ASCII.GetBytes(settings.CertificateSha256))
                    && current.NotBefore.ToUniversalTime() <= DateTime.UtcNow
                    && current.NotAfter.ToUniversalTime() >= DateTime.UtcNow;
            });
        await tls.AuthenticateAsClientAsync(new SslClientAuthenticationOptions
        {
            TargetHost = settings.RpiHost,
            EnabledSslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13,
            CertificateRevocationCheckMode = X509RevocationMode.NoCheck
        }, timeout.Token);
        byte[] request = JsonSerializer.SerializeToUtf8Bytes(new { v = 1, token = settings.Token, action, target });
        await tls.WriteAsync(request, timeout.Token);
        await tls.WriteAsync(new byte[] { 10 }, timeout.Token);
        await tls.FlushAsync(timeout.Token);
        // Bound the frame before decoding; ReadLineAsync alone permits unlimited allocation.
        using var frame = new MemoryStream();
        byte[] buffer = new byte[1024];
        bool completed = false;
        while (!completed)
        {
            int read = await tls.ReadAsync(buffer, timeout.Token);
            if (read == 0) throw new IOException("RPi zamknęło połączenie przed wysłaniem odpowiedzi.");
            int newline = Array.IndexOf(buffer, (byte)10, 0, read);
            int count = newline >= 0 ? newline : read;
            if (frame.Length + count > 16384) throw new IOException("Zbyt długa odpowiedź RPi.");
            frame.Write(buffer, 0, count);
            completed = newline >= 0;
        }
        using var document = JsonDocument.Parse(frame.ToArray());
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("v", out var version)
            || version.GetInt32() != 1 || !root.TryGetProperty("ok", out var ok)
            || ok.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new JsonException("Nieprawidłowa odpowiedź protokołu RPi.");
        return root.Clone();
    }

    public static async Task SendUdp(string host, int port, string text)
    {
        if (string.IsNullOrWhiteSpace(host))
            throw new ArgumentException("Najpierw skonfiguruj adres odbiornika UDP w ustawieniach.");
        using var udp = new UdpClient();
        byte[] payload = Encoding.UTF8.GetBytes(text);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        int sent = await udp.SendAsync(payload, host, port, timeout.Token);
        if (sent != payload.Length) throw new IOException("Niepełne wysłanie datagramu UDP.");
    }

    public static string FireCommand(bool on) => on
        ? "Output 1 On; Output 2 On; Output 3 On;"
        : "Output 1 Off; Output 2 Off; Output 3 Off;";

    public static string AuxiliaryCommand(bool cutPower) => cutPower ? "Output 8 On;" : "Output 8 Off;";
}
