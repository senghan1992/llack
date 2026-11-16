fn main() {
    // 서버 주소는 빌드할 때 정해집니다 — 주소가 바뀌면 다시 빌드되어야 합니다.
    println!("cargo:rerun-if-env-changed=LLACK_SERVER_URL");
    tauri_build::build()
}
