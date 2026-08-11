using System.Windows;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using Application = System.Windows.Application;
using MessageBox = System.Windows.MessageBox;

namespace RiftBoundTracker.App.Desktop;

/// <summary>
/// A thin native window around the existing web UI — the backend and frontend are unchanged,
/// this just gives a friend double-clicking the exe a real app window instead of a console
/// window plus "now go open a browser and remember this URL" instructions.
///
/// Closing the window minimizes to the tray instead of exiting: the server keeps running so a
/// phone on the same Wi-Fi can still reach it. "Exit" from the tray menu is the only way to
/// actually shut down — except <paramref name="lifetime"/>, which the self-update flow (and
/// anything else that calls IHostApplicationLifetime.StopApplication) also needs wired to a real
/// exit. Without that hook, stopping the ASP.NET Core host doesn't touch the WPF message loop at
/// all — the process just keeps running with the window still open, and the update relauncher
/// ends up trying to overwrite files that are still locked because nothing ever actually exited.
/// </summary>
public class DesktopShell(int port, IHostApplicationLifetime lifetime)
{
    private NotifyIcon? _trayIcon;
    private Window? _window;
    private bool _reallyExiting;

    public void Run()
    {
        var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };

        var icon = LoadIcon();
        _window = BuildWindow(icon);
        _trayIcon = BuildTrayIcon(icon);

        _window.Closing += (_, e) =>
        {
            if (_reallyExiting) return;
            e.Cancel = true;
            _window.Hide();
            _trayIcon.ShowBalloonTip(2500, "RiftBound Vault", "Still running in the background — your phone can keep using it. Right-click the tray icon to exit.", ToolTipIcon.Info);
        };

        lifetime.ApplicationStopping.Register(() =>
        {
            if (_reallyExiting) return;
            app.Dispatcher.BeginInvoke(ExitApp);
        });

        _window.Show();
        app.Run();

        _trayIcon.Visible = false;
        _trayIcon.Dispose();
    }

    private Window BuildWindow(System.Drawing.Icon? icon)
    {
        var webView = new WebView2 { Source = new Uri($"http://localhost:{port}") };
        webView.CoreWebView2InitializationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
            {
                MessageBox.Show(
                    "RiftBound Vault couldn't start its embedded browser (WebView2). " +
                    "It's usually already installed on Windows 10/11, but you may need to install " +
                    "the \"WebView2 Runtime\" from Microsoft to use the desktop window.\n\n" +
                    $"Details: {e.InitializationException?.Message}",
                    "RiftBound Vault", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        };

        var window = new Window
        {
            Title = "RiftBound Vault",
            Width = 1280,
            Height = 860,
            MinWidth = 720,
            MinHeight = 480,
            Content = webView,
            WindowStartupLocation = WindowStartupLocation.CenterScreen,
        };

        if (icon is not null)
            window.Icon = System.Windows.Interop.Imaging.CreateBitmapSourceFromHIcon(
                icon.Handle, Int32Rect.Empty, System.Windows.Media.Imaging.BitmapSizeOptions.FromEmptyOptions());

        return window;
    }

    private NotifyIcon BuildTrayIcon(System.Drawing.Icon? icon)
    {
        var menu = new ContextMenuStrip();
        menu.Items.Add("Open RiftBound Vault", null, (_, _) => ShowWindow());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Exit", null, (_, _) => ExitApp());

        var tray = new NotifyIcon
        {
            Icon = icon ?? System.Drawing.SystemIcons.Application,
            Text = "RiftBound Vault",
            Visible = true,
            ContextMenuStrip = menu,
        };
        tray.DoubleClick += (_, _) => ShowWindow();
        return tray;
    }

    private void ShowWindow()
    {
        if (_window is null) return;
        _window.Show();
        _window.WindowState = WindowState.Normal;
        _window.Activate();
    }

    private void ExitApp()
    {
        _reallyExiting = true;
        _window?.Close();
        Application.Current.Shutdown();
    }

    private static System.Drawing.Icon? LoadIcon()
    {
        try
        {
            var exePath = Environment.ProcessPath;
            return string.IsNullOrEmpty(exePath) ? null : System.Drawing.Icon.ExtractAssociatedIcon(exePath);
        }
        catch
        {
            return null;
        }
    }
}
