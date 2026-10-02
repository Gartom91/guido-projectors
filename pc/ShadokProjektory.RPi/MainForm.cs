using System.Security.Authentication;
using System.Text.Json;

namespace ShadokProjektory.RPi;

internal sealed class MainForm : Form
{
    private Settings settings;
    private readonly List<Button> buttons = [];
    private readonly TextBox log;
    private readonly Label state;
    private bool nextCutPower = true;

    public MainForm(Settings settings)
    {
        this.settings = settings;
        Text = "Projektory Shadok — RPi";
        MinimumSize = new Size(650, 460);
        ClientSize = new Size(780, 520);
        StartPosition = FormStartPosition.CenterScreen;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(16), ColumnCount = 2, RowCount = 6 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 55));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 55));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 55));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 35));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        Add(layout, "WDARCIE WODY WŁ", () => Projectors("on"));
        Add(layout, "WDARCIE WODY WYŁ", () => Projectors("off"));
        Add(layout, "POŻAR WŁ", () => Fire(true));
        Add(layout, "POŻAR WYŁ", () => Fire(false));
        Add(layout, "Zasilanie — wyłącz", Power);
        Add(layout, "Stan projektorów", () => Projectors("status"));
        state = new Label { Text = "Gotowe. Stan urządzeń nieznany.", AutoSize = true, Dock = DockStyle.Fill };
        layout.Controls.Add(state);
        layout.SetColumnSpan(state, 2);
        log = new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill };
        layout.Controls.Add(log);
        layout.SetColumnSpan(log, 2);
        var config = new Button { Text = "Ustawienia", Dock = DockStyle.Fill };
        config.Click += (_, _) =>
        {
            using var dialog = new SettingsDialog(this.settings);
            if (dialog.ShowDialog(this) == DialogResult.OK) this.settings = dialog.Result;
        };
        buttons.Add(config);
        layout.Controls.Add(config);
        layout.Controls.Add(new Label { Text = "UDP: wysłanie bez potwierdzenia wykonania", AutoSize = true, Anchor = AnchorStyles.Left });
        Controls.Add(layout);
        if (settings.RpiHost.Length == 0)
            Shown += (_, _) => config.PerformClick();
    }

    private void Add(TableLayoutPanel layout, string title, Func<Task> action)
    {
        var button = new Button { Text = title, Dock = DockStyle.Fill, Margin = new Padding(4), Font = new Font(Font, FontStyle.Bold) };
        button.Click += async (_, _) => await Execute(action);
        buttons.Add(button);
        layout.Controls.Add(button);
    }

    private async Task Execute(Func<Task> action)
    {
        foreach (var button in buttons) button.Enabled = false;
        state.Text = "Trwa wysyłanie / oczekiwanie na odpowiedź…";
        try
        {
            await action();
        }
        catch (Exception error) when (error is IOException or System.Net.Sockets.SocketException
            or AuthenticationException or OperationCanceledException or JsonException
            or ArgumentException or InvalidOperationException)
        {
            string detail = error is AuthenticationException
                ? "Błąd TLS. Sprawdź odcisk SHA256 odczytany na RPi i datę systemową."
                : error is OperationCanceledException ? "Przekroczono czas oczekiwania. Wynik polecenia może być nieznany." : error.Message;
            state.Text = "Błąd — sprawdź szczegóły poniżej.";
            Append(detail);
        }
        finally
        {
            foreach (var button in buttons) button.Enabled = true;
        }
    }

    private void Append(string message) => log.AppendText($"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}");

    private async Task Projectors(string action)
    {
        JsonElement reply = await Transport.Request(settings, action);
        bool ok = reply.GetProperty("ok").GetBoolean();
        state.Text = ok ? "Otrzymano odpowiedź RPi — szczegóły poniżej." : "Błąd lub częściowe wykonanie — szczegóły poniżej.";
        if (reply.TryGetProperty("error", out var error)) Append(error.GetString() ?? "Błąd RPi");
        if (!reply.TryGetProperty("results", out var results)) return;
        foreach (var item in results.EnumerateObject())
        {
            string status = item.Value.GetProperty("status").GetString() ?? "unknown";
            string translated = status switch
            {
                "verified" => "stan potwierdzony", "already_set" => "żądany stan już ustawiony",
                "acknowledged" => "projektor przyjął polecenie", "sent_unconfirmed" => "wysłano; wykonanie niepotwierdzone",
                "unavailable" => "odczyt stanu niedostępny", "disabled" => "wyłączony w konfiguracji",
                "busy" => "urządzenie zajęte", "error" => "błąd", _ => status
            };
            string powerState = item.Value.TryGetProperty("state", out var value) ? value.GetString() ?? "unknown" : "unknown";
            powerState = powerState switch
            {
                "on" => "włączony", "standby" => "czuwanie", "warming_up" => "rozgrzewanie",
                "cooling" => "chłodzenie", "power_saving" => "oszczędzanie energii", _ => "nieznany"
            };
            Append($"{item.Name}: {translated}; stan: {powerState}.");
            if (item.Value.TryGetProperty("detail", out var detail)) Append(detail.GetString() ?? "");
        }
    }

    private async Task Fire(bool on)
    {
        settings.ValidateFire();
        await Transport.SendUdp(settings.FireHost, settings.FirePort, Transport.FireCommand(on));
        state.Text = "POŻAR: wysłano UDP; brak potwierdzenia wykonania.";
        Append($"POŻAR {(on ? "WŁ" : "WYŁ")}: {settings.FireHost}:{settings.FirePort} — wysłano.");
    }

    private async Task Power()
    {
        settings.ValidatePower(reconnect: nextCutPower);
        if (nextCutPower)
        {
            await Transport.SendUdp(settings.PlaybackHost, settings.PlaybackPort, "reconnect");
            Append("Wysłano reconnect do odtwarzacza; brak potwierdzenia wykonania.");
        }
        await Transport.SendUdp(settings.AuxiliaryCueHost, settings.AuxiliaryCuePort, Transport.AuxiliaryCommand(nextCutPower));
        Append($"Zasilanie: wysłano Output 8 {(nextCutPower ? "On" : "Off")}; brak potwierdzenia wykonania.");
        nextCutPower = !nextCutPower;
        buttons[4].Text = nextCutPower ? "Zasilanie — wyłącz" : "Zasilanie — włącz";
        state.Text = "Zasilanie: polecenie wysłane; rzeczywisty stan niepotwierdzony.";
    }
}
