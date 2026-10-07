# Sürüm Çıkarma (macOS)

## Bir kerelik kurulum

### 1. İmza sertifikası (GitHub Secrets)
1. Anahtar Zinciri Erişimi → "Developer ID Application: BURAK CEYLAN (4F8TVA268Y)"
   sertifikasını (özel anahtarıyla birlikte) sağ tık → Dışa Aktar → `cert.p12`, bir parola belirle.
2. Secrets'a ekle:
   ```bash
   base64 -i cert.p12 | gh secret set MACOS_CERT_P12
   gh secret set MACOS_CERT_PASSWORD   # parolayı yapıştır
   rm cert.p12
   ```

### 2. Notarization API anahtarı
1. App Store Connect → Users and Access → Integrations → Team Keys → "+",
   Access: **Developer**. `AuthKey_<KEYID>.p8` dosyasını indir (bir kez indirilebilir).
2. Secrets'a ekle:
   ```bash
   gh secret set NOTARY_KEY_P8 < AuthKey_<KEYID>.p8
   gh secret set NOTARY_KEY_ID      # Key ID
   gh secret set NOTARY_ISSUER      # Issuer ID (sayfanın üstünde)
   ```
3. Yerelde derleme için keychain profili:
   ```bash
   xcrun notarytool store-credentials transkript-notary \
     --key AuthKey_<KEYID>.p8 --key-id <KEYID> --issuer <ISSUER>
   ```

## Her sürümde
1. `src/__init__.py` içindeki `__version__`'ı artır (ör. `0.1.1`), commit + push.
2. Etiketle: `git tag v0.1.1 && git push origin v0.1.1`
3. Actions'taki `release` işini izle: `gh run watch`
4. Release sayfasındaki `.dmg`'yi indirip doğrula:
   `spctl -a -vv -t open --context context:primary-signature Transkript-0.1.1.dmg`
5. Kullanıcıya Release linkini gönder; güncelleme = yeni `.dmg`'yi indirip uygulamayı üstüne sürüklemek.

## Yerelde derleme
`bash packaging/build_macos.sh` (hızlı deneme: `SKIP_NOTARIZE=1`). Değişkenler betiğin başında.
