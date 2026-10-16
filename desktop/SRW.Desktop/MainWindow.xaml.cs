using System.ComponentModel;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using SRW.Desktop.Hosting;

namespace SRW.Desktop;

public partial class MainWindow : Window
{
    private readonly HostController _controller;
    private bool _allowClose;
    private bool _closing;

    public MainWindow(HostController controller)
    {
        _controller = controller;
        InitializeComponent();
        Loaded += OnLoaded;
        Closing += OnClosing;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        try
        {
            var userData = Path.Combine(_controller.Paths.UserDataRoot, "runtime-state", "webview2");
            Directory.CreateDirectory(userData);
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: userData);
            await Browser.EnsureCoreWebView2Async(environment);
            _controller.LogEvent("webview_initialized");
            Browser.CoreWebView2.NavigationCompleted += (_, args) =>
            {
                if (args.IsSuccess)
                {
                    _controller.LogEvent("frontend_loaded");
                }
            };
            Browser.Source = _controller.ApplicationUri;
        }
        catch (Exception exc)
        {
            _controller.LogEvent("webview_failed", new { error = exc.GetType().Name, message = exc.Message });
            MessageBox.Show(
                $"WebView2 初始化失败。请确认 Microsoft Edge WebView2 Runtime 可用。\n\n{exc.Message}",
                "Smart Recruitment Workbench",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            Close();
        }
    }

    private async void OnClosing(object? sender, CancelEventArgs e)
    {
        if (_allowClose)
        {
            return;
        }
        e.Cancel = true;
        if (_closing)
        {
            return;
        }
        _closing = true;
        IsEnabled = false;
        try
        {
            await _controller.StopAsync();
        }
        finally
        {
            _allowClose = true;
            Close();
        }
    }
}
