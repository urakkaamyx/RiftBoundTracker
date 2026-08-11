using System.Runtime.InteropServices.WindowsRuntime;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;
using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Rectangle = SixLabors.ImageSharp.Rectangle;
using Image = SixLabors.ImageSharp.Image;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Reads the collector-number text near a card's bottom-left corner using Windows' built-in OCR
/// engine (Windows.Media.Ocr) rather than a bundled third-party library. Noticeably more accurate
/// on the small, stylized card print, ships with Windows itself (no native DLLs or language-data
/// files to bundle, version, or fight with PublishSingleFile over), and doesn't need the manual
/// multi-threshold binarization sweep Tesseract benefited from — it handles color/contrast
/// variance in real photos on its own, so one clean pass per region is enough.
/// </summary>
public class OcrService
{
    private readonly ILogger<OcrService> _logger;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly OcrEngine? _engine;

    public OcrService(ILogger<OcrService> logger)
    {
        _logger = logger;
        _engine = OcrEngine.TryCreateFromLanguage(new Language("en-US"))
                  ?? OcrEngine.TryCreateFromUserProfileLanguages();

        if (_engine is null)
            _logger.LogWarning(
                "No OCR language is installed on this Windows install — card-number recognition " +
                "will be unavailable until one is (Settings > Time & Language > Language & region " +
                "> add English, then 'Optional features' on that language > add 'Handwriting').");
    }

    // Upper bound on the long side fed to the OCR engine per pass. Small crops (the bottom-band
    // regions) still get upscaled up to 3x for better recognition of tiny print; a full-resolution
    // photo used as-is (see below) gets capped down instead so it doesn't blow up OCR latency.
    private const int MaxOcrDimension = 2200;

    /// <summary>
    /// <paramref name="image"/> should already be oriented and cropped down to just the card (see
    /// PhotoBoundaryDetector) — region percentages are relative to the card, not an arbitrary
    /// photo that may include background.
    ///
    /// Tries the bottom-band regions where the number usually sits on a whole-card photo, AND the
    /// full frame as-is — someone deliberately zooming in tight on just the number (a very natural
    /// thing to try when OCR is struggling) means the number may no longer be confined to that
    /// bottom band at all, so a fixed geographic crop guess would cut off the very text it's
    /// trying to read. Aggregating all passes and letting CardIdParser scan the whole combined
    /// text for a match is more robust than betting on one crop being right.
    ///
    /// <paramref name="fast"/> trims this for the live-camera loop, which fires a request every
    /// ~800ms and needs to come back quickly; the still-photo/manual flows try every candidate
    /// region since latency doesn't matter there.
    /// </summary>
    public async Task<string> ReadCardNumberTextAsync(Image<Rgba32> image, bool fast, CancellationToken ct = default)
    {
        if (_engine is null) return "";

        var w = image.Width;
        var h = image.Height;

        // A tight bottom-left corner (where the number usually sits), a wider bottom band (in
        // case the crop isn't tight to the card edges), and the full frame (in case the photo is
        // already zoomed into just the number, or the number sits somewhere the other two miss).
        var tightRegion = new Rectangle(0, (int)(h * 0.80), (int)(w * 0.45), (int)(h * 0.20));
        var wideRegion = new Rectangle(0, (int)(h * 0.82), w, (int)(h * 0.18));
        var fullRegion = image.Bounds;
        var regions = fast ? [tightRegion, fullRegion] : new[] { tightRegion, wideRegion, fullRegion };

        var combined = new System.Text.StringBuilder();
        foreach (var region in regions)
        {
            ct.ThrowIfCancellationRequested();
            var safe = Rectangle.Intersect(region, image.Bounds);
            if (safe.Width <= 4 || safe.Height <= 4) continue;

            combined.AppendLine(await RecognizeAsync(image, safe, ct));
        }

        return combined.ToString();
    }

    private async Task<string> RecognizeAsync(Image<Rgba32> source, Rectangle region, CancellationToken ct)
    {
        try
        {
            var longSide = Math.Max(region.Width, region.Height);
            var target = Math.Min(longSide * 3, MaxOcrDimension);
            var scale = (float)target / longSide;
            var newWidth = Math.Max(1, (int)(region.Width * scale));
            var newHeight = Math.Max(1, (int)(region.Height * scale));

            using var crop = source.Clone(x => x.Crop(region).Resize(newWidth, newHeight));
            using var bitmap = ToSoftwareBitmap(crop);

            // OcrEngine instances aren't documented as safe for concurrent RecognizeAsync calls —
            // serialize them rather than risk it, same as the previous engine did.
            await _gate.WaitAsync(ct);
            try
            {
                var result = await _engine!.RecognizeAsync(bitmap);
                return result.Text ?? "";
            }
            finally
            {
                _gate.Release();
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "OCR pass failed");
            return "";
        }
    }

    private static SoftwareBitmap ToSoftwareBitmap(Image<Rgba32> image)
    {
        using var bgra = image.CloneAs<Bgra32>();
        var bytes = new byte[bgra.Width * bgra.Height * 4];
        bgra.CopyPixelDataTo(bytes);

        var bitmap = new SoftwareBitmap(BitmapPixelFormat.Bgra8, bgra.Width, bgra.Height, BitmapAlphaMode.Ignore);
        bitmap.CopyFromBuffer(bytes.AsBuffer());
        return bitmap;
    }
}
