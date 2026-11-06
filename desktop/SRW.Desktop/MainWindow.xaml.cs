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
        FitToWorkArea();
        Loaded += OnLoaded;
        Closing += OnClosing;
    }

    // The XAML size is DIP. On a 1920x1200 screen at 135% scaling, 1440x900 DIP
    // becomes ~1946x1226 physical pixels: the window is wider and taller than the
    // desktop, so CenterScreen pushes the title bar (and its minimize/maximize/
    // close buttons) above the visible area and clips the left edge of the shell.
    // Clamp to the work area before the window is shown.
    private void FitToWorkArea()
    {
        var work = SystemParameters.WorkArea;
        var fitted = Hosting.WindowPlacement.Fit(
            Width, Height, MinWidth, MinHeight, work.Left, work.Top, work.Width, work.Height);
        if (!fitted.Changed)
        {
            return;
        }

        MinWidth = fitted.MinWidth;
        MinHeight = fitted.MinHeight;
        Width = fitted.Width;
        Height = fitted.Height;
        WindowStartupLocation = WindowStartupLocation.Manual;
        Left = fitted.Left;
        Top = fitted.Top;
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
            // Install only Core-minted business Cookies. Never inject the Host
            // lifecycle secret into the renderer, URL or JavaScript.
            foreach (var cookie in _controller.BrowserCookies)
            {
                var browserCookie = Browser.CoreWebView2.CookieManager.CreateCookie(
                    cookie.Name, cookie.Value, "127.0.0.1", cookie.Path);
                browserCookie.IsHttpOnly = cookie.HttpOnly;
                browserCookie.IsSecure = cookie.Secure;
                browserCookie.SameSite = CoreWebView2CookieSameSiteKind.Strict;
                Browser.CoreWebView2.CookieManager.AddOrUpdateCookie(browserCookie);
            }
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
            _controller.LogEvent("webview_failed", new { error = exc.GetType().Name, message_redacted = true });
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
