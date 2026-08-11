using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

namespace RiftBoundTracker.App.Services;

/// <summary>
/// Generates (and persists) a self-signed TLS certificate covering localhost plus the machine's
/// current LAN IPs, so the phone can reach the server over HTTPS — required for live camera
/// access (getUserMedia only works in a "secure context"). The phone will still show a one-time
/// "connection not private" warning per browser, since this cert isn't signed by a real CA; the
/// user taps through it once and the exception is remembered after that.
/// </summary>
public static class DevCertificateProvider
{
    public static X509Certificate2 GetOrCreate(string certPath, IReadOnlyList<string> lanIps)
    {
        var ipAddresses = new List<IPAddress> { IPAddress.Loopback, IPAddress.IPv6Loopback };
        foreach (var ip in lanIps)
            if (IPAddress.TryParse(ip, out var parsed))
                ipAddresses.Add(parsed);

        if (File.Exists(certPath))
        {
            try
            {
                var existing = X509CertificateLoader.LoadPkcs12FromFile(certPath, null, X509KeyStorageFlags.Exportable);
                if (existing.NotAfter > DateTime.UtcNow.AddDays(30) && CoversAllIps(existing, ipAddresses))
                    return existing;
                existing.Dispose();
            }
            catch
            {
                // Corrupt or unreadable — fall through and regenerate.
            }
        }

        var cert = Create(ipAddresses);
        Directory.CreateDirectory(Path.GetDirectoryName(certPath)!);
        File.WriteAllBytes(certPath, cert.Export(X509ContentType.Pfx));
        return cert;
    }

    private static bool CoversAllIps(X509Certificate2 cert, List<IPAddress> ips)
    {
        var san = cert.Extensions["2.5.29.17"]; // Subject Alternative Name
        if (san is null) return false;
        var sanText = san.Format(false);
        return ips.All(ip => sanText.Contains(ip.ToString()));
    }

    private static X509Certificate2 Create(List<IPAddress> ipAddresses)
    {
        using var rsa = RSA.Create(2048);
        var req = new CertificateRequest(
            "CN=RiftBound Vault (local)", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);

        req.CertificateExtensions.Add(new X509BasicConstraintsExtension(false, false, 0, false));
        req.CertificateExtensions.Add(new X509KeyUsageExtension(
            X509KeyUsageFlags.DigitalSignature | X509KeyUsageFlags.KeyEncipherment, false));
        req.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(
            [new Oid("1.3.6.1.5.5.7.3.1")], false)); // serverAuth

        var san = new SubjectAlternativeNameBuilder();
        san.AddDnsName("localhost");
        foreach (var ip in ipAddresses)
            san.AddIpAddress(ip);
        req.CertificateExtensions.Add(san.Build());

        var cert = req.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-1), DateTimeOffset.UtcNow.AddYears(2));

        // Round-trip through a PFX blob: CreateSelfSigned's private key isn't reliably reusable by
        // Kestrel as-is on every platform, but re-loading from an exported PFX is.
        return X509CertificateLoader.LoadPkcs12(cert.Export(X509ContentType.Pfx), null, X509KeyStorageFlags.Exportable);
    }
}
