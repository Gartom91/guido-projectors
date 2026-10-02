using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;

namespace ShadokProjektory.RPi;

internal static class SelfTest
{
    public static async Task<int> Run(string[] args)
    {
        string output = args.Length > 1 ? args[1] : "self-test.json";
        var passed = new List<string>();
        try
        {
            if (args[0] == "--udp-test")
            {
                if (args.Length != 4) throw new ArgumentException("--udp-test output.json host port");
                foreach (string command in new[] { Transport.FireCommand(true), Transport.FireCommand(false), "reconnect", Transport.AuxiliaryCommand(true), Transport.AuxiliaryCommand(false) })
                    await Transport.SendUdp(args[2], int.Parse(args[3]), command);
                passed.Add("Five original UDP payloads handed to the network stack; verify at external receiver");
            }
            else if (args[0] == "--integration-test")
            {
                if (args.Length != 3) throw new ArgumentException("--integration-test output.json settings.json");
                var settings = Settings.Load(args[2]);
                if (settings.RpiHost != "127.0.0.1") throw new ArgumentException("Test integracyjny wymaga serwera symulacyjnego na 127.0.0.1.");
                foreach (string action in new[] { "status", "on", "off" })
                {
                    JsonElement result = await Transport.Request(settings, action);
                    if (!result.GetProperty("ok").GetBoolean()) throw new Exception(result.ToString());
                    passed.Add("Python TLS receiver: " + action + " " + result.GetRawText());
                    // Casio's minimum spacing is configured explicitly in the simulation.
                }
            }
            else
            {
                var empty = new Settings();
                if (empty.RpiHost.Length != 0 || empty.FireHost.Length != 0 || empty.AuxiliaryCueHost.Length != 0 || empty.PlaybackHost.Length != 0)
                    throw new Exception("Device address embedded in defaults");
                empty.Validate(requireRpi: false);
                try { empty.ValidateFire(); throw new Exception("Unconfigured fire action accepted"); }
                catch (ArgumentException) { }
                try { empty.ValidatePower(reconnect: true); throw new Exception("Unconfigured power action accepted"); }
                catch (ArgumentException) { }
                empty.AuxiliaryCueHost = "127.0.0.1";
                try { empty.ValidatePower(reconnect: true); throw new Exception("Partial power setup accepted"); }
                catch (ArgumentException) { }
                try { await Transport.SendUdp("", 52737, "test"); throw new Exception("Blank UDP destination accepted"); }
                catch (ArgumentException) { }
                passed.Add("Empty device defaults; incomplete fire/power setup rejected before network effects");
                using var rsa = RSA.Create(2048);
                var request = new CertificateRequest("CN=localhost", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
                using var issued = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-1), DateTimeOffset.UtcNow.AddDays(1));
                // Import into the platform key store so Windows Schannel can use the server key.
                using var certificate = X509CertificateLoader.LoadPkcs12(issued.Export(X509ContentType.Pfx), null);
                var listener = new TcpListener(IPAddress.Loopback, 0);
                listener.Start();
                var settings = new Settings
                {
                    RpiHost = "127.0.0.1", RpiPort = ((IPEndPoint)listener.LocalEndpoint).Port,
                    Token = new string('a', 64), CertificateSha256 = Convert.ToHexString(SHA256.HashData(certificate.RawData))
                };
                var server = Task.Run(async () =>
                {
                    using var tcp = await listener.AcceptTcpClientAsync();
                    using var tls = new SslStream(tcp.GetStream());
                    await tls.AuthenticateAsServerAsync(certificate, false, SslProtocols.Tls12 | SslProtocols.Tls13, false);
                    using var reader = new StreamReader(tls, new UTF8Encoding(false), leaveOpen: true);
                    string frame = await reader.ReadLineAsync() ?? throw new Exception("No frame");
                    using var json = JsonDocument.Parse(frame);
                    if (json.RootElement.GetProperty("action").GetString() != "on" || json.RootElement.GetProperty("token").GetString() != settings.Token)
                        throw new Exception("Wrong request");
                    await tls.WriteAsync(Encoding.UTF8.GetBytes("{\"v\":1,\"ok\":true,\"results\":{}}\n"));
                });
                var reply = await Transport.Request(settings, "on");
                await server.WaitAsync(TimeSpan.FromSeconds(10));
                listener.Stop();
                if (!reply.GetProperty("ok").GetBoolean()) throw new Exception("Wrong reply");
                passed.Add("TLS certificate pin, request encoding, response framing");
                settings.Token = "short";
                try { settings.Validate(); throw new Exception("Invalid token accepted"); }
                catch (ArgumentException) { passed.Add("Reject incomplete credentials"); }
                string previous = Settings.FilePath;
                string isolated = Path.Combine(Path.GetTempPath(), "guido-settings-" + Guid.NewGuid().ToString("N") + ".json");
                try
                {
                    Settings.UseFile(isolated);
                    new Settings { RpiPort = 41999 }.Save();
                    if (Settings.Load().RpiPort != 41999) throw new Exception("Isolated settings path failed");
                    passed.Add("Emulator settings isolated from normal installation settings");
                }
                finally
                {
                    Settings.UseFile(previous);
                    if (File.Exists(isolated)) File.Delete(isolated);
                }
            }
            File.WriteAllText(output, JsonSerializer.Serialize(new { ok = true, passed }, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }
        catch (Exception error)
        {
            File.WriteAllText(output, JsonSerializer.Serialize(new { ok = false, passed, error = error.ToString() }, new JsonSerializerOptions { WriteIndented = true }));
            return 1;
        }
    }
}
