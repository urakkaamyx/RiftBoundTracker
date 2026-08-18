using System.Windows;
using System.Windows.Controls;
using System.Windows.Forms;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Shell;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using Application = System.Windows.Application;
using Image = System.Windows.Controls.Image;
using MessageBox = System.Windows.MessageBox;
using Button = System.Windows.Controls.Button;
using HorizontalAlignment = System.Windows.HorizontalAlignment;
using Orientation = System.Windows.Controls.Orientation;
using FontFamily = System.Windows.Media.FontFamily;
using Point = System.Windows.Point;

namespace RiftBoundTracker.App.Desktop;

/// <summary>
/// A thin native window around the existing web UI — the backend and frontend are unchanged,
/// this just gives a friend double-clicking the exe a real app window instead of a console
/// window plus "now go open a browser and remember this URL" instructions.
///
/// Opens straight into a maximized main window with its own custom title bar — no native Windows
/// chrome, matching the app's dark/gold web theme instead of whatever the OS default looks like.
///
/// Closing the window minimizes to the tray instead of exiting: the server keeps running so a
/// phone on the same Wi-Fi can still reach it. "Exit" from the tray menu is the only way to
/// actually shut down — except <paramref name="lifetime"/>, which the self-update flow (and
/// anything else that calls IHostApplicationLifetime.StopApplication) also needs wired to a real
/// exit. Without that hook, stopping the ASP.NET Core host doesn't touch the WPF message loop at
/// all — the process just keeps running with the window still open, and the update relauncher
/// ends up trying to overwrite files that are still locked because nothing ever actually exited.
/// </summary>
public class DesktopShell(int port, string webRootPath, IHostApplicationLifetime lifetime)
{
    private const string BgHex = "#090A09";
    private const string TitleBarHex = "#0D0E0C";
    private const string TextHex = "#F3F0E7";
    private const string GoldHex = "#F0CA68";
    private const string CaptionHoverHex = "#232520";
    private const string CloseHoverHex = "#DC6557";

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
            _trayIcon.ShowBalloonTip(2500, "RiftKeep", "Still running in the background — your phone can keep using it. Right-click the tray icon to exit.", ToolTipIcon.Info);
        };

        lifetime.ApplicationStopping.Register(() =>
        {
            if (_reallyExiting) return;
            app.Dispatcher.BeginInvoke(ExitApp);
        });

        var launcher = BuildLauncherWindow(icon);
        launcher.Show();
        app.Run();

        _trayIcon.Visible = false;
        _trayIcon.Dispose();
    }

    private Window BuildLauncherWindow(System.Drawing.Icon? icon)
    {
        // Native size (1254x1254), only capped if the screen is literally too short to fit it —
        // no decorative shrinking into a small icon-in-a-box the way an earlier version did.
        var workArea = SystemParameters.WorkArea;
        var side = Math.Min(1254, Math.Max(480, workArea.Height * 0.92));

        var image = new Image
        {
            Stretch = Stretch.Uniform,
            // Slightly under the crystal floating in the doorway, so the zoom reads as walking
            // toward/past it rather than centering on empty space above it.
            RenderTransformOrigin = new Point(0.5, 0.62),
            RenderTransform = new ScaleTransform(1, 1),
        };
        var fullLogo = LoadImage("logo-full.png");
        if (fullLogo is not null) image.Source = fullLogo;

        // Stone "Enter Vault" plaque (hand-made asset, normal/hover pair) instead of a plain
        // rectangle — the plaque's own bottom diamond decoration is placed directly on top of
        // the diamond gem above "RIFTKEEP" in the main logo, so the two visually merge.
        const double buttonWidthFraction = 0.34;
        const double plaqueAspect = 2.1912;        // measured from enter.png after cropping to content bbox
        const double plaqueBottomGemFraction = 0.787; // the plaque's own bottom diamond, measured down from its top edge
        const double targetGemFraction = 0.80;     // the RIFTKEEP diamond's center, in the main logo
        var buttonWidth = side * buttonWidthFraction;
        var buttonHeight = buttonWidth / plaqueAspect;
        var buttonTop = side * targetGemFraction - buttonHeight * plaqueBottomGemFraction;

        var enterNormal = LoadImage("enter.png");
        var enterHover = LoadImage("enter-hover.png");
        var buttonImage = new Image { Stretch = Stretch.Uniform, Width = buttonWidth, Height = buttonHeight };
        if (enterNormal is not null) buttonImage.Source = enterNormal;

        var openButton = new Button
        {
            Content = buttonImage,
            Width = buttonWidth,
            Height = buttonHeight,
            Cursor = System.Windows.Input.Cursors.Hand,
            Template = ImageButtonTemplate(),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Top,
            Margin = new Thickness(0, buttonTop, 0, 0),
        };
        openButton.MouseEnter += (_, _) => { if (enterHover is not null) buttonImage.Source = enterHover; };
        openButton.MouseLeave += (_, _) => { if (enterNormal is not null) buttonImage.Source = enterNormal; };

        // Fully transparent window + content background: the logo's own alpha (transparent
        // outside the badge) is what actually shapes the window — a rectangular window with an
        // opaque black fill would just show the PNG's transparent corners as a black square.
        var root = new Grid { Background = System.Windows.Media.Brushes.Transparent };
        root.Children.Add(image);
        root.Children.Add(openButton);

        var launcher = new Window
        {
            Title = "RiftKeep",
            Width = side,
            Height = side,
            WindowStyle = WindowStyle.None,
            AllowsTransparency = true,
            ResizeMode = ResizeMode.NoResize,
            WindowStartupLocation = WindowStartupLocation.CenterScreen,
            Background = System.Windows.Media.Brushes.Transparent,
            Content = root,
        };
        SetWindowIcon(launcher, icon);
        launcher.MouseLeftButtonDown += (_, e) => { if (e.ButtonState == System.Windows.Input.MouseButtonState.Pressed) launcher.DragMove(); };

        openButton.Click += (_, _) => EnterVault(launcher, image, openButton);

        return launcher;
    }

    // "Zoom through the gate" on Open Vault: the logo scales up around its own center while the
    // button and then the whole window fade out, timed so the window closes right as the zoom
    // reads as "walked past the edges of frame" rather than a sudden cut.
    private void EnterVault(Window launcher, Image image, Button openButton)
    {
        openButton.IsHitTestVisible = false;
        PlayDoorSound();

        var zoomDuration = TimeSpan.FromMilliseconds(1600);
        var ease = new QuadraticEase { EasingMode = EasingMode.EaseIn };
        var scale = (ScaleTransform)image.RenderTransform;
        scale.BeginAnimation(ScaleTransform.ScaleXProperty, new DoubleAnimation(1, 9, zoomDuration) { EasingFunction = ease });
        scale.BeginAnimation(ScaleTransform.ScaleYProperty, new DoubleAnimation(1, 9, zoomDuration) { EasingFunction = ease });
        openButton.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(200)));

        var windowFade = new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(350))
        {
            BeginTime = zoomDuration - TimeSpan.FromMilliseconds(350),
        };
        windowFade.Completed += (_, _) =>
        {
            launcher.Close();
            _window!.Show();
            _window.Activate();
        };
        launcher.BeginAnimation(UIElement.OpacityProperty, windowFade);
    }

    // Best-effort: a missing sound asset should never block entering the app. Drop a
    // wwwroot/sounds/door-open.mp3 (or .wav) in to give this a real sound.
    private void PlayDoorSound()
    {
        foreach (var name in new[] { "door-open.mp3", "door-open.wav" })
        {
            var path = Path.Combine(webRootPath, "sounds", name);
            if (!File.Exists(path)) continue;
            try
            {
                var player = new System.Windows.Media.MediaPlayer();
                player.Open(new Uri(path, UriKind.Absolute));
                player.Play();
            }
            catch
            {
                // Ignored — silence beats a crash on a decorative sound effect.
            }
            return;
        }
    }

    private Window BuildWindow(System.Drawing.Icon? icon)
    {
        var webView = new WebView2 { Source = new Uri($"http://localhost:{port}") };
        webView.CoreWebView2InitializationCompleted += (_, e) =>
        {
            if (!e.IsSuccess)
            {
                MessageBox.Show(
                    "RiftKeep couldn't start its embedded browser (WebView2). " +
                    "It's usually already installed on Windows 10/11, but you may need to install " +
                    "the \"WebView2 Runtime\" from Microsoft to use the desktop window.\n\n" +
                    $"Details: {e.InitializationException?.Message}",
                    "RiftKeep", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        };

        var window = new Window
        {
            Title = "RiftKeep",
            Width = 1280,
            Height = 860,
            MinWidth = 720,
            MinHeight = 480,
            WindowStartupLocation = WindowStartupLocation.CenterScreen,
            WindowState = WindowState.Maximized,
            Background = ColorFromHex(BgHex),
        };

        var titleBar = BuildTitleBar(window);

        var layout = new Grid();
        layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        layout.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        Grid.SetRow(titleBar, 0);
        Grid.SetRow(webView, 1);
        layout.Children.Add(titleBar);
        layout.Children.Add(webView);
        window.Content = layout;

        WindowChrome.SetWindowChrome(window, new WindowChrome
        {
            CaptionHeight = 40,
            ResizeBorderThickness = new Thickness(6),
            GlassFrameThickness = new Thickness(0),
            CornerRadius = new CornerRadius(0),
            UseAeroCaptionButtons = false,
        });

        SetWindowIcon(window, icon);
        return window;
    }

    private FrameworkElement BuildTitleBar(Window window)
    {
        var bar = new Grid { Height = 40, Background = ColorFromHex(TitleBarHex) };
        bar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        bar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var brand = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Margin = new Thickness(14, 0, 0, 0),
            VerticalAlignment = VerticalAlignment.Center,
        };
        var logo = LoadImage("logo.png");
        if (logo is not null)
            brand.Children.Add(new Image { Source = logo, Width = 20, Height = 20, Margin = new Thickness(0, 0, 8, 0) });
        brand.Children.Add(new TextBlock
        {
            Text = "RIFTKEEP",
            Foreground = ColorFromHex(GoldHex),
            FontSize = 11,
            FontWeight = FontWeights.Bold,
            VerticalAlignment = VerticalAlignment.Center,
        });
        Grid.SetColumn(brand, 0);

        var buttons = new StackPanel { Orientation = Orientation.Horizontal };
        buttons.Children.Add(CaptionButton("", CaptionHoverHex, (_, _) => window.WindowState = WindowState.Minimized));
        buttons.Children.Add(CaptionButton("", CaptionHoverHex, (_, _) =>
            window.WindowState = window.WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized));
        buttons.Children.Add(CaptionButton("", CloseHoverHex, (_, _) => window.Close()));
        Grid.SetColumn(buttons, 1);
        WindowChrome.SetIsHitTestVisibleInChrome(buttons, true);

        bar.Children.Add(brand);
        bar.Children.Add(buttons);
        return bar;
    }

    private static Button CaptionButton(string segoeGlyph, string hoverHex, RoutedEventHandler onClick)
    {
        var button = new Button
        {
            Content = new TextBlock { Text = segoeGlyph, FontFamily = new FontFamily("Segoe MDL2 Assets"), FontSize = 10 },
            Width = 46,
            Height = 40,
            Foreground = ColorFromHex(TextHex),
            Cursor = System.Windows.Input.Cursors.Hand,
            Template = SolidButtonTemplate("Transparent", hoverHex, cornerRadius: 0),
        };
        button.Click += onClick;
        return button;
    }

    // Built via inline XAML rather than FrameworkElementFactory — far less verbose for a simple
    // "flat background + rounded corners + hover color swap" template, and this codebase has no
    // .xaml files at all (everything is built in code), so this stays self-contained here.
    private static ControlTemplate SolidButtonTemplate(string backgroundHex, string hoverHex, double cornerRadius)
    {
        var xaml = $"""
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="Button">
              <Border x:Name="Bg" Background="{backgroundHex}" CornerRadius="{cornerRadius}">
                <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
              </Border>
              <ControlTemplate.Triggers>
                <Trigger Property="IsMouseOver" Value="True">
                  <Setter TargetName="Bg" Property="Background" Value="{hoverHex}"/>
                </Trigger>
              </ControlTemplate.Triggers>
            </ControlTemplate>
            """;
        return (ControlTemplate)XamlReader.Parse(xaml);
    }

    // No background/border chrome at all — the button's own image (the stone plaque asset) is
    // the entire visual, hover is handled by swapping the Image.Source rather than a template
    // trigger, so this just needs to host the content without adding anything of its own.
    private static ControlTemplate ImageButtonTemplate()
    {
        const string xaml = """
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="Button">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </ControlTemplate>
            """;
        return (ControlTemplate)XamlReader.Parse(xaml);
    }

    private static SolidColorBrush ColorFromHex(string hex) =>
        (SolidColorBrush)new BrushConverter().ConvertFromString(hex)!;

    private BitmapImage? LoadImage(string fileName)
    {
        var path = Path.Combine(webRootPath, fileName);
        if (!File.Exists(path)) return null;
        var bitmap = new BitmapImage();
        bitmap.BeginInit();
        bitmap.UriSource = new Uri(path, UriKind.Absolute);
        bitmap.CacheOption = BitmapCacheOption.OnLoad;
        bitmap.EndInit();
        bitmap.Freeze();
        return bitmap;
    }

    private static void SetWindowIcon(Window window, System.Drawing.Icon? icon)
    {
        if (icon is null) return;
        window.Icon = System.Windows.Interop.Imaging.CreateBitmapSourceFromHIcon(
            icon.Handle, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
    }

    private NotifyIcon BuildTrayIcon(System.Drawing.Icon? icon)
    {
        var menu = new ContextMenuStrip();
        menu.Items.Add("Open RiftKeep", null, (_, _) => ShowWindow());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Exit", null, (_, _) => ExitApp());

        var tray = new NotifyIcon
        {
            Icon = icon ?? System.Drawing.SystemIcons.Application,
            Text = "RiftKeep",
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
        if (_window.WindowState == WindowState.Minimized) _window.WindowState = WindowState.Maximized;
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
