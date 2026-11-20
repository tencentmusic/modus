use aes_gcm::{
    aead::{Aead, KeyInit},
    Aes256Gcm, Key, Nonce,
};
use anyhow::{Context, Result};
use std::path::Path;

pub const ENC_PREFIX: &str = "enc:v1:";

/// Load an existing 32-byte key from `path`, or generate and persist a new one.
///
/// If the file exists but has an unexpected size, returns an error instead of
/// silently regenerating — regenerating would make all previously encrypted
/// values permanently undecryptable.
pub fn load_or_create_key(path: &Path) -> Result<[u8; 32]> {
    if path.exists() {
        let bytes = std::fs::read(path).context("Failed to read secret key file")?;
        anyhow::ensure!(
            bytes.len() == 32,
            "Secret key file '{}' is corrupted ({} bytes, expected 32). \
             Delete it manually to regenerate, but note that existing encrypted values will be lost.",
            path.display(),
            bytes.len()
        );
        let mut key = [0u8; 32];
        key.copy_from_slice(&bytes);
        return Ok(key);
    }

    let mut key = [0u8; 32];
    use rand::RngCore;
    rand::thread_rng().fill_bytes(&mut key);
    std::fs::write(path, key).context("Failed to write secret key file")?;
    set_owner_readonly(path);
    Ok(key)
}

/// On Unix, restrict the key file to owner-only access (0600).
#[cfg(unix)]
fn set_owner_readonly(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
}

#[cfg(not(unix))]
fn set_owner_readonly(_path: &Path) {}

/// Encrypt `plaintext` with AES-256-GCM and return an `enc:v1:<hex>` string.
pub fn encrypt(key: &[u8; 32], plaintext: &str) -> Result<String> {
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));

    let mut nonce_bytes = [0u8; 12];
    use rand::RngCore;
    rand::thread_rng().fill_bytes(&mut nonce_bytes);
    let nonce = Nonce::from_slice(&nonce_bytes);

    let ciphertext = cipher
        .encrypt(nonce, plaintext.as_bytes())
        .map_err(|_| anyhow::anyhow!("Encryption failed"))?;

    // Store as hex(nonce || ciphertext) so the result is printable ASCII.
    let mut combined = nonce_bytes.to_vec();
    combined.extend_from_slice(&ciphertext);
    Ok(format!("{}{}", ENC_PREFIX, hex::encode(&combined)))
}

/// Decrypt an `enc:v1:<hex>` string.  Returns an error if the value is not
/// a recognised encrypted blob (callers can detect plaintext via `is_encrypted`).
pub fn decrypt(key: &[u8; 32], value: &str) -> Result<String> {
    let hex_str = value
        .strip_prefix(ENC_PREFIX)
        .ok_or_else(|| anyhow::anyhow!("Value is not an encrypted blob"))?;

    let combined = hex::decode(hex_str).context("Invalid hex in encrypted value")?;
    if combined.len() < 12 {
        anyhow::bail!("Encrypted value is too short to contain a nonce");
    }

    let (nonce_bytes, ciphertext) = combined.split_at(12);
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let nonce = Nonce::from_slice(nonce_bytes);

    let plaintext = cipher
        .decrypt(nonce, ciphertext)
        .map_err(|_| anyhow::anyhow!("Decryption failed — key mismatch or data corrupted"))?;

    String::from_utf8(plaintext).context("Decrypted bytes are not valid UTF-8")
}

/// Returns true if `value` looks like it was produced by `encrypt()`.
pub fn is_encrypted(value: &str) -> bool {
    value.starts_with(ENC_PREFIX)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_key() -> [u8; 32] {
        [0x42u8; 32]
    }

    #[test]
    fn round_trip() {
        let key = test_key();
        let plaintext = "https://ghp_secret@github.com/user/repo.git";
        let encrypted = encrypt(&key, plaintext).unwrap();
        assert!(is_encrypted(&encrypted));
        assert_ne!(encrypted, plaintext);
        let decrypted = decrypt(&key, &encrypted).unwrap();
        assert_eq!(decrypted, plaintext);
    }

    #[test]
    fn different_nonces_each_time() {
        let key = test_key();
        let a = encrypt(&key, "same").unwrap();
        let b = encrypt(&key, "same").unwrap();
        // Nonces are random, so ciphertexts must differ even for the same plaintext.
        assert_ne!(a, b);
    }

    #[test]
    fn wrong_key_fails() {
        let key_a = test_key();
        let key_b = [0x99u8; 32];
        let encrypted = encrypt(&key_a, "secret").unwrap();
        assert!(decrypt(&key_b, &encrypted).is_err());
    }

    #[test]
    fn is_encrypted_detects_prefix() {
        assert!(is_encrypted("enc:v1:deadbeef"));
        assert!(!is_encrypted("https://user:pass@host"));
        assert!(!is_encrypted(""));
    }

    #[test]
    fn load_or_create_key_creates_and_reloads() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join(".secret.key");

        let key1 = load_or_create_key(&path).unwrap();
        assert!(path.exists());

        let key2 = load_or_create_key(&path).unwrap();
        assert_eq!(key1, key2);
    }

    #[test]
    fn corrupted_key_file_returns_error() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join(".secret.key");
        // Write a file with wrong length.
        std::fs::write(&path, b"too-short").unwrap();
        let err = load_or_create_key(&path).unwrap_err();
        assert!(err.to_string().contains("corrupted"));
    }

    #[cfg(unix)]
    #[test]
    fn key_file_has_owner_only_permissions() {
        use std::os::unix::fs::PermissionsExt;
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join(".secret.key");
        load_or_create_key(&path).unwrap();
        let mode = std::fs::metadata(&path).unwrap().permissions().mode();
        assert_eq!(mode & 0o777, 0o600);
    }
}
