using System.IO;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;
using RiftBoundTracker.App.Data;
using Image = SixLabors.ImageSharp.Image;

namespace RiftBoundTracker.App.Services;

public record CardMatch(CardEntity Card, int Confidence, string Method);

public record ScanResult(string Method, List<CardMatch> Matches, string? DebugOcrText);

public class ScanService(
    OcrService ocr,
    CardCacheService cache,
    ImageHashService hasher,
    ILogger<ScanService> logger)
{
    private const int ImageMatchMaxDistance = 56; // out of 256 bits; lower = stricter

    public async Task<ScanResult> ScanAsync(Stream imageStream, string? setHint, bool fast = false, CancellationToken ct = default)
    {
        using var raw = await Image.LoadAsync<Rgba32>(imageStream, ct);
        // A light blur before anything else: it smooths out high-frequency sensor noise, and
        // especially moiré (the wavy interference pattern you get photographing a screen instead
        // of a physical card — two overlapping pixel grids beating against each other). Doesn't
        // fully remove moiré — that's an optical effect, not something software can undo — but it
        // keeps it from corrupting the boundary detection, OCR, and art-hash steps that follow.
        raw.Mutate(x => x.AutoOrient().GaussianBlur(0.8f));

        // Photos of the whole card usually include some background (table, hand, etc.) — find the
        // card within the frame so both OCR crop regions and the art hash work relative to the
        // card itself, not raw-photo percentages.
        var cardBounds = PhotoBoundaryDetector.DetectCardBounds(raw);
        using var card = cardBounds == raw.Bounds ? raw.Clone() : raw.Clone(x => x.Crop(cardBounds));

        var ocrText = await ocr.ReadCardNumberTextAsync(card, fast, ct);
        var candidates = CardIdParser.Parse(ocrText);

        foreach (var candidate in candidates)
        {
            // Trust the set the user already has active in the UI over an OCR-guessed set code —
            // a stray letter sequence picked up from the card's rules text is far less reliable
            // than context the user explicitly chose.
            if (setHint is not null)
            {
                var hinted = await cache.FindByNumberAsync(setHint, candidate.Number, ct);
                if (hinted is not null)
                    return new ScanResult("ocr", [new CardMatch(hinted, 100, "ocr")], ocrText);
            }

            if (candidate.SetCode is not null && candidate.SetCode != setHint)
            {
                var bySetCode = await cache.FindByNumberAsync(candidate.SetCode, candidate.Number, ct);
                if (bySetCode is not null)
                    return new ScanResult("ocr", [new CardMatch(bySetCode, 95, "ocr")], ocrText);
            }

            // No usable set context (or it didn't match) — the number might still be unique across the whole cache.
            var all = await cache.FindAllByNumberAsync(candidate.Number, ct);
            if (all.Count == 1)
                return new ScanResult("ocr", [new CardMatch(all[0], 85, "ocr")], ocrText);
            if (all.Count > 1)
                return new ScanResult("ocr-ambiguous",
                    all.Select(c => new CardMatch(c, 50, "ocr")).ToList(), ocrText);
        }

        // The live loop wants speed over thoroughness — it fires several requests a second, so it
        // skips the image-hash search (an O(n) scan + hash compute over the whole cached set) and
        // just reports what OCR saw. The full still-photo/manual flows always run the fallback.
        if (fast)
            return new ScanResult("no-confident-match", [], ocrText);

        logger.LogInformation("OCR found no cache match (text candidates: {Count}); falling back to image match", candidates.Count);

        var photoHash = hasher.ComputeDHash(card);
        var pool = await cache.GetCardsWithHashesAsync(setHint, ct);

        var ranked = pool
            .Select(c => (Card: c, Distance: ImageHashService.HammingDistance(photoHash, c.ImageHash!)))
            .OrderBy(x => x.Distance)
            .Take(5)
            .ToList();

        var strong = ranked.Where(x => x.Distance <= ImageMatchMaxDistance).ToList();
        var chosen = strong.Count > 0 ? strong : ranked.Take(3).ToList();

        var matches = chosen
            .Select(x => new CardMatch(x.Card, Math.Max(0, 100 - x.Distance * 100 / 256), "image"))
            .ToList();

        return new ScanResult(strong.Count > 0 ? "image-match" : "no-confident-match", matches, ocrText);
    }
}
