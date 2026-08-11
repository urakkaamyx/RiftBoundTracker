using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Difference-hash (dHash) perceptual image hashing over a 16x16 grid (256 bits): two visually
/// similar images produce hashes with a small Hamming distance, even after re-encoding or minor
/// lighting/angle differences from a phone photo. 256 bits (vs. a coarser 64-bit hash) keeps
/// enough fine-grained detail to tell visually similar cards apart — many Riftbound cards in the
/// same domain share a similar overall color palette.
/// </summary>
public class ImageHashService
{
    private const int GridSize = 16;

    public async Task<byte[]> ComputeDHashAsync(Stream imageStream, CancellationToken ct = default)
    {
        using var image = await Image.LoadAsync<Rgba32>(imageStream, ct);
        image.Mutate(x => x.AutoOrient());
        return ComputeDHash(image);
    }

    public byte[] ComputeDHash(Image<Rgba32> image)
    {
        using var gray = image.CloneAs<L8>();
        gray.Mutate(x => x.Resize(GridSize + 1, GridSize));

        var bits = new bool[GridSize * GridSize];
        var i = 0;
        for (var y = 0; y < GridSize; y++)
        {
            for (var x = 0; x < GridSize; x++)
            {
                var left = gray[x, y].PackedValue;
                var right = gray[x + 1, y].PackedValue;
                bits[i++] = left > right;
            }
        }

        var bytes = new byte[GridSize * GridSize / 8];
        for (var b = 0; b < bits.Length; b++)
            if (bits[b])
                bytes[b / 8] |= (byte)(1 << (b % 8));
        return bytes;
    }

    public static int HammingDistance(byte[] a, byte[] b)
    {
        var len = Math.Min(a.Length, b.Length);
        var distance = Math.Abs(a.Length - b.Length) * 8;
        for (var i = 0; i < len; i++)
            distance += System.Numerics.BitOperations.PopCount((uint)(a[i] ^ b[i]));
        return distance;
    }
}
