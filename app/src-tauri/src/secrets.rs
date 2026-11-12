//! API keys in the OS credential store, shared with the Python CLI (one entry for both).
//!
//! Python `keyring` (which the CLI uses) stores service "podcastz", user name = provider.
//! On Windows it writes the generic credential under TargetName "podcastz" (first user) or
//! "<user>@podcastz" (any other user) and reads both; the Rust `keyring` crate would use
//! "<user>.podcastz", so on Windows this module talks to Credential Manager directly with
//! Python's naming and UTF-16 blob encoding. Elsewhere the `keyring` crate matches Python
//! (Keychain / Secret Service take service and user name as they are).
//! Values only go in; the UI sees where a key comes from, never the key.

use serde::Serialize;

pub const SERVICE: &str = "podcastz";
pub const PROVIDERS: [(&str, &str); 2] = [("openai", "OPENAI_API_KEY"), ("elevenlabs", "ELEVENLABS_API_KEY")];

#[derive(Serialize)]
pub struct KeyInfo {
    provider: String,
    source: Option<String>,
    env: Vec<String>,
}

pub fn env_names(provider: &str) -> Vec<String> {
    let own = PROVIDERS.iter().find(|(p, _)| *p == provider).map(|(_, e)| e.to_string()).unwrap_or_default();
    vec![format!("PODCASTZ_{}_API_KEY", provider.to_uppercase()), own]
}

pub fn check_provider(provider: &str) -> Result<(), String> {
    if PROVIDERS.iter().any(|(p, _)| *p == provider) { Ok(()) } else { Err(format!("unknown provider {provider}")) }
}

fn env_set(name: &str) -> bool {
    std::env::var(name).map(|v| !v.is_empty()).unwrap_or(false)
}

/// Where the key would come from, in the CLI's order (devstackz ADR 0006):
/// PODCASTZ_<P>_API_KEY override, then the stored key, then the provider's generic variable.
pub fn source(provider: &str) -> Option<String> {
    source_with(provider, |p| matches!(store::get(SERVICE, p), Ok(Some(_))), env_set)
}

fn source_with(provider: &str, stored: impl Fn(&str) -> bool, env: impl Fn(&str) -> bool) -> Option<String> {
    let names = env_names(provider);
    if env(&names[0]) {
        return Some(names[0].clone());
    }
    if stored(provider) {
        return Some("store".into());
    }
    (!names[1].is_empty() && env(&names[1])).then(|| names[1].clone())
}

#[cfg(test)]
mod order_tests {
    use super::*;

    #[test]
    fn lookup_order_matches_cli() {
        let none = |_: &str| false;
        assert_eq!(source_with("openai", none, none), None);
        assert_eq!(source_with("openai", none, |n| n == "OPENAI_API_KEY").as_deref(), Some("OPENAI_API_KEY"));
        assert_eq!(source_with("openai", |_| true, |n| n == "OPENAI_API_KEY").as_deref(), Some("store"));
        assert_eq!(source_with("openai", |_| true, |_| true).as_deref(), Some("PODCASTZ_OPENAI_API_KEY"));
    }
}

pub fn status() -> Vec<KeyInfo> {
    PROVIDERS.iter().map(|(p, _)| KeyInfo { provider: p.to_string(), source: source(p), env: env_names(p) }).collect()
}

pub fn set(provider: &str, value: &str) -> Result<(), String> {
    check_provider(provider)?;
    let value = value.trim();
    if value.is_empty() {
        return Err("empty key".into());
    }
    store::set(SERVICE, provider, value)
}

pub fn delete(provider: &str) -> Result<bool, String> {
    check_provider(provider)?;
    store::delete(SERVICE, provider)
}

#[cfg(windows)]
pub mod store {
    use std::ptr::null_mut;
    use windows_sys::Win32::Security::Credentials::{
        CredDeleteW, CredFree, CredReadW, CredWriteW, CREDENTIALW, CRED_PERSIST_ENTERPRISE, CRED_TYPE_GENERIC,
    };

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect()
    }

    unsafe fn from_wide(p: *const u16) -> String {
        if p.is_null() {
            return String::new();
        }
        let mut len = 0;
        while unsafe { *p.add(len) } != 0 {
            len += 1;
        }
        String::from_utf16_lossy(unsafe { std::slice::from_raw_parts(p, len) })
    }

    /// (user name, secret) stored under a target, if any.
    fn read(target: &str) -> Option<(String, String)> {
        let t = wide(target);
        let mut cred: *mut CREDENTIALW = null_mut();
        let ok = unsafe { CredReadW(t.as_ptr(), CRED_TYPE_GENERIC, 0, &mut cred) };
        if ok == 0 || cred.is_null() {
            return None;
        }
        let res = unsafe {
            let c = &*cred;
            let user = from_wide(c.UserName);
            let bytes = std::slice::from_raw_parts(c.CredentialBlob, c.CredentialBlobSize as usize);
            let units: Vec<u16> = bytes.as_chunks::<2>().0.iter().map(|b| u16::from_le_bytes(*b)).collect();
            (user, String::from_utf16_lossy(&units))
        };
        unsafe { CredFree(cred as *const _) };
        Some(res)
    }

    fn write(target: &str, user: &str, secret: &str) -> Result<(), String> {
        let mut t = wide(target);
        let mut u = wide(user);
        let blob: Vec<u8> = secret.encode_utf16().flat_map(|c| c.to_le_bytes()).collect();
        let mut cred: CREDENTIALW = unsafe { std::mem::zeroed() };
        cred.Type = CRED_TYPE_GENERIC;
        cred.TargetName = t.as_mut_ptr();
        cred.UserName = u.as_mut_ptr();
        cred.CredentialBlobSize = blob.len() as u32;
        cred.CredentialBlob = blob.as_ptr() as *mut u8;
        cred.Persist = CRED_PERSIST_ENTERPRISE;
        let ok = unsafe { CredWriteW(&cred, 0) };
        if ok == 0 { Err(format!("cannot write credential ({})", std::io::Error::last_os_error())) } else { Ok(()) }
    }

    fn remove(target: &str) -> bool {
        let t = wide(target);
        unsafe { CredDeleteW(t.as_ptr(), CRED_TYPE_GENERIC, 0) != 0 }
    }

    fn compound(user: &str, service: &str) -> String {
        format!("{user}@{service}")
    }

    /// Same lookup as Python keyring: target "<service>" if its user name matches, else "<user>@<service>".
    pub fn get(service: &str, user: &str) -> Result<Option<String>, String> {
        if let Some((u, v)) = read(service)
            && u == user
        {
            return Ok(Some(v));
        }
        Ok(read(&compound(user, service)).map(|(_, v)| v))
    }

    /// Same placement as Python keyring: overwrite "<service>" if it belongs to this user,
    /// otherwise use "<user>@<service>" (Python finds both).
    pub fn set(service: &str, user: &str, secret: &str) -> Result<(), String> {
        match read(service) {
            Some((u, _)) if u == user => write(service, user, secret),
            Some(_) => write(&compound(user, service), user, secret),
            None => write(service, user, secret),
        }
    }

    pub fn delete(service: &str, user: &str) -> Result<bool, String> {
        let mut deleted = false;
        if matches!(read(service), Some((u, _)) if u == user) {
            deleted |= remove(service);
        }
        if read(&compound(user, service)).is_some() {
            deleted |= remove(&compound(user, service));
        }
        Ok(deleted)
    }

    #[cfg(test)]
    mod tests {
        // Touches the real Credential Manager under a throwaway service name; run explicitly:
        // cargo test -- --ignored interop
        use super::*;

        #[test]
        #[ignore]
        fn interop_roundtrip_two_users() {
            let svc = "podcastz-interop-test";
            set(svc, "openai", "dummy-1").unwrap();
            set(svc, "elevenlabs", "dummy-2").unwrap();
            assert_eq!(get(svc, "openai").unwrap().as_deref(), Some("dummy-1"));
            assert_eq!(get(svc, "elevenlabs").unwrap().as_deref(), Some("dummy-2"));
            set(svc, "openai", "dummy-3").unwrap();
            assert_eq!(get(svc, "openai").unwrap().as_deref(), Some("dummy-3"));
            assert!(delete(svc, "openai").unwrap());
            assert!(delete(svc, "elevenlabs").unwrap());
            assert_eq!(get(svc, "openai").unwrap(), None);
        }

        /// Step 1 of the Python cross-check: Rust writes, Python reads (see docs/keys-interop.md).
        #[test]
        #[ignore]
        fn interop_write_for_python() {
            set("podcastz-interop-py", "openai", "dummy-a").unwrap();
            set("podcastz-interop-py", "elevenlabs", "dummy-b").unwrap();
        }

        /// Step 2: Python wrote "podcastz-interop-rs"; Rust reads and cleans up.
        #[test]
        #[ignore]
        fn interop_read_from_python() {
            assert_eq!(get("podcastz-interop-rs", "openai").unwrap().as_deref(), Some("dummy-c"));
            assert_eq!(get("podcastz-interop-rs", "elevenlabs").unwrap().as_deref(), Some("dummy-d"));
            assert!(delete("podcastz-interop-rs", "openai").unwrap());
            assert!(delete("podcastz-interop-rs", "elevenlabs").unwrap());
        }
    }
}

#[cfg(not(windows))]
pub mod store {
    pub fn get(service: &str, user: &str) -> Result<Option<String>, String> {
        let e = keyring::Entry::new(service, user).map_err(|e| e.to_string())?;
        match e.get_password() {
            Ok(v) => Ok(Some(v)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(e) => Err(e.to_string()),
        }
    }

    pub fn set(service: &str, user: &str, secret: &str) -> Result<(), String> {
        keyring::Entry::new(service, user).and_then(|e| e.set_password(secret)).map_err(|e| e.to_string())
    }

    pub fn delete(service: &str, user: &str) -> Result<bool, String> {
        let e = keyring::Entry::new(service, user).map_err(|e| e.to_string())?;
        match e.delete_credential() {
            Ok(()) => Ok(true),
            Err(keyring::Error::NoEntry) => Ok(false),
            Err(e) => Err(e.to_string()),
        }
    }
}
