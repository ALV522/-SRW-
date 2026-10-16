namespace SRW.Desktop.Runtime;

public sealed record AppPaths(string ApplicationRoot, string UserDataRoot)
{
    public string PythonExe => Path.Combine(ApplicationRoot, "runtime", "python.exe");
    public string BackendLauncher => Path.Combine(ApplicationRoot, "scripts", "run_local.py");
    public string FrontendDist => Path.Combine(ApplicationRoot, "frontend", "dist");
    public string KnowledgeRoot => Path.Combine(ApplicationRoot, "knowledge");
    public string LogRoot => Path.Combine(UserDataRoot, "logs");

    public static AppPaths Discover(IReadOnlyList<string> args)
    {
        string? explicitRoot = null;
        string? explicitData = null;
        for (var index = 0; index < args.Count; index++)
        {
            if (args[index] == "--application-root" && index + 1 < args.Count)
            {
                explicitRoot = args[++index];
            }
            else if (args[index] == "--data-root" && index + 1 < args.Count)
            {
                explicitData = args[++index];
            }
        }

        var applicationRoot = explicitRoot is not null
            ? Path.GetFullPath(explicitRoot)
            : FindApplicationRoot(AppContext.BaseDirectory);
        var userDataRoot = Path.GetFullPath(explicitData ?? Path.Combine(applicationRoot, "data"));

        RequireFile(Path.Combine(applicationRoot, "VERSION"));
        RequireFile(Path.Combine(applicationRoot, "runtime", "python.exe"));
        RequireFile(Path.Combine(applicationRoot, "scripts", "run_local.py"));
        RequireFile(Path.Combine(applicationRoot, "frontend", "dist", "index.html"));
        Directory.CreateDirectory(userDataRoot);
        Directory.CreateDirectory(Path.Combine(userDataRoot, "logs"));
        return new AppPaths(applicationRoot, userDataRoot);
    }

    private static string FindApplicationRoot(string start)
    {
        var directory = new DirectoryInfo(Path.GetFullPath(start));
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "VERSION")) &&
                File.Exists(Path.Combine(directory.FullName, "scripts", "run_local.py")) &&
                Directory.Exists(Path.Combine(directory.FullName, "frontend", "dist")))
            {
                return directory.FullName;
            }
            directory = directory.Parent;
        }
        throw new InvalidOperationException("无法定位 ApplicationRoot。请从完整 Windows Portable 包启动，或传入 --application-root。 ");
    }

    private static void RequireFile(string path)
    {
        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"缺少必需运行文件: {path}", path);
        }
    }
}
