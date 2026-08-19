namespace RiftBoundTracker.App.Services;

public sealed record RiftAtlasDeckEntry(string SetId, string Code, int Quantity);
public sealed record RiftAtlasDecodedDeck(
    List<RiftAtlasDeckEntry> MainDeck, List<RiftAtlasDeckEntry> Sideboard, string? ChosenChampionSetId, string? ChosenChampionCode);

/// <summary>
/// Decodes RiftAtlas / Piltover Archive "deck code" strings — a compact base32-encoded format for
/// sharing a full decklist as one short string — into a flat list of (set, collector code,
/// quantity) entries that DeckService.ImportAsync can resolve the exact same way it already
/// resolves RiftKeep/RiftAtlas plain-text lines, via CardCacheService.FindByCodeAsync.
///
/// This is a from-scratch C# re-implementation of the format documented at
/// https://github.com/Piltover-Archive/RiftboundDeckCodes (Apache License 2.0, Copyright 2025
/// PiltoverArchive) — no .NET package exists for it, so the algorithm (varint byte arrays,
/// base32 encoding, set/variant grouping, and the format-1 version 1-5 wire layout) is
/// reproduced here rather than ported line-for-line from their TypeScript source. See that
/// repo's README for the authoritative format specification this follows; encoding (the reverse
/// direction) is intentionally not implemented since nothing in this app needs to produce codes,
/// only read decks other tools already generated.
/// </summary>
public static class RiftAtlasDeckCodeService
{
    private const string Base32Alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    private const int Format = 1;
    private const int MaxSupportedVersion = 5;

    // Index position is the wire value written for each set/variant — must match the reference
    // encoder's SET_MAP/VARIANT_MAP exactly, not just contain the same entries.
    private static readonly string[] SetByIndex = ["OGN", "OGS", "ARC", "SFD", "UNL", "VEN", "RAD"];
    private static readonly string[] VariantSuffixByIndex = ["", "a", "s", "b"];

    /// <summary>
    /// A deck code is a single unbroken run of base32 characters — unlike every other supported
    /// import format (RiftKeep, RiftAtlas plain-text, RiftDecks), which are always multi-line with
    /// spaces. Checking for whitespace first avoids running the full base32 alphabet check against
    /// an entire multi-line paste for every import.
    /// </summary>
    public static bool LooksLikeDeckCode(string text)
    {
        var trimmed = text.Trim();
        if (trimmed.Length < 8 || trimmed.Any(char.IsWhiteSpace)) return false;
        return trimmed.All(c => Base32Alphabet.Contains(char.ToUpperInvariant(c)));
    }

    public static RiftAtlasDecodedDeck Decode(string code)
    {
        var reader = new VarintReader(Base32Decode(code.Trim()));

        var formatVersion = reader.ReadByte();
        var format = (formatVersion >> 4) & 0x0F;
        var version = formatVersion & 0x0F;
        if (format != Format) throw new FormatException($"Unsupported deck code format: {format}.");
        if (version > MaxSupportedVersion) throw new FormatException($"Unsupported deck code version: {version}.");

        // v5 carries an explicit deck-level bit for whether card numbers have a per-card
        // normal/rune/special flag byte; for v1-v4 this is implied by the version itself
        // (v4+ always flags, v1-v3 never does — rune/special cards didn't exist yet).
        bool flagged;
        if (version >= 5)
        {
            var prefixFlag = reader.ReadByte();
            if (prefixFlag > 1) throw new FormatException($"Unsupported deck prefix flag: {prefixFlag}.");
            flagged = prefixFlag == 1;
        }
        else
        {
            flagged = version >= 4;
        }

        List<RiftAtlasDeckEntry> mainDeck;
        List<RiftAtlasDeckEntry> sideboard = [];
        if (version >= 5)
        {
            mainDeck = DecodeSectionSparse(reader, flagged);
            sideboard = DecodeSectionSparse(reader, flagged);
        }
        else
        {
            mainDeck = DecodeSectionFixed(reader, 12, flagged);
            if (version >= 2) sideboard = DecodeSectionFixed(reader, 3, flagged);
        }

        string? championSetId = null, championCode = null;
        if (version >= 3)
        {
            var hasChampion = reader.ReadByte();
            if (hasChampion == 0x01)
            {
                var set = reader.ReadByte();
                var variant = reader.ReadByte();
                var (number, prefix) = ReadCardNumber(reader, flagged);
                championSetId = SetIdFor(set);
                championCode = FormatCode(prefix, number, VariantSuffixFor(variant));
            }
        }

        return new RiftAtlasDecodedDeck(mainDeck, sideboard, championSetId, championCode);
    }

    private static List<RiftAtlasDeckEntry> DecodeSectionFixed(VarintReader reader, int maxCount, bool flagged)
    {
        var result = new List<RiftAtlasDeckEntry>();
        for (var count = maxCount; count >= 1; count--)
        {
            var numGroups = reader.PopVarint();
            for (var g = 0; g < numGroups; g++)
            {
                var numCards = reader.PopVarint();
                var setId = SetIdFor(reader.ReadByte());
                var variantSuffix = VariantSuffixFor(reader.ReadByte());
                for (var j = 0; j < numCards; j++)
                {
                    var (number, prefix) = ReadCardNumber(reader, flagged);
                    result.Add(new RiftAtlasDeckEntry(setId, FormatCode(prefix, number, variantSuffix), count));
                }
            }
        }
        return result;
    }

    private static List<RiftAtlasDeckEntry> DecodeSectionSparse(VarintReader reader, bool flagged)
    {
        var result = new List<RiftAtlasDeckEntry>();
        var numCounts = reader.PopVarint();
        for (var i = 0; i < numCounts; i++)
        {
            var count = reader.PopVarint();
            var numGroups = reader.PopVarint();
            for (var g = 0; g < numGroups; g++)
            {
                var numCards = reader.PopVarint();
                var setId = SetIdFor(reader.ReadByte());
                var variantSuffix = VariantSuffixFor(reader.ReadByte());
                for (var j = 0; j < numCards; j++)
                {
                    var (number, prefix) = ReadCardNumber(reader, flagged);
                    result.Add(new RiftAtlasDeckEntry(setId, FormatCode(prefix, number, variantSuffix), count));
                }
            }
        }
        return result;
    }

    // Returns (number, prefix) where prefix is "" (normal card), "R" (rune), or "SP" (special).
    private static (int Number, string Prefix) ReadCardNumber(VarintReader reader, bool flagged)
    {
        if (!flagged) return (reader.PopVarint(), "");
        var flag = reader.ReadByte();
        var number = reader.PopVarint();
        return flag switch
        {
            0x00 => (number, ""),
            0x01 => (number, "R"),
            0x02 => (number, "SP"),
            _ => throw new FormatException($"Unknown card number-prefix flag: {flag}."),
        };
    }

    private static string SetIdFor(int index) =>
        index >= 0 && index < SetByIndex.Length ? SetByIndex[index] : throw new FormatException($"Unknown set index: {index}.");

    private static string VariantSuffixFor(int index) =>
        index >= 0 && index < VariantSuffixByIndex.Length ? VariantSuffixByIndex[index] : throw new FormatException($"Unknown variant index: {index}.");

    // Rune numbers are conventionally rendered 2-digit ("R01"), everything else 3-digit ("007") —
    // matches the reference decoder's own padding per prefix, so decoded codes line up with how
    // this app's own catalog already stores CollectorCode for the same cards.
    private static string FormatCode(string prefix, int number, string variantSuffix) => prefix switch
    {
        "R" => $"R{number:D2}{variantSuffix}",
        "SP" => $"SP{number}{variantSuffix}",
        _ => $"{number:D3}{variantSuffix}",
    };

    private static byte[] Base32Decode(string text)
    {
        var bytes = new List<byte>();
        int buffer = 0, bitsLeft = 0;
        foreach (var ch in text)
        {
            var value = Base32Alphabet.IndexOf(char.ToUpperInvariant(ch));
            if (value < 0) throw new FormatException($"Invalid character in deck code: '{ch}'.");
            buffer = (buffer << 5) | value;
            bitsLeft += 5;
            if (bitsLeft >= 8)
            {
                bitsLeft -= 8;
                bytes.Add((byte)((buffer >> bitsLeft) & 0xFF));
            }
        }
        return bytes.ToArray();
    }

    // Mirrors the reference implementation's VarintTranslator: 7 payload bits per byte, MSB as a
    // continuation flag, least-significant group first.
    private sealed class VarintReader(byte[] bytes)
    {
        private int _pos;

        public byte ReadByte()
        {
            if (_pos >= bytes.Length) throw new FormatException("Deck code ended unexpectedly.");
            return bytes[_pos++];
        }

        public int PopVarint()
        {
            var result = 0;
            var shift = 0;
            while (true)
            {
                if (_pos >= bytes.Length) throw new FormatException("Deck code ended unexpectedly while reading a varint.");
                var b = bytes[_pos++];
                result |= (b & 0x7F) << shift;
                if ((b & 0x80) == 0) return result;
                shift += 7;
            }
        }
    }
}
