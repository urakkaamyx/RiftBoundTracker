namespace RiftBoundTracker.App.Services.Logging;

/// <summary>
/// The app previously only had --debug-console (a live console window you had to remember to
/// open *before* reproducing a bug) — nothing persisted, so a bug hit without that flag left
/// nothing to grab afterward. This appends every log line to a small rolling file under
/// App_Data/logs instead, so a bug report can always pull a recent trace regardless of how the
/// app was launched. Deliberately minimal (no external logging package) — just enough to append
/// timestamped lines and cap the file size.
/// </summary>
public sealed class FileLoggerProvider : ILoggerProvider
{
    private const long MaxBytes = 5 * 1024 * 1024;
    private readonly string _filePath;
    private readonly object _lock = new();

    public FileLoggerProvider(string filePath)
    {
        _filePath = filePath;
        Directory.CreateDirectory(Path.GetDirectoryName(filePath)!);
    }

    public ILogger CreateLogger(string categoryName) => new FileLogger(categoryName, this);

    internal void Write(string line)
    {
        lock (_lock)
        {
            try
            {
                if (File.Exists(_filePath) && new FileInfo(_filePath).Length > MaxBytes)
                {
                    var rolled = _filePath + ".old";
                    File.Move(_filePath, rolled, overwrite: true);
                }
                File.AppendAllText(_filePath, line);
            }
            catch
            {
                // Logging must never be the thing that crashes the app.
            }
        }
    }

    public void Dispose() { }
}

internal sealed class FileLogger(string category, FileLoggerProvider provider) : ILogger
{
    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

    // Information+ only — Debug/Trace from EF Core and Kestrel would otherwise fill 5MB in minutes
    // and push out the entries that actually matter for a bug report.
    public bool IsEnabled(LogLevel logLevel) => logLevel >= LogLevel.Information;

    public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
    {
        if (!IsEnabled(logLevel)) return;
        var line = $"{DateTime.UtcNow:yyyy-MM-dd HH:mm:ss.fff}Z [{logLevel}] {category}: {formatter(state, exception)}";
        if (exception is not null) line += Environment.NewLine + exception;
        provider.Write(line + Environment.NewLine);
    }
}
