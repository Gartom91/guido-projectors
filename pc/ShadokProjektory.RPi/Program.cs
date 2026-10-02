namespace ShadokProjektory.RPi;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--settings")
        {
            Settings.UseFile(args[1]);
            args = [];
        }
        if (args.Length > 0 && args[0] is "--self-test" or "--integration-test" or "--udp-test")
            return SelfTest.Run(args).GetAwaiter().GetResult();
        ApplicationConfiguration.Initialize();
        if (args.Length == 2 && args[0] == "--render-ui")
        {
            using var form = new MainForm(new Settings { RpiHost = "guido.local" });
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new Point(-30000, -30000);
            form.ShowInTaskbar = false;
            form.Show();
            form.PerformLayout();
            Application.DoEvents();
            using var bitmap = new Bitmap(form.Width, form.Height);
            form.DrawToBitmap(bitmap, new Rectangle(Point.Empty, bitmap.Size));
            bitmap.Save(args[1], System.Drawing.Imaging.ImageFormat.Png);
            return 0;
        }
        try
        {
            Application.Run(new MainForm(Settings.Load()));
            return 0;
        }
        catch (Exception error) when (error is IOException or System.Text.Json.JsonException or ArgumentException)
        {
            MessageBox.Show($"Nie można odczytać ustawień:\n{Settings.FilePath}\n\n{error.Message}", "ShadokProjektory", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
