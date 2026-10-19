// Transparent process launcher. No extraction, downloads, patching or elevation.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class Program {
    // Windows argv quoting, including embedded quotes and trailing backslashes.
    private static string Quote(string value) {
        StringBuilder text = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { text.Append('\\', slashes * 2 + 1); text.Append(c); }
            else { text.Append('\\', slashes); text.Append(c); }
            slashes = 0;
        }
        text.Append('\\', slashes * 2);
        return text.Append('"').ToString();
    }

    [STAThread]
    private static int Main(string[] args) {
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(root, "_internal", "python", "pythonw.exe");
            string script = Path.Combine(root, "_internal", "app", "launch.py");
            StringBuilder arguments = new StringBuilder("-I -B " + Quote(script));
            foreach (string arg in args) arguments.Append(" ").Append(Quote(arg));
            ProcessStartInfo start = new ProcessStartInfo(python, arguments.ToString());
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.WorkingDirectory = root;
            using (Process child = Process.Start(start)) {
                child.WaitForExit();
                return child.ExitCode;
            }
        } catch (Exception error) {
            MessageBox.Show(error.Message, "ECU Studio AI konnte nicht starten", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
