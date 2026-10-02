using System.Text.Json;
using System.Text.RegularExpressions;

namespace ShadokProjektory.RPi;

internal sealed class Settings
{
    public string RpiHost { get; set; } = "";
    public int RpiPort { get; set; } = 41794;
    public string Token { get; set; } = "";
    public string CertificateSha256 { get; set; } = "";
    public string FireHost { get; set; } = "";
    public int FirePort { get; set; } = 52737;
    public string AuxiliaryCueHost { get; set; } = "";
    public int AuxiliaryCuePort { get; set; } = 52737;
    public string PlaybackHost { get; set; } = "";
    public int PlaybackPort { get; set; } = 52737;

    public static string FilePath { get; private set; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ShadokProjektory-RPi", "settings.json");

    public static void UseFile(string path) => FilePath = Path.GetFullPath(path);

    public void Validate(bool requireRpi = true)
    {
        static void Host(string host, bool optional = false)
        {
            if (optional && host == "") return;
            if (string.IsNullOrWhiteSpace(host) || host.Length > 253 || Uri.CheckHostName(host) == UriHostNameType.Unknown)
                throw new ArgumentException("Wymagany poprawny adres IP lub nazwa hosta.");
        }
        static void Port(int port)
        {
            if (port is < 1 or > 65535) throw new ArgumentException("Port musi mieścić się w zakresie 1–65535.");
        }
        if (requireRpi || RpiHost.Length != 0)
        {
            Host(RpiHost);
            if (!Regex.IsMatch(Token, "^[A-Za-z0-9_-]{32,128}$"))
                throw new ArgumentException("Wpisz token odczytany w menu RPi (32–128 znaków).");
            CertificateSha256 = CertificateSha256.Replace(":", "").Replace(" ", "").ToUpperInvariant();
            if (!Regex.IsMatch(CertificateSha256, "^[A-F0-9]{64}$"))
                throw new ArgumentException("Wpisz pełny odcisk SHA256 certyfikatu RPi (64 znaki HEX).");
        }
        Host(FireHost, optional: true); Host(AuxiliaryCueHost, optional: true); Host(PlaybackHost, optional: true);
        Port(RpiPort); Port(FirePort); Port(AuxiliaryCuePort); Port(PlaybackPort);
    }

    public void ValidateFire()
    {
        Validate(requireRpi: false);
        if (FireHost.Length == 0)
            throw new ArgumentException("Najpierw wpisz adres urządzenia POŻAR w ustawieniach.");
    }

    public void ValidatePower(bool reconnect)
    {
        Validate(requireRpi: false);
        if (AuxiliaryCueHost.Length == 0 || (reconnect && PlaybackHost.Length == 0))
            throw new ArgumentException("Najpierw wpisz adres CueServer zasilania i odtwarzacza w ustawieniach.");
    }

    public static Settings Load(string? path = null)
    {
        path ??= FilePath;
        if (!File.Exists(path)) return new Settings();
        var settings = JsonSerializer.Deserialize<Settings>(File.ReadAllText(path))
            ?? throw new JsonException("Pusty plik ustawień.");
        settings.Validate(requireRpi: false);
        return settings;
    }

    public void Save()
    {
        Validate(requireRpi: false);
        Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
        string temporary = FilePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                JsonSerializer.Serialize(file, this, new JsonSerializerOptions { WriteIndented = true });
                file.Flush(flushToDisk: true);
            }
            File.Move(temporary, FilePath, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }
}
