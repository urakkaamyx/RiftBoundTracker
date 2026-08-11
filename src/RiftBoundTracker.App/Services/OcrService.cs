using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Formats.Png;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;
using Tesseract;

namespace RiftBoundTracker.App.Services;

public class OcrService : IDisposable
{
    private readonly ILogger<OcrService> _logger;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private TesseractEngine? _engine;

    public OcrService(ILogger<OcrService> logger) => _logger = logger;

    private string TessDataPath => Path.Combine(AppContext.BaseDirectory, "tessdata");

    /// <summary>
    /// Runs OCR near the bottom-left corner, where Riftbound prints the collector number.
    /// Expects <paramref name="image"/> to already be oriented and cropped down to just the card
    /// (see PhotoBoundaryDetector) — region percentages are relative to the card, not an arbitrary
    /// photo that may include background.
    ///
    /// <paramref name="fast"/> trades thoroughness for latency: one crop, one threshold, digits
    /// only — meant for the live-camera loop, where a request fires every ~800ms and needs to come
    /// back quickly rather than exhaustively. The still-photo/manual flows use the slower, more
    /// thorough multi-pass sweep instead, since latency doesn't matter there.
    /// </summary>
    public async Task<string> ReadCardNumberTextAsync(Image<Rgba32> image, bool fast, CancellationToken ct = default)
    {
        var w = image.Width;
        var h = image.Height;

        var tightRegion = new Rectangle(0, (int)(h * 0.80), (int)(w * 0.45), (int)(h * 0.20));
        var wideRegion = new Rectangle(0, (int)(h * 0.82), w, (int)(h * 0.18));

        var combined = new System.Text.StringBuilder();

        if (fast)
        {
            var safe = Rectangle.Intersect(tightRegion, image.Bounds);
            if (safe.Width > 4 && safe.Height > 4)
            {
                using var crop = image.Clone(x => x
                    .Crop(safe)
                    .Resize(safe.Width * 3, safe.Height * 3)
                    .Grayscale()
                    .Contrast(1.5f)
                    .BinaryThreshold(0.5f));
                using var ms = new MemoryStream();
                await crop.SaveAsync(ms, new PngEncoder(), ct);
                combined.AppendLine(await RunTesseractAsync(ms.ToArray(), "0123456789/. ", ct));
            }
            return combined.ToString();
        }

        // Two candidate regions: a tight bottom-left corner (where the number usually sits),
        // and a wider bottom band (in case the crop isn't tight to the card edges).
        foreach (var region in new[] { tightRegion, wideRegion })
        {
            var safe = Rectangle.Intersect(region, image.Bounds);
            if (safe.Width <= 4 || safe.Height <= 4) continue;

            foreach (var threshold in new[] { 0.5f, 0.62f, 0.38f })
            {
                using var crop = image.Clone(x => x
                    .Crop(safe)
                    .Resize(safe.Width * 4, safe.Height * 4)
                    .Grayscale()
                    .Contrast(1.5f)
                    .BinaryThreshold(threshold));

                using var ms = new MemoryStream();
                await crop.SaveAsync(ms, new PngEncoder(), ct);
                combined.AppendLine(await RunTesseractAsync(ms.ToArray(), "0123456789/. ", ct));
            }
        }

        // One unrestricted pass, kept to the tight bottom-left corner only, to try to pick up a
        // nearby set code (e.g. "VEN"). The wider band runs into rules-text lines further up the
        // card, which produces garbage letter sequences that outrank the real set code.
        var tightSafe = Rectangle.Intersect(tightRegion, image.Bounds);
        if (tightSafe.Width > 4 && tightSafe.Height > 4)
        {
            using var tightCrop = image.Clone(x => x
                .Crop(tightSafe)
                .Resize(tightSafe.Width * 3, tightSafe.Height * 3)
                .Grayscale()
                .Contrast(1.4f));
            using var ms = new MemoryStream();
            await tightCrop.SaveAsync(ms, new PngEncoder(), ct);
            combined.AppendLine(await RunTesseractAsync(ms.ToArray(), null, ct));
        }

        return combined.ToString();
    }

    // Tesseract's native engine isn't safe for concurrent Process() calls, and constructing a new
    // engine per request means reloading the ~4MB language model every time — costly when the live
    // loop is firing several requests a second. One engine, reused, guarded by a gate instead.
    private async Task<string> RunTesseractAsync(byte[] pngBytes, string? whitelist, CancellationToken ct)
    {
        await _gate.WaitAsync(ct);
        try
        {
            _engine ??= new TesseractEngine(TessDataPath, "eng", EngineMode.Default);
            _engine.SetVariable("tessedit_char_whitelist", whitelist ?? "");
            using var pix = Pix.LoadFromMemory(pngBytes);
            using var page = _engine.Process(pix, PageSegMode.SparseText);
            return page.GetText() ?? "";
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "OCR pass failed");
            return "";
        }
        finally
        {
            _gate.Release();
        }
    }

    public void Dispose()
    {
        _engine?.Dispose();
        _gate.Dispose();
    }
}
