using System.Windows;
using SRW.Desktop.Hosting;
using SRW.Desktop.Runtime;

namespace SRW.Desktop;

public partial class App : Application
{
    private HostController? _controller;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        try
        {
            var paths = AppPaths.Discover(e.Args);
            _controller = new HostController(paths);
            await _controller.StartAsync();
            var window = new MainWindow(_controller);
            MainWindow = window;
            window.Show();
        }
        catch (Exception exc)
        {
            MessageBox.Show(
                $"智能招聘工作台 Windows Host 启动失败。\n\n{exc.Message}\n\n请查看 data\\logs\\host.log。",
                "Smart Recruitment Workbench",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            if (_controller is not null)
            {
                await _controller.StopAsync();
            }
            Shutdown(1);
        }
    }
}
