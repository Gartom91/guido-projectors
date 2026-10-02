namespace ShadokProjektory.RPi;

internal sealed class SettingsDialog : Form
{
    private readonly List<(Label Label, Control Editor)> fields = [];
    public Settings Result { get; private set; }

    public SettingsDialog(Settings current)
    {
        Result = current;
        Text = "Ustawienia ShadokProjektory — RPi";
        ClientSize = new Size(660, 500);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterParent;
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, Padding = new Padding(16) };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 225));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        Add("Adres IP / nazwa RPi", current.RpiHost);
        Add("Port TLS/TCP RPi", current.RpiPort);
        Add("Token RPi", current.Token, secret: true);
        Add("SHA256 certyfikatu RPi", current.CertificateSha256);
        Add("POŻAR — adres CueServer", current.FireHost);
        Add("POŻAR — port UDP", current.FirePort);
        Add("Zasilanie — adres CueServer", current.AuxiliaryCueHost);
        Add("Zasilanie — port UDP", current.AuxiliaryCuePort);
        Add("reconnect — adres odtwarzacza", current.PlaybackHost);
        Add("reconnect — port UDP", current.PlaybackPort);
        foreach (var field in fields)
        {
            table.RowStyles.Add(new RowStyle(SizeType.Absolute, 35));
            table.Controls.Add(field.Label);
            table.Controls.Add(field.Editor);
        }
        var info = new Label { Text = "Token i odcisk: sudo guido-config → Dane dla PC.\nHasło SSH ustawiasz na RPi; nie jest tokenem aplikacji.", AutoSize = true };
        table.Controls.Add(info);
        table.SetColumnSpan(info, 2);
        var buttons = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.RightToLeft, Dock = DockStyle.Fill };
        var save = new Button { Text = "Zapisz", AutoSize = true };
        var cancel = new Button { Text = "Anuluj", AutoSize = true, DialogResult = DialogResult.Cancel };
        save.Click += (_, _) => Save();
        buttons.Controls.Add(save);
        buttons.Controls.Add(cancel);
        table.Controls.Add(buttons);
        table.SetColumnSpan(buttons, 2);
        Controls.Add(table);
        AcceptButton = save;
        CancelButton = cancel;
    }

    private void Add(string title, object value, bool secret = false)
    {
        Control editor = value is int number
            ? new NumericUpDown { Minimum = 1, Maximum = 65535, Value = number, Dock = DockStyle.Fill }
            : new TextBox { Text = (string)value, UseSystemPasswordChar = secret, Dock = DockStyle.Fill };
        fields.Add((new Label { Text = title, AutoSize = true, Anchor = AnchorStyles.Left }, editor));
    }

    private void Save()
    {
        string TextAt(int index) => fields[index].Editor.Text.Trim();
        int PortAt(int index) => (int)((NumericUpDown)fields[index].Editor).Value;
        var changed = new Settings
        {
            RpiHost = TextAt(0), RpiPort = PortAt(1), Token = TextAt(2), CertificateSha256 = TextAt(3),
            FireHost = TextAt(4), FirePort = PortAt(5), AuxiliaryCueHost = TextAt(6), AuxiliaryCuePort = PortAt(7),
            PlaybackHost = TextAt(8), PlaybackPort = PortAt(9)
        };
        try
        {
            changed.Save();
            Result = changed;
            DialogResult = DialogResult.OK;
            Close();
        }
        catch (Exception error) when (error is ArgumentException or IOException or UnauthorizedAccessException)
        {
            MessageBox.Show(this, error.Message, "Ustawienia", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }
}
