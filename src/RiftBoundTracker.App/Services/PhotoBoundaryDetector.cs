using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Locates the card within a phone photo that may include background (table, hand, etc.) by
/// finding the bounding box of high-edge-density content — card art/text is visually "busy"
/// compared to a plain background. Everything downstream (OCR crop regions, the hash used for
/// art matching) then works relative to the card itself instead of raw-photo percentages, which
/// otherwise assumes the card already fills the whole frame edge-to-edge.
///
/// This is a lightweight heuristic, not true perspective correction: it handles "card on a
/// fairly plain surface, photographed mostly straight-on" well, and safely falls back to the
/// full photo when the background is too cluttered for the heuristic to trust its own result.
/// </summary>
public static class PhotoBoundaryDetector
{
    public static Rectangle DetectCardBounds(Image<Rgba32> source)
    {
        const int probeSize = 260;
        var scale = Math.Min(1f, (float)probeSize / Math.Max(source.Width, source.Height));
        var probeWidth = Math.Max(1, (int)(source.Width * scale));
        var probeHeight = Math.Max(1, (int)(source.Height * scale));

        using var probe = source.Clone(x => x.Resize(probeWidth, probeHeight).Grayscale());

        var rowEnergy = new float[probeHeight];
        var colEnergy = new float[probeWidth];

        probe.ProcessPixelRows(accessor =>
        {
            for (var y = 1; y < accessor.Height; y++)
            {
                var prevRow = accessor.GetRowSpan(y - 1);
                var row = accessor.GetRowSpan(y);
                for (var x = 1; x < row.Length; x++)
                {
                    var dx = Math.Abs(row[x].PackedValue - row[x - 1].PackedValue);
                    var dy = Math.Abs(row[x].PackedValue - prevRow[x].PackedValue);
                    var e = dx + dy;
                    rowEnergy[y] += e;
                    colEnergy[x] += e;
                }
            }
        });

        var top = FindEdge(rowEnergy, fromStart: true);
        var bottom = FindEdge(rowEnergy, fromStart: false);
        var left = FindEdge(colEnergy, fromStart: true);
        var right = FindEdge(colEnergy, fromStart: false);

        if (bottom <= top || right <= left)
            return source.Bounds;

        var invScale = 1f / scale;
        const float margin = 0.03f;
        var bx0 = Math.Max(0, (int)((left - probeWidth * margin) * invScale));
        var by0 = Math.Max(0, (int)((top - probeHeight * margin) * invScale));
        var bx1 = Math.Min(source.Width, (int)((right + probeWidth * margin) * invScale));
        var by1 = Math.Min(source.Height, (int)((bottom + probeHeight * margin) * invScale));

        var box = new Rectangle(bx0, by0, bx1 - bx0, by1 - by0);

        // If the detected region is implausibly small (background too busy — detection probably
        // failed) or nearly the whole frame already (card already fills it — cropping is a no-op
        // at best, risky at worst), trust the original photo instead.
        var area = (float)(box.Width * box.Height) / (source.Width * source.Height);
        return area is < 0.25f or > 0.97f ? source.Bounds : box;
    }

    private static int FindEdge(float[] profile, bool fromStart)
    {
        var max = profile.Max();
        if (max <= 0) return fromStart ? 0 : profile.Length - 1;
        var threshold = max * 0.12f;

        if (fromStart)
        {
            for (var i = 0; i < profile.Length; i++)
                if (profile[i] >= threshold) return i;
            return 0;
        }

        for (var i = profile.Length - 1; i >= 0; i--)
            if (profile[i] >= threshold) return i;
        return profile.Length - 1;
    }
}
