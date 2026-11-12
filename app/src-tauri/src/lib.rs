//! podcastz desktop shell: runs the `podcastz` CLI (the sidecar) per task and streams its JSON lines
//! to the UI, launches the user's own AI session in the workspace, and marks the app as running in
//! `<workspace>/.podcastz/app.json` so the session's tools know the app is there.
//! The app never calls a language model and never sees API key values (it passes them to the CLI on stdin).

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{Emitter, Manager, State};

mod secrets;

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Default)]
struct Jobs {
    next: AtomicU32,
    children: Mutex<HashMap<u32, Arc<Mutex<Child>>>>,
}

#[derive(Default)]
struct Presence(Mutex<Option<PathBuf>>);

#[derive(Clone, Serialize)]
struct JobEvent {
    id: u32,
    line: Option<String>,
    stderr: Option<String>,
    done: bool,
    code: Option<i32>,
}

/// Set on every process the app starts; an app instance that finds it exits at once.
/// Guards against the app ever running itself instead of the CLI (that once spawned windows without end).
const CHILD_MARKER: &str = "PODCASTZ_SPAWNED_BY_APP";

fn same_file(a: &std::path::Path, b: &std::path::Path) -> bool {
    match (a.canonicalize(), b.canonicalize()) {
        (Ok(x), Ok(y)) => x == y,
        _ => false,
    }
}

/// Windows GUI-subsystem executable (a desktop app, never the console CLI). Reads the PE header only.
#[cfg(windows)]
fn is_gui_exe(p: &std::path::Path) -> bool {
    use std::io::{Read, Seek, SeekFrom};
    let read = || -> std::io::Result<u16> {
        let mut f = std::fs::File::open(p)?;
        let mut b4 = [0u8; 4];
        f.seek(SeekFrom::Start(0x3C))?;
        f.read_exact(&mut b4)?;
        let pe = u32::from_le_bytes(b4) as u64;
        let mut b2 = [0u8; 2];
        f.seek(SeekFrom::Start(pe + 0x5C))?; // PE signature (4) + file header (20) + Subsystem offset (68)
        f.read_exact(&mut b2)?;
        Ok(u16::from_le_bytes(b2))
    };
    matches!(read(), Ok(2)) // IMAGE_SUBSYSTEM_WINDOWS_GUI
}
#[cfg(not(windows))]
fn is_gui_exe(_: &std::path::Path) -> bool {
    false
}

/// Whether `candidate` may be run as the CLI: not the app itself, not anything inside the app's own
/// folder tree (on Windows `cargo run` puts `target/debug/deps` first on PATH, and an old build of
/// the app named `podcastz.exe` lying there once started itself without end), and not a GUI program.
fn acceptable_cli(candidate: &std::path::Path, me: Option<&std::path::Path>) -> bool {
    if !candidate.is_file() || is_gui_exe(candidate) {
        return false;
    }
    let Some(me) = me else { return true };
    if same_file(candidate, me) {
        return false;
    }
    let home = me.parent().map(|d| d.canonicalize().unwrap_or_else(|_| d.to_path_buf()));
    let cand = candidate.canonicalize().unwrap_or_else(|_| candidate.to_path_buf());
    home.is_none_or(|h| !cand.starts_with(h))
}

/// The CLI: $PODCASTZ_CLI, a bundled sidecar `podcastz-cli` next to the executable, or `podcastz` on PATH
/// (outside the app's own folder). Never a bare name: on Windows that would search the app's own folder first.
fn cli_path() -> Result<PathBuf, String> {
    let me = std::env::current_exe().ok();
    if let Ok(p) = std::env::var("PODCASTZ_CLI") {
        let p = PathBuf::from(p);
        return if p.is_file() && !is_gui_exe(&p) && me.as_deref().is_none_or(|m| !same_file(&p, m)) {
            Ok(p)
        } else {
            Err(format!("PODCASTZ_CLI ({}) is not the podcastz CLI", p.display()))
        };
    }
    if let Some(m) = &me {
        let sidecar = m.with_file_name(if cfg!(windows) { "podcastz-cli.exe" } else { "podcastz-cli" });
        if sidecar.is_file() && !is_gui_exe(&sidecar) && !same_file(&sidecar, m) {
            return Ok(sidecar);
        }
    }
    let exe_name = if cfg!(windows) { "podcastz.exe" } else { "podcastz" };
    let path = std::env::var_os("PATH").unwrap_or_default();
    std::env::split_paths(&path)
        .map(|dir| dir.join(exe_name))
        .find(|p| acceptable_cli(p, me.as_deref()))
        .ok_or_else(|| "podcastz CLI not found: install it (see Help) or set PODCASTZ_CLI".into())
}

fn cli_command(args: &[String], cwd: Option<&str>) -> Result<Command, String> {
    let mut cmd = Command::new(cli_path()?);
    cmd.env(CHILD_MARKER, "1");
    cmd.arg("--json").args(args);
    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }
    cmd.env("PYTHONIOENCODING", "utf-8");
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    Ok(cmd)
}

/// Run a short CLI command and return its stdout (JSON). `stdin` carries secrets such as API keys.
#[tauri::command]
async fn cli(args: Vec<String>, cwd: Option<String>, stdin: Option<String>) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut cmd = cli_command(&args, cwd.as_deref())?;
        cmd.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
        let mut child = cmd.spawn().map_err(|e| format!("cannot start podcastz CLI: {e}"))?;
        if let (Some(mut pipe), Some(input)) = (child.stdin.take(), stdin) {
            pipe.write_all(input.as_bytes()).map_err(|e| e.to_string())?;
        }
        let output = child.wait_with_output().map_err(|e| e.to_string())?;
        let out = String::from_utf8_lossy(&output.stdout).to_string();
        if output.status.success() || output.status.code() == Some(1) {
            Ok(out)
        } else {
            let err = String::from_utf8_lossy(&output.stderr);
            Err(if out.trim().is_empty() { err.trim().to_string() } else { out })
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Start a long CLI task (build, sample, publish); its JSON lines arrive as `job` events.
#[tauri::command]
fn start_job(app: tauri::AppHandle, jobs: State<'_, Jobs>, args: Vec<String>, cwd: Option<String>) -> Result<u32, String> {
    let id = jobs.next.fetch_add(1, Ordering::SeqCst) + 1;
    let mut cmd = cli_command(&args, cwd.as_deref())?;
    cmd.stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = cmd.spawn().map_err(|e| format!("cannot start podcastz CLI: {e}"))?;
    let stdout = child.stdout.take().ok_or("no stdout")?;
    let stderr = child.stderr.take().ok_or("no stderr")?;
    let child = Arc::new(Mutex::new(child));
    jobs.children.lock().unwrap().insert(id, child.clone());

    let app_err = app.clone();
    std::thread::spawn(move || {
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            let _ = app_err.emit("job", JobEvent { id, line: None, stderr: Some(line), done: false, code: None });
        }
    });
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            let _ = app.emit("job", JobEvent { id, line: Some(line), stderr: None, done: false, code: None });
        }
        let code = child.lock().unwrap().wait().ok().and_then(|s| s.code());
        app.state::<Jobs>().children.lock().unwrap().remove(&id);
        let _ = app.emit("job", JobEvent { id, line: None, stderr: None, done: true, code });
    });
    Ok(id)
}

#[tauri::command]
fn cancel_job(jobs: State<'_, Jobs>, id: u32) -> Result<(), String> {
    if let Some(child) = jobs.children.lock().unwrap().get(&id) {
        child.lock().unwrap().kill().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Where each TTS key comes from (never the value): "store", an environment variable name, or none.
#[tauri::command]
fn key_status() -> serde_json::Value {
    serde_json::json!({ "store": true, "keys": secrets::status() })
}

/// Store a key in the OS credential store (the same entry the CLI reads).
#[tauri::command]
fn key_set(provider: String, value: String) -> Result<(), String> {
    secrets::set(&provider, &value)
}

#[tauri::command]
fn key_delete(provider: String) -> Result<bool, String> {
    secrets::delete(&provider)
}

/// Mark the app as running in the workspace (and clear the previous workspace).
#[tauri::command]
fn set_workspace(presence: State<'_, Presence>, workspace: Option<String>) -> Result<(), String> {
    let mut current = presence.0.lock().unwrap();
    if let Some(old) = current.take() {
        let _ = std::fs::remove_file(old.join(".podcastz").join("app.json"));
    }
    if let Some(ws) = workspace {
        let dir = PathBuf::from(&ws).join(".podcastz");
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let info = serde_json::json!({
            "pid": std::process::id(),
            "version": env!("CARGO_PKG_VERSION"),
            "started": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0),
        });
        std::fs::write(dir.join("app.json"), info.to_string()).map_err(|e| e.to_string())?;
        *current = Some(PathBuf::from(ws));
    }
    Ok(())
}

fn on_path(name: &str) -> Option<PathBuf> {
    let file = if cfg!(windows) { format!("{name}.exe") } else { name.to_string() };
    let path = std::env::var_os("PATH").unwrap_or_default();
    std::env::split_paths(&path).map(|d| d.join(&file)).find(|p| p.is_file())
}

/// What the Help page shows under "Setup check": app version, the CLI and its version, ffmpeg.
#[tauri::command]
async fn diagnostics() -> serde_json::Value {
    tauri::async_runtime::spawn_blocking(|| {
        let cli = cli_path();
        let cli_version = cli.as_ref().ok().and_then(|p| {
            let mut cmd = Command::new(p);
            cmd.env(CHILD_MARKER, "1").arg("--version");
            #[cfg(windows)]
            cmd.creation_flags(CREATE_NO_WINDOW);
            cmd.output().ok().filter(|o| o.status.success())
                .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        });
        serde_json::json!({
            "app_version": env!("CARGO_PKG_VERSION"),
            "os": std::env::consts::OS,
            "arch": std::env::consts::ARCH,
            "cli": cli.as_ref().ok().map(|p| p.display().to_string()),
            "cli_error": cli.err(),
            "cli_version": cli_version,
            "ffmpeg": on_path("ffmpeg").map(|p| p.display().to_string()),
            "ffprobe": on_path("ffprobe").map(|p| p.display().to_string()),
        })
    })
    .await
    .unwrap_or_else(|e| serde_json::json!({ "error": e.to_string() }))
}

/// Open the user's AI session in the workspace: focus its terminal window, or start one
/// (`continue_previous` → `claude --continue`, otherwise a new session with a first prompt).
#[tauri::command]
fn open_session(workspace: String, focus_only: bool, continue_previous: bool, client: Option<String>) -> Result<String, String> {
    let window = "podcastz";
    #[cfg(windows)]
    {
        let has_wt = Command::new("where").arg("wt.exe").creation_flags(CREATE_NO_WINDOW)
            .output().map(|o| o.status.success()).unwrap_or(false);
        if focus_only {
            if !has_wt {
                return Err("Windows Terminal not found; switch to the session window yourself".into());
            }
            Command::new("wt.exe").args(["-w", window, "focus-tab", "-t", "0"]).spawn().map_err(|e| e.to_string())?;
            return Ok("focused".into());
        }
        let client = client.unwrap_or_else(|| "claude".into());
        let command = if continue_previous {
            format!("{client} --continue")
        } else {
            format!("{client} '/podcastz:prepare'")
        };
        if has_wt {
            Command::new("wt.exe")
                .args(["-w", window, "new-tab", "--title", "podcastz AI session", "-d", &workspace,
                       "powershell.exe", "-NoExit", "-Command", &command])
                .spawn().map_err(|e| e.to_string())?;
        } else {
            Command::new("cmd.exe")
                .args(["/c", "start", "podcastz AI session", "powershell.exe", "-NoExit", "-Command", &command])
                .current_dir(&workspace).spawn().map_err(|e| e.to_string())?;
        }
        Ok("started".into())
    }
    #[cfg(not(windows))]
    {
        let _ = (window, focus_only, continue_previous, client);
        Err(format!("Open a terminal in {workspace} and run `claude --continue` (automatic launch is Windows-only for now)"))
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    if std::env::var_os(CHILD_MARKER).is_some() {
        // Started by the app as if it were the CLI: refuse instead of opening another window.
        eprintln!("podcastz-app was started as a child of itself; exiting");
        std::process::exit(3);
    }
    tauri::Builder::default()
        // The first plugin: a second launch only focuses the running window.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(Jobs::default())
        .manage(Presence::default())
        .invoke_handler(tauri::generate_handler![
            cli, start_job, cancel_job, set_workspace, open_session, key_status, key_set, key_delete, diagnostics
        ])
        .build(tauri::generate_context!())
        .expect("error while building podcastz")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(ws) = app.state::<Presence>().0.lock().unwrap().take() {
                    let _ = std::fs::remove_file(ws.join(".podcastz").join("app.json"));
                }
                for (_, child) in app.state::<Jobs>().children.lock().unwrap().drain() {
                    let _ = child.lock().unwrap().kill();
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cli_never_from_the_apps_own_folder() {
        let dir = std::env::temp_dir().join(format!("podcastz-cli-test-{}", std::process::id()));
        let deps = dir.join("deps");
        std::fs::create_dir_all(&deps).unwrap();
        let me = dir.join("podcastz-app.exe");
        let inside = deps.join("podcastz.exe");
        std::fs::write(&me, b"x").unwrap();
        std::fs::write(&inside, b"x").unwrap();
        let outside_dir = std::env::temp_dir().join(format!("podcastz-cli-test-out-{}", std::process::id()));
        std::fs::create_dir_all(&outside_dir).unwrap();
        let outside = outside_dir.join("podcastz.exe");
        std::fs::write(&outside, b"x").unwrap();
        assert!(!acceptable_cli(&me, Some(&me)), "the app itself");
        assert!(!acceptable_cli(&inside, Some(&me)), "an old build under the app's folder");
        assert!(acceptable_cli(&outside, Some(&me)), "an installed CLI elsewhere");
        let _ = std::fs::remove_dir_all(&dir);
        let _ = std::fs::remove_dir_all(&outside_dir);
    }

    #[cfg(windows)]
    #[test]
    fn gui_programs_are_not_the_cli() {
        // notepad is a GUI program; cmd is a console one
        let win = std::env::var("SystemRoot").unwrap_or_else(|_| r"C:\Windows".into());
        assert!(is_gui_exe(&PathBuf::from(&win).join("notepad.exe")));
        assert!(!is_gui_exe(&PathBuf::from(&win).join("System32").join("cmd.exe")));
    }

    /// The app shows release notes from CHANGELOG.md; every released version needs an entry.
    #[test]
    fn changelog_has_current_version() {
        let changelog = include_str!("../../../CHANGELOG.md");
        let heading = format!("## {} ", env!("CARGO_PKG_VERSION"));
        assert!(changelog.lines().any(|l| l.starts_with(&heading)), "CHANGELOG.md has no '{heading}…' entry");
    }

    #[test]
    fn versions_agree() {
        let conf: serde_json::Value = serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let pkg: serde_json::Value = serde_json::from_str(include_str!("../../package.json")).unwrap();
        assert_eq!(conf["version"], env!("CARGO_PKG_VERSION"));
        assert_eq!(pkg["version"], env!("CARGO_PKG_VERSION"));
    }
}
