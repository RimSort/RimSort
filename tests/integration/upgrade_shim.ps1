param([Parameter(Mandatory = $true)][string]$OutputDirectory)

$ErrorActionPreference = 'Stop'
$source = @'
using System;
using System.Diagnostics;
using System.IO;
using System.Web.Script.Serialization;

public class UpgradeShim {
    public static int Main(string[] args) {
        string root = Environment.GetEnvironmentVariable("RIMSORT_UPGRADE_TEST_ROOT");
        string python = Environment.GetEnvironmentVariable("RIMSORT_UPGRADE_TEST_PYTHON");
        string helper = Environment.GetEnvironmentVariable("RIMSORT_UPGRADE_TEST_HELPER");
        if (String.IsNullOrEmpty(root) || String.IsNullOrEmpty(python) || String.IsNullOrEmpty(helper)) return 64;
        string operation = Path.GetFileNameWithoutExtension(Process.GetCurrentProcess().MainModule.FileName);
        string request = Path.Combine(root, "events", Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(request, new JavaScriptSerializer().Serialize(new { operation, args }));
        ProcessStartInfo start = new ProcessStartInfo(python,
            "-I \"" + helper + "\" cli \"" + root + "\" \"" + request + "\"");
        start.UseShellExecute = false;
        using (Process child = Process.Start(start)) {
            child.WaitForExit();
            return child.ExitCode;
        }
    }
}
'@
Add-Type -TypeDefinition $source -ReferencedAssemblies System.dll, System.Web.Extensions.dll `
    -OutputAssembly (Join-Path $OutputDirectory 'taskkill.exe') -OutputType ConsoleApplication
